"""
Wire-level venue simulation.

Boots the REAL backend as a subprocess against a throwaway database, walks the
first-run flow an installer would, patches a rig from a seeded template, plays
synthetic music into the audio WebSocket at real-time pace, and records every
Art-Net packet the box puts on the wire (loopback, non-default port so nothing
reaches the LAN). The capture is then decoded against the patch read straight
from the database - independently of the engine's own channel maps.

Usage: python venue_sim.py <backend_dir> <out_dir>
"""
from __future__ import annotations

import asyncio
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
from collections import Counter, defaultdict
from pathlib import Path

import httpx
import numpy as np
import websockets

BACKEND = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
DATA = OUT / "data"
DATA.mkdir(exist_ok=True)

HTTP_PORT = 8031
ART_PORT = 16454
BASE = f"http://127.0.0.1:{HTTP_PORT}"
WS = f"ws://127.0.0.1:{HTTP_PORT}"
DB_PATH = DATA / "lighting.db"

sys.path.insert(0, str(BACKEND))
from tests.musical import synthetic_audio as sa  # noqa: E402

SR = sa.SAMPLE_RATE
CHUNK = sa.CHUNK_SIZE
REPORT: dict = {"phases": {}, "checks": {}, "notes": []}


def note(msg: str) -> None:
    print(msg, flush=True)
    REPORT["notes"].append(msg)


# --------------------------------------------------------------------------
# Art-Net capture
# --------------------------------------------------------------------------
class Capture:
    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self.sock.bind(("127.0.0.1", ART_PORT))
        self.sock.settimeout(0.2)
        self.packets: list = []   # (t, universe, seq, length, payload)
        self.bad = Counter()
        self.stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.stop:
            try:
                data, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                # Windows raises WSAECONNRESET on a UDP socket after an ICMP
                # port-unreachable; nothing to do with us.
                continue
            t = time.perf_counter()
            if data[:8] != b"Art-Net\x00":
                self.bad["not_artnet"] += 1
                continue
            opcode = struct.unpack("<H", data[8:10])[0]
            if opcode != 0x5000:
                self.bad[f"op_{opcode:#06x}"] += 1
                continue
            protver = struct.unpack(">H", data[10:12])[0]
            if protver != 14:
                self.bad[f"protver_{protver}"] += 1
            seq, phys, subuni, net = data[12], data[13], data[14], data[15]
            length = struct.unpack(">H", data[16:18])[0]
            if length != len(data) - 18:
                self.bad["length_mismatch"] += 1
            if length % 2 or not (2 <= length <= 512):
                self.bad["length_illegal"] += 1
            self.packets.append((t, (net << 8) | subuni, seq, length, data[18:18 + length]))

    def window(self, t0: float, t1: float) -> dict:
        """{universe: (times[N], frames[N,512] uint8, seqs[N])} for packets in [t0,t1)."""
        per = defaultdict(list)
        for p in self.packets:
            if t0 <= p[0] < t1:
                per[p[1]].append(p)
        out = {}
        for uni, pk in per.items():
            times = np.array([p[0] for p in pk])
            frames = np.zeros((len(pk), 512), dtype=np.uint8)
            for i, p in enumerate(pk):
                frames[i, :len(p[4])] = np.frombuffer(p[4], dtype=np.uint8)
            out[uni] = (times, frames, np.array([p[2] for p in pk]))
        return out


# --------------------------------------------------------------------------
# Backend process
# --------------------------------------------------------------------------
SERVERS: list = []


class Server:
    def __init__(self, tag: str) -> None:
        SERVERS.append(self)
        self.log_path = OUT / f"server_{tag}.log"
        self.log = open(self.log_path, "w", encoding="utf-8", errors="replace")
        env = dict(os.environ)
        env.update({
            "DATABASE_URL": f"sqlite:///{DB_PATH.as_posix()}",
            "ARTNET_IP": "127.0.0.1",
            "ARTNET_PORT": str(ART_PORT),
            "AUDIO_CAPTURE_AUTO_START": "false",
            "DEBUG": "false",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        })
        env.pop("ILS_OPERATOR_PASSWORD", None)
        self.t_spawn = time.perf_counter()
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(HTTP_PORT)],
            cwd=str(BACKEND), env=env, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    def wait_http(self, timeout: float = 180.0) -> float:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"backend exited early, code {self.proc.returncode}")
            try:
                r = httpx.get(f"{BASE}/health", timeout=1.0)
                if r.status_code in (200, 503):
                    return time.perf_counter() - self.t_spawn
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError("backend never answered /health")

    def read_log(self) -> str:
        self.log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def graceful_stop(self, timeout: float = 30.0) -> float:
        t = time.perf_counter()
        self.proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            note("  !! graceful stop timed out; killing")
            self.proc.kill()
            self.proc.wait(10)
        return time.perf_counter() - t

    def hard_kill(self) -> None:
        self.proc.kill()
        self.proc.wait(10)


# --------------------------------------------------------------------------
# Patch, read from the database independently of the engine
# --------------------------------------------------------------------------
def read_patch(rig_id: int) -> list:
    con = sqlite3.connect(str(DB_PATH))
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


def analyse(cap: Capture, patch: list, name: str, t0: float, t1: float,
            beats: np.ndarray | None = None, extra: dict | None = None) -> dict:
    win = cap.window(t0, t1)
    dur = t1 - t0
    res: dict = {"duration_s": round(dur, 2), "universes_on_wire": sorted(int(u) for u in win)}
    rig_unis = sorted({fx["universe"] for fx in patch})
    res["universes_patched"] = rig_unis

    # transport
    tx = {}
    for uni, (times, frames, seqs) in win.items():
        gaps = np.diff(times) * 1000.0 if len(times) > 1 else np.array([0.0])
        dseq = np.diff(seqs.astype(int)) % 256 if len(seqs) > 1 else np.array([1])
        tx[int(uni)] = {
            "packets": int(len(times)), "fps": round(len(times) / dur, 1),
            "gap_ms_p50": round(float(np.percentile(gaps, 50)), 1),
            "gap_ms_p99": round(float(np.percentile(gaps, 99)), 1),
            "gap_ms_max": round(float(gaps.max()), 1),
            "seq_values_distinct": int(len(set(seqs.tolist()))),
            "seq_skips": int(np.sum((dseq != 1) & (seqs[1:] != 0))) if len(seqs) > 1 else 0,
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
    grid = np.arange(t0, t1, 1 / 40.0)
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
        freqs = np.fft.rfftfreq(len(rig), 1 / 40.0)
        band = spec[(freqs >= 3) & (freqs <= 20)].sum()
        res["flash"]["rig_energy_share_3_20hz"] = round(float(band / max(spec.sum(), 1e-12)), 3)

    # strobe / shutter channel usage
    if strobes:
        vals = Counter()
        for _, v in strobes:
            vals.update(v.astype(int).tolist())
        res["strobe_shutter_values_top"] = vals.most_common(6)
        res["strobe_shutter_distinct"] = len(vals)

    # what each channel type did on the wire
    type_vals = defaultdict(set)
    type_count = Counter()
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
            i = int(round((b - t0) * 40))
            if 0 <= i < len(train):
                train[i] = 1.0
        xc = [float(np.sum(np.roll(train, int(l)) * attack)) for l in lags]
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
    np.savez_compressed(OUT / f"cap_{name}.npz", grid=grid, rig=rig, mat=mat)
    return res


# --------------------------------------------------------------------------
# Audio streaming
# --------------------------------------------------------------------------
class AudioFeed:
    def __init__(self, token: str) -> None:
        self.token = token
        self.ws = None
        self.seen: list = []
        self._reader = None

    async def __aenter__(self):
        self.ws = await websockets.connect(f"{WS}/ws/audio?token={self.token}", max_size=None)
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
        await self.ws.close()

    async def play(self, samples: np.ndarray) -> float:
        """Send at real-time pace. Returns the capture-clock time of sample 0."""
        pcm = np.clip(samples * 32767.0, -32768, 32767).astype("<i2")
        n = (len(pcm) // CHUNK) * CHUNK
        t_start = time.perf_counter()
        for i, start in enumerate(range(0, n, CHUNK)):
            # A capture device hands over a chunk once its last sample exists.
            due = t_start + (start + CHUNK) / SR
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await self.ws.send(pcm[start:start + CHUNK].tobytes())
        return t_start


def summarise_analysis(seen: list, t0: float, t1: float) -> dict:
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
            vals = [str(l.get(key)) for l in lighting if l.get(key) is not None]
            if vals:
                seq = [vals[0]] + [b for a, b in zip(vals, vals[1:]) if a != b]
                out[f"lighting.{key}_sequence"] = seq[:25]
    return out


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------
async def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    cap = Capture()

    # ---- boot 1: brand-new install ---------------------------------------
    note("== BOOT 1: fresh install, empty database")
    srv = Server("boot1")
    t_http = srv.wait_http()
    note(f"  /health answered {t_http:.1f}s after process start")
    REPORT["checks"]["boot1_seconds_to_http"] = round(t_http, 1)

    t0 = time.perf_counter()
    await asyncio.sleep(5.0)
    win = cap.window(t0, time.perf_counter())
    REPORT["phases"]["P0_fresh_install_no_rig"] = {
        "packets": int(sum(len(v[0]) for v in win.values())),
        "universes_on_wire": sorted(int(u) for u in win),
    }
    note(f"  fresh install, nothing patched: {REPORT['phases']['P0_fresh_install_no_rig']}")

    # unauthenticated probes
    probes = {}
    with httpx.Client(base_url=BASE, timeout=10.0) as c:
        probes["GET /health"] = [c.get("/health").status_code, c.get("/health").json()]
        probes["GET /api/rigs/"] = c.get("/api/rigs/").status_code
        probes["POST /api/trigger/blackout"] = c.post("/api/trigger/blackout").status_code
        probes["POST /api/dmx/channel"] = c.post("/api/dmx/channel", json={"universe": 0, "channel": 1, "value": 255}).status_code
        probes["POST /api/strobe"] = c.post("/api/strobe", json={}).status_code
        probes["GET /api/auth/status"] = c.get("/api/auth/status").json()
    try:
        async with websockets.connect(f"{WS}/ws/audio") as w:
            await w.recv()
            probes["WS /ws/audio no token"] = "ACCEPTED"
    except Exception as e:
        probes["WS /ws/audio no token"] = f"rejected ({type(e).__name__}: {str(e)[:60]})"
    REPORT["checks"]["unauthenticated"] = probes
    note(f"  unauthenticated probes: {json.dumps(probes)}")

    # first-run setup, with the code the box printed on its console
    log = srv.read_log()
    m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", log) or re.search(r"[Ss]etup code[^A-Za-z0-9]+([A-Z0-9\-]{4,})", log)
    if not m:
        raise RuntimeError("no setup code found in the console log")
    password = secrets.token_urlsafe(12)
    client = httpx.AsyncClient(base_url=BASE, timeout=30.0)
    r = await client.post("/api/auth/setup", json={"setup_code": m.group(1), "password": password})
    note(f"  setup with console code -> HTTP {r.status_code}")
    r.raise_for_status()
    token = r.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"

    health = (await client.get("/api/health")).json()
    REPORT["checks"]["health_after_setup"] = health
    note(f"  health: {json.dumps(health)}")

    # ---- patch a rig from a seeded venue template ------------------------
    tpl = (await client.get("/api/templates/")).json()
    items = tpl.get("items", [])
    note(f"  seeded templates: {[(t.get('id'), t.get('name')) for t in items]}")
    REPORT["checks"]["templates"] = [t.get("name") for t in items]

    def movers_in(t):
        return sum(s.get("count", 1) for s in (t.get("fixture_slots") or [])
                   if "mov" in str(s.get("fixture_type", "")) or str(s.get("fixture_type")) in ("beam", "spot"))

    chosen = max(items, key=lambda t: (movers_in(t) > 0, -abs(sum(s.get("count", 1) for s in (t.get("fixture_slots") or [])) - 16)))
    r = await client.post(f"/api/templates/{chosen['id']}/apply", params={"rig_name": "Sim Venue"})
    note(f"  apply template '{chosen['name']}' -> HTTP {r.status_code} {r.text[:160]}")
    r.raise_for_status()
    rig_id = r.json()["id"]
    r = await client.post(f"/api/rigs/{rig_id}/activate")
    note(f"  activate rig -> HTTP {r.status_code}")
    r.raise_for_status()

    patch = read_patch(rig_id)
    types = Counter(fx["ftype"] for fx in patch)
    foot = sum(fx["channel_count"] or 0 for fx in patch)
    REPORT["rig"] = {
        "template": chosen["name"], "fixtures": len(patch), "by_type": dict(types),
        "universes": sorted({fx["universe"] for fx in patch}), "channels_patched": foot,
        "profiles": sorted({f"{fx['profile']} [{fx['mode']}]" for fx in patch}),
        "channel_types": dict(Counter(c["type"] for fx in patch for c in fx["channels"])),
    }
    note(f"  rig: {json.dumps(REPORT['rig'])}")
    (OUT / "patch.json").write_text(json.dumps(patch, indent=1))

    # ---- P1: rig live, never heard any audio -----------------------------
    await asyncio.sleep(1.0)
    t0 = time.perf_counter()
    await asyncio.sleep(6.0)
    REPORT["phases"]["P1_rig_live_no_audio_yet"] = analyse(cap, patch, "P1", t0, time.perf_counter())
    note(f"  P1 rig live, no audio yet: {json.dumps(REPORT['phases']['P1_rig_live_no_audio_yet'])}")

    # ---- P2: a track with an intro, a build and a drop -------------------
    track = sa.intro_build_drop_track(bpm=128.0)
    note(f"== P2: intro/build/drop @128 BPM, {track.duration_s:.0f}s, drop at {track.drop_time:.1f}s")
    async with AudioFeed(token) as feed:
        t_begin = time.perf_counter()
        t_start = await feed.play(track.samples)
        t_end = time.perf_counter()
        beats = t_start + track.beat_times
        drop_t = t_start + track.drop_time
        REPORT["phases"]["P2_music_whole_track"] = analyse(
            cap, patch, "P2", t_begin, t_end, beats=beats,
            extra={"audio": summarise_analysis(feed.seen, t_begin, t_end)})
        note(f"  P2 whole track: {json.dumps(REPORT['phases']['P2_music_whole_track'])}")
        pre = analyse(cap, patch, "P2_predrop", drop_t - 8.0, drop_t)
        post = analyse(cap, patch, "P2_postdrop", drop_t, min(drop_t + 12.0, t_end), beats=beats[beats >= drop_t])
        intro = analyse(cap, patch, "P2_intro", t_begin + 1.0, t_begin + 13.0, beats=beats[beats < t_begin + 13.0])
        REPORT["phases"]["P2a_intro_12s"] = intro
        REPORT["phases"]["P2b_last_8s_before_drop"] = pre
        REPORT["phases"]["P2c_first_12s_after_drop"] = post
        note(f"  intro      : level={intro.get('level')} flash={intro.get('flash')}")
        note(f"  pre-drop   : level={pre.get('level')} flash={pre.get('flash')}")
        note(f"  post-drop  : level={post.get('level')} flash={post.get('flash')} beat={post.get('beat_alignment')}")

        # ---- P3: BLACKOUT while the music keeps playing -------------------
        dense = sa.dense_loud_track(bpm=128.0, duration_s=36.0)
        note("== P3/P4: dense 128 BPM; blackout at +8s for 6s, then grand master 0.3 at +20s for 8s")
        marks = {}

        async def controls(t_ref: float):
            await asyncio.sleep(max(0.0, t_ref + 8.0 - time.perf_counter()))
            marks["bo_cmd"] = time.perf_counter()
            rr = await client.post("/api/trigger/blackout")
            marks["bo_ack"] = time.perf_counter()
            marks["bo_status"] = rr.status_code
            await asyncio.sleep(6.0)
            marks["restore_cmd"] = time.perf_counter()
            await client.post("/api/trigger/restore")
            await asyncio.sleep(max(0.0, t_ref + 20.0 - time.perf_counter()))
            marks["gm_cmd"] = time.perf_counter()
            rr = await client.post("/api/master", json={"level": 0.3})
            marks["gm_reply"] = rr.json() if rr.status_code == 200 else rr.status_code
            await asyncio.sleep(8.0)
            marks["gm_release"] = time.perf_counter()
            await client.post("/api/master", json={"level": 1.0})

        t_ref = time.perf_counter()
        ctl = asyncio.create_task(controls(t_ref))
        t_start2 = await feed.play(dense.samples)
        await ctl
        t_end2 = time.perf_counter()
        beats2 = t_start2 + dense.beat_times

        before = analyse(cap, patch, "P3_before", t_ref + 2.0, marks["bo_cmd"], beats=beats2)
        # time for the wire to go fully dark after the command
        w = cap.window(marks["bo_cmd"], marks["restore_cmd"])
        dark_at = None
        lit_after = 0.0
        for uni, (times, frames, _) in w.items():
            for fx in patch:
                if fx["universe"] != uni:
                    continue
                lv = fixture_series(fx, frames)["level"]
                lit = np.where(lv > 0)[0]
                if len(lit):
                    lit_after = max(lit_after, float(times[lit[-1]] - marks["bo_cmd"]))
        held = analyse(cap, patch, "P3_blackout", marks["bo_cmd"] + 1.0, marks["restore_cmd"])
        REPORT["phases"]["P3_blackout_under_music"] = {
            "http_status": marks["bo_status"],
            "ack_ms": round(1000 * (marks["bo_ack"] - marks["bo_cmd"]), 0),
            "last_lit_frame_s_after_command": round(lit_after, 3),
            "level_before": before.get("level"),
            "level_while_latched": held.get("level"),
            "dimmer_channel_max_while_latched": held.get("dimmer_channel_max"),
            "movement_while_latched": held.get("movement"),
            "strobe_shutter_while_latched": held.get("strobe_shutter_values_top"),
            "transport_while_latched": held.get("transport"),
        }
        note(f"  P3 blackout: {json.dumps(REPORT['phases']['P3_blackout_under_music'])}")
        after = analyse(cap, patch, "P3_after", marks["restore_cmd"] + 1.0, marks["gm_cmd"], beats=beats2)
        gm = analyse(cap, patch, "P4_gm", marks["gm_cmd"] + 1.0, marks["gm_release"], beats=beats2)
        REPORT["phases"]["P4_grand_master_0.3"] = {
            "reply": marks["gm_reply"],
            "level_after_restore_full": after.get("level"),
            "dimmer_max_full": after.get("dimmer_channel_max"),
            "level_at_0.3": gm.get("level"),
            "dimmer_max_at_0.3": gm.get("dimmer_channel_max"),
            "movement_at_0.3": gm.get("movement"),
        }
        note(f"  P4 grand master: {json.dumps(REPORT['phases']['P4_grand_master_0.3'])}")
        REPORT["phases"]["P3b_dense_music_reference"] = after

        # ---- P5: the music stops (digital silence on a live feed) ---------
        note("== P5: 40s of silence on a live audio feed")
        t0 = time.perf_counter()
        await feed.play(np.zeros(int(40.0 * SR), dtype=np.float32))
        t1 = time.perf_counter()
        for label, a, b in (("P5a_silence_0_5s", 0, 5), ("P5b_silence_5_20s", 5, 20), ("P5c_silence_20_40s", 20, 40)):
            REPORT["phases"][label] = analyse(cap, patch, label, t0 + a, min(t0 + b, t1))
            ph = REPORT["phases"][label]
            note(f"  {label}: level={ph.get('level')} flash={ph.get('flash')} move={ph.get('movement')}")

    # ---- P6: the audio feed itself is gone --------------------------------
    note("== P6: audio feed disconnected, 25s")
    t0 = time.perf_counter()
    await asyncio.sleep(25.0)
    for label, a, b in (("P6a_feed_lost_0_10s", 0, 10), ("P6b_feed_lost_10_25s", 10, 25)):
        REPORT["phases"][label] = analyse(cap, patch, label, t0 + a, t0 + b)
        ph = REPORT["phases"][label]
        note(f"  {label}: level={ph.get('level')} transport={ph.get('transport')}")
    REPORT["checks"]["health_feed_lost"] = (await client.get("/api/health")).json()
    note(f"  health with feed lost: {json.dumps(REPORT['checks']['health_feed_lost'])}")

    # music returns, then a graceful stop mid-show
    async with AudioFeed(token) as feed:
        back = sa.dense_loud_track(bpm=128.0, duration_s=14.0)
        t0 = time.perf_counter()
        await feed.play(back.samples)
        REPORT["phases"]["P7_music_returns"] = analyse(cap, patch, "P7", t0 + 4.0, time.perf_counter())
        note(f"  P7 music returns: level={REPORT['phases']['P7_music_returns'].get('level')}")

        note("== P8: graceful stop (Ctrl+Break) with the show running")
        t_sig = time.perf_counter()
        took = srv.graceful_stop()
    await asyncio.sleep(2.0)
    tail = [p for p in cap.packets if p[0] >= t_sig]
    last = {}
    for p in tail:
        last[p[1]] = p
    final = {}
    for uni, p in last.items():
        arr = np.frombuffer(p[4], dtype=np.uint8)
        final[int(uni)] = {"nonzero_channels": int((arr != 0).sum()), "max": int(arr.max()) if len(arr) else 0,
                           "sent_s_after_signal": round(p[0] - t_sig, 2)}
    REPORT["phases"]["P8_graceful_stop"] = {
        "exit_code": srv.proc.returncode, "seconds_to_exit": round(took, 1),
        "packets_after_signal": len(tail), "final_frame_per_universe": final,
    }
    note(f"  P8 graceful stop: {json.dumps(REPORT['phases']['P8_graceful_stop'])}")
    await client.aclose()

    # ---- boot 2: power-cycle with a rig already patched -------------------
    note("== BOOT 2: restart with the rig persisted, nobody logged in, no audio")
    t_mark = time.perf_counter()
    srv2 = Server("boot2")
    t_http2 = srv2.wait_http()
    await asyncio.sleep(8.0)
    first = next((p for p in cap.packets if p[0] >= t_mark), None)
    REPORT["checks"]["boot2_seconds_to_http"] = round(t_http2, 1)
    REPORT["checks"]["boot2_seconds_to_first_artnet_frame"] = round(first[0] - srv2.t_spawn, 1) if first else None
    REPORT["phases"]["P9_after_reboot_no_audio"] = analyse(cap, patch, "P9", time.perf_counter() - 5.0, time.perf_counter())
    note(f"  http after {t_http2:.1f}s; first Art-Net frame after {REPORT['checks']['boot2_seconds_to_first_artnet_frame']}s")
    note(f"  P9 after reboot: {json.dumps(REPORT['phases']['P9_after_reboot_no_audio'])}")

    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c2:
        r = await c2.post("/api/auth/login", json={"password": password})
        tok2 = r.json().get("token", "")
        note(f"  login after reboot -> HTTP {r.status_code}")
    async with AudioFeed(tok2) as feed:
        t0 = time.perf_counter()
        await feed.play(sa.dense_loud_track(bpm=128.0, duration_s=10.0).samples)
        note("== P10: hard kill (power loss / crash) mid-show")
        t_kill = time.perf_counter()
        srv2.hard_kill()
    await asyncio.sleep(3.0)
    before_kill = [p for p in cap.packets if t_kill - 0.5 <= p[0] < t_kill + 5]
    after_kill = [p for p in cap.packets if p[0] >= t_kill + 0.1]
    lastp = {}
    for p in before_kill:
        lastp[p[1]] = p
    REPORT["phases"]["P10_hard_kill"] = {
        "packets_after_kill": len(after_kill),
        "last_frame_per_universe": {int(u): {"nonzero_channels": int((np.frombuffer(p[4], dtype=np.uint8) != 0).sum()),
                                              "max": int(np.frombuffer(p[4], dtype=np.uint8).max())}
                                    for u, p in lastp.items()},
    }
    note(f"  P10 hard kill: {json.dumps(REPORT['phases']['P10_hard_kill'])}")

    cap.stop = True
    REPORT["checks"]["capture_anomalies"] = dict(cap.bad)
    REPORT["checks"]["total_packets"] = len(cap.packets)
    (OUT / "report.json").write_text(json.dumps(REPORT, indent=1, default=str))
    note(f"report written to {OUT / 'report.json'}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        import traceback
        traceback.print_exc()
        (OUT / "report.json").write_text(json.dumps(REPORT, indent=1, default=str))
        raise
    finally:
        for srv in SERVERS:
            if srv.proc.poll() is None:
                srv.proc.kill()
