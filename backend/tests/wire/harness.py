"""
Wire-level harness.

Boots the REAL backend as a subprocess against a throwaway database, records every
Art-Net packet it sends on loopback, and decodes the capture against the patch read
straight from SQLite, independently of the engine's own channel maps.

Importing this module has no side effects. Everything that used to be a module global
in ``scripts/venue_sim/venue_sim.py`` (ports, output directory, database path) lives on
a ``WireConfig``, so pytest and the audit scripts can share one copy of the code and
several runs can share one machine.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[2]
FRAME_HZ = 40.0
IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def _free_port(kind: int) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class WireConfig:
    """Where one run lives: its backend tree, output directory and loopback ports."""

    backend: Path
    out: Path
    http_port: int
    art_port: int

    @classmethod
    def create(cls, out: Path, backend: Optional[Path] = None,
               http_port: Optional[int] = None, art_port: Optional[int] = None) -> "WireConfig":
        """Ports default to free ones, so parallel checkouts do not collide."""
        out = Path(out).resolve()
        (out / "data").mkdir(parents=True, exist_ok=True)
        return cls(
            backend=Path(backend).resolve() if backend else BACKEND_DIR,
            out=out,
            http_port=http_port or _free_port(socket.SOCK_STREAM),
            art_port=art_port or _free_port(socket.SOCK_DGRAM),
        )

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.http_port}"

    @property
    def ws(self) -> str:
        return f"ws://127.0.0.1:{self.http_port}"

    @property
    def db_path(self) -> Path:
        return self.out / "data" / "lighting.db"


def synthetic_audio(backend: Optional[Path] = None):
    """The synthetic track generators that ship with the musical tests."""
    root = str(Path(backend).resolve() if backend else BACKEND_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tests.musical import synthetic_audio as sa
    return sa


# --------------------------------------------------------------------------
# Art-Net capture
# --------------------------------------------------------------------------
def sequence_breaks(seqs) -> int:
    """Packets that did not follow their predecessor.

    Art-Net sequence runs 1..255 and wraps to 1; 0 means "sequence disabled" and
    is skipped by a sender that uses sequencing, so 255 -> 1 is not a break.
    """
    seqs = np.asarray(seqs, dtype=int)
    if len(seqs) < 2:
        return 0
    expected = seqs[:-1] % 255 + 1
    return int(np.sum(seqs[1:] != expected))


SYNC_MAGIC = b"ILS-SYNC"
_RECORD = struct.Struct("<dH")


class Capture:
    """Keeps every ArtDmx packet sent to the Art-Net port, with its arrival time.

    Packets are received and time-stamped by ``capture_proc.py`` in a process of
    its own, so the times are not stretched by whatever this process is busy with.
    The stamps arrive on that process's clock; a few datagrams carrying our own
    clock are sent at start to measure the offset between the two, and every
    packet time is stored on this process's ``time.perf_counter`` clock.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self.packets: list = []   # (t, universe, seq, length, payload), in arrival order
        self.bad: Counter = Counter()
        self.lengths: Counter = Counter()   # DMX slot count -> packets
        self.total = 0            # ArtDmx packets ever seen, including pruned ones
        self.stop = False
        self._lock = threading.Lock()
        self._offsets: list = []
        self._synced = False
        self.clock_offset = 0.0
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).with_name("capture_proc.py")), str(port)],
            stdout=subprocess.PIPE,
        )
        ready = self.proc.stdout.readline()
        if ready.strip() != b"READY":
            self.proc.kill()
            raise RuntimeError(f"capture process did not start on UDP port {port}")
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._synchronise()

    def _synchronise(self, pings: int = 9) -> None:
        """Measure the receiver's clock against ours. The smallest offset seen is
        the one least delayed between reading our clock and the receiver's stamp."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            for _ in range(pings):
                s.sendto(SYNC_MAGIC + struct.pack("<d", time.perf_counter()), ("127.0.0.1", self.port))
                time.sleep(0.01)
        deadline = time.perf_counter() + 5.0
        while len(self._offsets) < pings and time.perf_counter() < deadline:
            time.sleep(0.01)
        if not self._offsets:
            self.close()
            raise RuntimeError("capture process returned no clock-sync datagrams")
        with self._lock:
            self.clock_offset = min(self._offsets)
            # Anything that arrived before the offset was known is on the wrong clock.
            self.packets = [(p[0] - self.clock_offset,) + p[1:] for p in self.packets]
            self._synced = True

    def _run(self) -> None:
        stream = self.proc.stdout
        while not self.stop:
            header = stream.read(_RECORD.size)
            if len(header) < _RECORD.size:
                return
            t_remote, length = _RECORD.unpack(header)
            data = stream.read(length) if length else b""
            if not data:
                continue    # the receiver's once-a-second "still here"
            if data.startswith(SYNC_MAGIC):
                self._offsets.append(t_remote - struct.unpack("<d", data[len(SYNC_MAGIC):])[0])
                continue
            parsed = self.parse(data, self.bad)
            if parsed is not None:
                with self._lock:
                    t = t_remote - self.clock_offset if self._synced else t_remote
                    self.packets.append((t,) + parsed)
                    self.lengths[parsed[2]] += 1
                    self.total += 1

    @staticmethod
    def parse(data: bytes, bad: Counter):
        """(universe, seq, length, payload) for an ArtDmx packet, else None.

        Anything that breaks the Art-Net 4 ArtDmx layout is counted in ``bad``.
        """
        if data[:8] != b"Art-Net\x00" or len(data) < 18:
            bad["not_artnet"] += 1
            return None
        opcode = struct.unpack("<H", data[8:10])[0]
        if opcode != 0x5000:
            bad[f"op_{opcode:#06x}"] += 1
            return None
        protver = struct.unpack(">H", data[10:12])[0]
        if protver != 14:
            bad[f"protver_{protver}"] += 1
        seq, subuni, net = data[12], data[14], data[15]
        length = struct.unpack(">H", data[16:18])[0]
        if length != len(data) - 18:
            bad["length_mismatch"] += 1
        if length % 2 or not (2 <= length <= 512):
            bad["length_illegal"] += 1
        return ((net << 8) | subuni, seq, length, data[18:18 + length])

    def window(self, t0: float, t1: float) -> dict:
        """{universe: (times[N], frames[N,512] uint8, seqs[N])} for packets in [t0,t1)."""
        with self._lock:
            times_all = [p[0] for p in self.packets]
            chosen = self.packets[bisect_left(times_all, t0):bisect_left(times_all, t1)]
        per = defaultdict(list)
        for p in chosen:
            per[p[1]].append(p)
        out = {}
        for uni, pk in per.items():
            times = np.array([p[0] for p in pk])
            frames = np.zeros((len(pk), 512), dtype=np.uint8)
            for i, p in enumerate(pk):
                frames[i, :len(p[4])] = np.frombuffer(p[4], dtype=np.uint8)
            out[uni] = (times, frames, np.array([p[2] for p in pk]))
        return out

    def since(self, t0: float) -> list:
        with self._lock:
            return [p for p in self.packets if p[0] >= t0]

    def prune(self, before: float) -> None:
        """Forget packets older than ``before``. A long soak must call this."""
        with self._lock:
            times_all = [p[0] for p in self.packets]
            del self.packets[:bisect_left(times_all, before)]

    def close(self) -> None:
        self.stop = True
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(5)
        self.thread.join(timeout=2.0)
        self.proc.stdout.close()


# --------------------------------------------------------------------------
# Backend process
# --------------------------------------------------------------------------
def is_loopback(address: str) -> bool:
    """True only for a literal loopback IP address. A name is not trusted to be one."""
    try:
        return ipaddress.ip_address(str(address).strip()).is_loopback
    except ValueError:
        return False


class Server:
    """One boot of the backend, pointed at the run's database and capture port."""

    def __init__(self, cfg: WireConfig, tag: str, extra_env: Optional[dict] = None) -> None:
        self.cfg = cfg
        # This harness must never light a real rig. The backend's own default is
        # limited broadcast, so the destination is fixed here and may only be
        # overridden with another loopback address.
        target = (extra_env or {}).get("ARTNET_IP", "127.0.0.1")
        if not is_loopback(target):
            raise ValueError(f"the wire harness sends Art-Net to loopback only, not {target!r}")
        self.log_path = cfg.out / f"server_{tag}.log"
        self.log = open(self.log_path, "w", encoding="utf-8", errors="replace")
        env = dict(os.environ)
        env.update({
            "DATABASE_URL": f"sqlite:///{cfg.db_path.as_posix()}",
            "ARTNET_IP": "127.0.0.1",
            "ARTNET_PORT": str(cfg.art_port),
            "AUDIO_CAPTURE_AUTO_START": "false",
            "AUTH_ENABLED": "true",
            "DEBUG": "false",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        })
        env.pop("ILS_OPERATOR_PASSWORD", None)
        env.update(extra_env or {})
        self.t_spawn = time.perf_counter()
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(cfg.http_port)],
            cwd=str(cfg.backend), env=env, stdout=self.log, stderr=subprocess.STDOUT,
            # A new group on Windows so Ctrl+Break reaches the backend and not us.
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
        )

    def alive(self) -> bool:
        return self.proc.poll() is None

    def wait_http(self, timeout: float = 180.0) -> float:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if not self.alive():
                raise RuntimeError(
                    f"backend exited early, code {self.proc.returncode}; see {self.log_path}")
            try:
                r = httpx.get(f"{self.cfg.base}/health", timeout=1.0)
                if r.status_code in (200, 503):
                    return time.perf_counter() - self.t_spawn
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"backend never answered /health; see {self.log_path}")

    def read_log(self) -> str:
        self.log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def setup_code(self, timeout: float = 20.0) -> str:
        """The first-run code, as an installer would read it off the console."""
        deadline = time.perf_counter() + timeout
        while True:
            m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", self.read_log())
            if m:
                return m.group(1)
            if time.perf_counter() > deadline:
                raise RuntimeError(f"no setup code in the console log; see {self.log_path}")
            time.sleep(0.2)

    def graceful_stop(self, timeout: float = 30.0) -> float:
        """Ask the backend to stop the way a console would. Returns seconds to exit."""
        t = time.perf_counter()
        self.proc.send_signal(signal.CTRL_BREAK_EVENT if IS_WINDOWS else signal.SIGINT)
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.hard_kill()
            raise RuntimeError("graceful stop timed out; the backend was killed")
        finally:
            self.log.close()
        return time.perf_counter() - t

    def hard_kill(self) -> None:
        if self.alive():
            self.proc.kill()
            self.proc.wait(10)
        if not self.log.closed:
            self.log.close()


def process_tree_usage(pid: int) -> tuple:
    """(RSS in MB, threads, CPU seconds) summed over a process and its children.

    On Windows a Store or venv ``python.exe`` is a launcher stub and the real
    interpreter is its child, so the root process alone under-reports badly.
    """
    import psutil
    root = psutil.Process(pid)
    procs = [root] + root.children(recursive=True)
    rss = threads = cpu = 0.0
    for p in procs:
        try:
            rss += p.memory_info().rss
            threads += p.num_threads()
            cpu += sum(p.cpu_times()[:2])
        except psutil.Error:
            continue
    return round(rss / 1e6, 1), int(threads), round(cpu, 1)


# --------------------------------------------------------------------------
# Operator walk-through
# --------------------------------------------------------------------------
async def first_run_setup(cfg: WireConfig, srv: Server) -> tuple:
    """Complete first-run setup. Returns (authenticated client, token, password)."""
    password = secrets.token_urlsafe(12)
    client = httpx.AsyncClient(base_url=cfg.base, timeout=30.0)
    r = await client.post("/api/auth/setup",
                          json={"setup_code": srv.setup_code(), "password": password})
    r.raise_for_status()
    token = r.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client, token, password


async def rig_from_template(client: httpx.AsyncClient, template: str = "Small Club",
                            rig_name: str = "Sim Venue") -> int:
    """Apply a seeded venue template by name and put it on the engine."""
    items = (await client.get("/api/templates/")).json().get("items", [])
    match = [t for t in items if t.get("name") == template]
    if not match:
        raise RuntimeError(f"no template named {template!r}; have {[t.get('name') for t in items]}")
    r = await client.post(f"/api/templates/{match[0]['id']}/apply", params={"rig_name": rig_name})
    r.raise_for_status()
    rig_id = r.json()["id"]
    (await client.post(f"/api/rigs/{rig_id}/activate")).raise_for_status()
    return rig_id


# --------------------------------------------------------------------------
# Patch, read from the database independently of the engine
# --------------------------------------------------------------------------
def read_patch(db_path: Path, rig_id: int) -> list:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    fixtures = []
    rows = con.execute(
        "SELECT rf.*, f.model AS profile_name, f.manufacturer AS manufacturer, "
        "f.fixture_type AS fixture_type, f.pan_range AS pan_range, f.tilt_range AS tilt_range, "
        "m.name AS mode_name, m.channel_count AS channel_count "
        "FROM rig_fixtures rf JOIN fixtures f ON f.id = rf.fixture_id "
        "LEFT JOIN fixture_modes m ON m.id = rf.mode_id WHERE rf.rig_id = ? ORDER BY rf.id",
        (rig_id,),
    ).fetchall()
    for r in rows:
        chans = con.execute(
            "SELECT * FROM fixture_channels WHERE mode_id = ? ORDER BY channel_number", (r["mode_id"],)
        ).fetchall()
        fixtures.append({
            "id": r["id"], "name": r["name"], "universe": r["universe"], "address": r["dmx_address"],
            "group": r["group_name"], "zone": r["zone"],
            "profile": f"{r['manufacturer']} {r['profile_name']}", "ftype": str(r["fixture_type"]).lower(),
            "mode": r["mode_name"], "channel_count": r["channel_count"],
            "pan_range": r["pan_range"], "tilt_range": r["tilt_range"],
            "channels": [{
                "offset": c["channel_number"] - 1,
                "type": str(c["channel_type"]).lower(),
                "name": c["name"],
                "default": c["default_value"] or 0,
                "is_fine": bool(c["is_fine"]),
            } for c in chans],
        })
    con.close()
    return fixtures


COLOUR_ADD = {"red", "green", "blue", "white", "amber", "lime", "uv", "warm_white", "cool_white", "indigo"}
COLOUR_SUB = {"cyan", "magenta", "yellow"}


def fixture_series(fx: dict, frames: np.ndarray) -> dict:
    """Decode one fixture's channels out of a universe's frames."""
    base = fx["address"] - 1
    by_type = defaultdict(list)
    for c in fx["channels"]:
        idx = base + c["offset"]
        if 0 <= idx < 512:
            by_type[c["type"]].append((c, frames[:, idx].astype(np.float32)))
    n = frames.shape[0]

    def first(t):
        for c, v in by_type.get(t, []):
            if not c["is_fine"]:
                return v
        return None

    dim = first("dimmer")
    if dim is None:
        dim = first("intensity")
    add = [v for t in COLOUR_ADD for c, v in by_type.get(t, []) if not c["is_fine"]]
    sub = [v for t in COLOUR_SUB for c, v in by_type.get(t, []) if not c["is_fine"]]
    if add:
        colour = np.max(np.stack(add), axis=0) / 255.0
    elif sub:
        # CMY is subtractive: 0 is fully open.
        colour = 1.0 - np.min(np.stack(sub), axis=0) / 255.0
    else:
        colour = np.ones(n, dtype=np.float32)
    level = (dim / 255.0 if dim is not None else np.ones(n, dtype=np.float32)) * colour

    def sixteen(t, fine_t):
        coarse = first(t)
        if coarse is None:
            return None
        fine = None
        for c, v in by_type.get(fine_t, []) + by_type.get(t, []):
            if c["is_fine"] or c["type"] == fine_t:
                fine = v
                break
        return coarse * 256.0 + (fine if fine is not None else 0.0), fine is not None

    return {
        "level": level, "dimmer": dim, "has_dimmer": dim is not None,
        "pan": sixteen("pan", "pan_fine"), "tilt": sixteen("tilt", "tilt_fine"),
        "strobe": [v for t in ("strobe", "shutter") for c, v in by_type.get(t, [])],
        "other": [(c, v) for c, v in by_type.get("other", [])],
        "by_type": by_type,
    }


def analyse(cap: Capture, patch: list, t0: float, t1: float,
            beats: Optional[np.ndarray] = None, extra: Optional[dict] = None,
            save_to: Optional[Path] = None) -> dict:
    """Everything the capture says about [t0, t1), as plain JSON-able figures."""
    win = cap.window(t0, t1)
    dur = t1 - t0
    res: dict = {"duration_s": round(dur, 2), "universes_on_wire": sorted(int(u) for u in win)}
    rig_unis = sorted({fx["universe"] for fx in patch})
    res["universes_patched"] = rig_unis

    # transport
    tx = {}
    for uni, (times, frames, seqs) in win.items():
        gaps = np.diff(times) * 1000.0 if len(times) > 1 else np.array([0.0])
        tx[int(uni)] = {
            "packets": int(len(times)), "fps": round(len(times) / dur, 1),
            "gap_ms_p50": round(float(np.percentile(gaps, 50)), 1),
            "gap_ms_p99": round(float(np.percentile(gaps, 99)), 1),
            "gap_ms_max": round(float(gaps.max()), 1),
            "seq_values_distinct": int(len(set(seqs.tolist()))),
            "seq_min": int(seqs.min()), "seq_max": int(seqs.max()),
            "seq_breaks": sequence_breaks(seqs),
        }
    res["transport"] = tx

    # footprint check + decode
    levels, movers, strobes, others = [], [], [], []
    out_of_footprint = 0
    for uni, (times, frames, _) in win.items():
        mask = np.zeros(512, dtype=bool)
        for fx in patch:
            if fx["universe"] != uni:
                continue
            a = fx["address"] - 1
            mask[a:a + (fx["channel_count"] or len(fx["channels"]))] = True
        stray = np.where((frames[:, ~mask] != 0).any(axis=0))[0]
        out_of_footprint += int(len(stray))
        for fx in patch:
            if fx["universe"] != uni:
                continue
            s = fixture_series(fx, frames)
            levels.append((fx, times, s["level"]))
            if s["pan"] is not None or s["tilt"] is not None:
                movers.append((fx, times, s))
            for v in s["strobe"]:
                strobes.append((fx, v))
            for c, v in s["other"]:
                others.append((fx, c, v))
    res["nonzero_channels_outside_patch"] = out_of_footprint
    res["unpatched_universes_transmitted"] = sorted(set(res["universes_on_wire"]) - set(rig_unis))

    if not levels:
        return res

    # resample every fixture level onto a common 40 Hz grid
    grid = np.arange(t0, t1, 1 / FRAME_HZ)
    mat = np.stack([np.interp(grid, t, lv) for _, t, lv in levels])   # [fixtures, T]
    rig = mat.mean(axis=0)
    res["level"] = {
        "rig_mean": round(float(rig.mean()), 3), "rig_min": round(float(rig.min()), 3),
        "rig_max": round(float(rig.max()), 3),
        "fixture_peak_max": round(float(mat.max()), 3),
        "fixtures_ever_lit": int((mat.max(axis=1) > 0.02).sum()), "fixtures_total": int(mat.shape[0]),
        "pct_time_rig_dark": round(float((rig < 0.01).mean() * 100), 1),
    }
    dims = [fixture_series(fx, win[fx["universe"]][1])["dimmer"] for fx in patch if fx["universe"] in win]
    dims = [d for d in dims if d is not None]
    if dims:
        res["dimmer_channel_max"] = int(max(d.max() for d in dims))

    # flash rate: rises of >= 25% of full scale inside 75 ms
    def flashes(series: np.ndarray, rise: float = 0.25) -> tuple:
        d3 = series[3:] - series[:-3]
        edges = np.where((d3[1:] >= rise) & (d3[:-1] < rise))[0]
        if len(edges) == 0:
            return 0, 0.0
        tt = grid[edges]
        worst = max(int(np.sum((tt >= x) & (tt < x + 1.0))) for x in tt)
        return int(len(edges)), float(worst)

    n_rig, worst_rig = flashes(rig)
    per_fx = [flashes(mat[i]) for i in range(mat.shape[0])]
    res["flash"] = {
        "rig_flash_edges": n_rig, "rig_worst_flashes_in_1s": worst_rig,
        "fixture_worst_flashes_in_1s": float(max(p[1] for p in per_fx)),
        "fixtures_flashing_over_3_per_s": int(sum(1 for p in per_fx if p[1] > 3)),
    }
    # spectral share of rig-level energy in the 3-20 Hz photosensitive band
    if len(rig) > 80:
        spec = np.abs(np.fft.rfft(rig - rig.mean())) ** 2
        freqs = np.fft.rfftfreq(len(rig), 1 / FRAME_HZ)
        band = spec[(freqs >= 3) & (freqs <= 20)].sum()
        res["flash"]["rig_energy_share_3_20hz"] = round(float(band / max(spec.sum(), 1e-12)), 3)

    # strobe / shutter channel usage
    if strobes:
        vals: Counter = Counter()
        for _, v in strobes:
            vals.update(v.astype(int).tolist())
        res["strobe_shutter_values_top"] = vals.most_common(6)
        res["strobe_shutter_distinct"] = len(vals)

    # what each channel type did on the wire
    type_vals = defaultdict(set)
    type_count: Counter = Counter()
    for uni, (times, frames, _) in win.items():
        for fx in patch:
            if fx["universe"] != uni:
                continue
            for c in fx["channels"]:
                idx = fx["address"] - 1 + c["offset"]
                if 0 <= idx < 512:
                    type_vals[c["type"]].update(np.unique(frames[:, idx]).tolist())
                    type_count[c["type"]] += 1
    res["channel_types_on_wire"] = {
        t: {"channels": type_count[t], "distinct_values": len(v), "min": int(min(v)), "max": int(max(v))}
        for t, v in sorted(type_vals.items())
    }

    # channels typed "other" must sit at their default
    moved = []
    for fx, c, v in others:
        distinct = sorted(set(v.astype(int).tolist()))
        if distinct != [c["default"]]:
            moved.append(f"{fx['name']} ch{c['offset'] + 1} '{c['name']}' default={c['default']} saw={distinct[:6]}")
    res["other_channels_total"] = len(others)
    res["other_channels_off_default"] = moved[:8]

    # movement
    if movers:
        pan_use, tilt_use, pan_speed, sixteen_bit = [], [], [], 0
        for fx, times, s in movers:
            for key, use in (("pan", pan_use), ("tilt", tilt_use)):
                if s[key] is None:
                    continue
                v, is16 = s[key]
                use.append(float(v.max() - v.min()) / 65535.0)
                if key == "pan":
                    sixteen_bit += int(is16)
                    if len(v) > 2:
                        dt = np.diff(times)
                        sp = np.abs(np.diff(v)) / 65535.0 / np.maximum(dt, 1e-3)
                        pan_speed.append(float(np.percentile(sp, 99)))
        res["movement"] = {
            "movers": len(movers), "movers_with_16bit_pan": sixteen_bit,
            "pan_range_used_pct_median": round(100 * float(np.median(pan_use)), 1) if pan_use else None,
            "pan_range_used_pct_max": round(100 * float(np.max(pan_use)), 1) if pan_use else None,
            "tilt_range_used_pct_median": round(100 * float(np.median(tilt_use)), 1) if tilt_use else None,
            "pan_speed_p99_pct_range_per_s": round(100 * float(np.max(pan_speed)), 1) if pan_speed else None,
        }

    # beat alignment: where does the light's attack land relative to the kick?
    if beats is not None and len(beats) > 8:
        attack = np.maximum(0.0, np.diff(rig, prepend=rig[0]))
        offs = []
        for b in beats:
            m = (grid >= b - 0.20) & (grid <= b + 0.20)
            if m.sum() < 4:
                continue
            seg = attack[m]
            if seg.max() >= 0.02:
                offs.append(float(grid[m][int(seg.argmax())] - b))
        lags = np.arange(-12, 13)
        train = np.zeros_like(rig)
        for b in beats:
            i = int(round((b - t0) * FRAME_HZ))
            if 0 <= i < len(train):
                train[i] = 1.0
        xc = [float(np.sum(np.roll(train, int(lag)) * attack)) for lag in lags]
        z = (np.max(xc) - np.mean(xc)) / (np.std(xc) + 1e-9)
        res["beat_alignment"] = {
            "beats": int(len(beats)), "beats_with_visible_attack": len(offs),
            "attack_offset_ms_median": round(1000 * float(np.median(offs)), 0) if offs else None,
            "attack_offset_ms_iqr": round(1000 * float(np.percentile(offs, 75) - np.percentile(offs, 25)), 0) if offs else None,
            "xcorr_peak_lag_ms": int(lags[int(np.argmax(xc))] * 25),
            "xcorr_peak_z": round(float(z), 2),
        }
    if extra:
        res.update(extra)
    if save_to is not None:
        np.savez_compressed(save_to, grid=grid, rig=rig, mat=mat)
    return res


def last_lit(cap: Capture, patch: list, t_cmd: float, t_until: float) -> tuple:
    """(seconds after t_cmd of the last lit frame, peak level later than 0.5 s after it)."""
    last, peak_after = 0.0, 0.0
    for uni, (times, frames, _) in cap.window(t_cmd, t_until).items():
        for fx in patch:
            if fx["universe"] != uni:
                continue
            lv = fixture_series(fx, frames)["level"]
            lit = np.where(lv > 0)[0]
            if len(lit):
                last = max(last, float(times[lit[-1]] - t_cmd))
            late = lv[times >= t_cmd + 0.5]
            if len(late):
                peak_after = max(peak_after, float(late.max()))
    return round(last, 3), round(peak_after, 3)


def first_lit(cap: Capture, patch: list, t_cmd: float, t_until: float) -> Optional[float]:
    """Seconds after t_cmd at which any fixture first shows light, or None."""
    first = None
    for uni, (times, frames, _) in cap.window(t_cmd, t_until).items():
        for fx in patch:
            if fx["universe"] != uni:
                continue
            lv = fixture_series(fx, frames)["level"]
            lit = np.where(lv > 0.02)[0]
            if len(lit):
                t = float(times[lit[0]] - t_cmd)
                first = t if first is None else min(first, t)
    return None if first is None else round(first, 3)


# --------------------------------------------------------------------------
# Audio streaming
# --------------------------------------------------------------------------
def pcm_chunks(samples: np.ndarray, chunk: int) -> list:
    """Float samples as the int16 chunks a capture client sends, whole chunks only."""
    pcm = np.clip(samples * 32767.0, -32768, 32767).astype("<i2")
    n = (len(pcm) // chunk) * chunk
    return [pcm[i:i + chunk].tobytes() for i in range(0, n, chunk)]


class AudioFeed:
    """A capture client on /ws/audio, sending at real-time pace."""

    def __init__(self, cfg: WireConfig, token: str, sample_rate: int = 44100, chunk: int = 2048) -> None:
        self.cfg, self.token = cfg, token
        self.sample_rate, self.chunk = sample_rate, chunk
        self.ws = None
        self.seen: list = []
        self._reader = None

    async def __aenter__(self):
        import websockets
        self.ws = await websockets.connect(
            f"{self.cfg.ws}/ws/audio?token={self.token}", max_size=None)
        self._reader = asyncio.create_task(self._drain())
        return self

    async def _drain(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, str):
                    try:
                        d = json.loads(msg)
                    except Exception:
                        continue
                    if d.get("type") == "analysis":
                        self.seen.append((time.perf_counter(), d))
        except Exception:
            pass

    async def __aexit__(self, *exc):
        self._reader.cancel()
        try:
            await self.ws.close()
        except Exception:
            pass

    async def play(self, audio) -> float:
        """Send float samples, or chunks from ``pcm_chunks``, at real-time pace.

        Returns the capture-clock time of sample 0.
        """
        chunks = audio if isinstance(audio, list) else pcm_chunks(audio, self.chunk)
        t_start = time.perf_counter()
        for i, payload in enumerate(chunks):
            # A capture device hands over a chunk once its last sample exists.
            due = t_start + (i + 1) * self.chunk / self.sample_rate
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await self.ws.send(payload)
        return t_start


def summarise_analysis(seen: list, t0: float, t1: float) -> dict:
    """What the backend said it heard between t0 and t1."""
    msgs = [d for t, d in seen if t0 <= t < t1]
    if not msgs:
        return {"analysis_messages": 0}
    out = {"analysis_messages": len(msgs), "top_level_keys": sorted(msgs[-1].keys())[:40]}

    def dig(d, *path):
        for p in path:
            if not isinstance(d, dict) or p not in d:
                return None
            d = d[p]
        return d

    bpms = [v for v in (dig(m, "beat", "bpm") or m.get("bpm") for m in msgs) if isinstance(v, (int, float))]
    if bpms:
        tail = bpms[len(bpms) // 2:]
        out["bpm_median_second_half"] = round(float(np.median(tail)), 1)
        out["bpm_first_reported"] = round(float(bpms[0]), 1)
    lighting = [m.get("lighting") for m in msgs if isinstance(m.get("lighting"), dict)]
    if lighting:
        out["lighting_keys"] = sorted(lighting[-1].keys())[:40]
        for key in ("state", "section", "lighting_state", "genre", "palette", "look", "movement"):
            vals = [str(item.get(key)) for item in lighting if item.get(key) is not None]
            if vals:
                seq = [vals[0]] + [b for a, b in zip(vals, vals[1:]) if a != b]
                out[f"lighting.{key}_sequence"] = seq[:25]
    return out
