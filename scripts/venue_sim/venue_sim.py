"""
Wire-level venue simulation: the November 2026 audit run.

Boots the REAL backend as a subprocess against a throwaway database, walks the
first-run flow an installer would, patches a rig from a seeded template, plays
synthetic music into the audio WebSocket at real-time pace, and records every
Art-Net packet the box puts on the wire (loopback, so nothing reaches the LAN).
The capture is then decoded against the patch read straight from the database -
independently of the engine's own channel maps.

The capture, decoder and server control now live in the test suite, in
``backend/tests/wire/harness.py``; the standing checks are ``backend/tests/wire``.
This module binds that library to the two command-line arguments so the audit
scripts beside it (``venue_sim2.py`` onwards, which ``import venue_sim as V``) keep
working unchanged.

Usage: python venue_sim.py <backend_dir> <out_dir>
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
import numpy as np
import websockets

BACKEND = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()

sys.path.insert(0, str(BACKEND))
from tests.wire import harness as H  # noqa: E402

CFG = H.WireConfig.create(OUT, backend=BACKEND)
DATA = OUT / "data"
HTTP_PORT, ART_PORT = CFG.http_port, CFG.art_port
BASE, WS, DB_PATH = CFG.base, CFG.ws, CFG.db_path

sa = H.synthetic_audio(BACKEND)
SR = sa.SAMPLE_RATE
CHUNK = sa.CHUNK_SIZE
REPORT: dict = {"phases": {}, "checks": {}, "notes": []}

fixture_series = H.fixture_series
summarise_analysis = H.summarise_analysis


def note(msg: str) -> None:
    print(msg, flush=True)
    REPORT["notes"].append(msg)


def Capture() -> H.Capture:
    return H.Capture(ART_PORT)


SERVERS: list = []


class Server(H.Server):
    def __init__(self, tag: str) -> None:
        super().__init__(CFG, tag)
        SERVERS.append(self)


def read_patch(rig_id: int) -> list:
    return H.read_patch(DB_PATH, rig_id)


def analyse(cap, patch: list, name: str, t0: float, t1: float,
            beats: np.ndarray | None = None, extra: dict | None = None) -> dict:
    """As H.analyse, and keeps the level traces in <out_dir>/cap_<name>.npz."""
    # Only a window that has just closed needs a moment for the capture process to
    # hand over its last packets; an older one is already complete.
    time.sleep(min(0.25, max(0.0, t1 + 0.25 - time.perf_counter())))
    return H.analyse(cap, patch, t0, t1, beats=beats, extra=extra, save_to=OUT / f"cap_{name}.npz")


class AudioFeed(H.AudioFeed):
    def __init__(self, token: str) -> None:
        super().__init__(CFG, token, SR, CHUNK)


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
