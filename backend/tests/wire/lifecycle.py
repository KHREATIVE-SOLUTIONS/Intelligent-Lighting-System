"""
One scripted night on the wire, measured once.

``run_lifecycle`` walks a fresh install through first-run setup, a rig from a venue
template, music with the operator's blackout and grand master, a lost audio feed, a
graceful stop and a reboot. It returns plain measurements; ``test_wire_truth.py``
asserts on them, one test per row of section 4 of
docs/ASSESSMENT_AND_ROADMAP_2026-11.md. Measuring once keeps the tier to about two
minutes of real time however many rows are checked.
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx

from . import harness as H

# Routes an unauthenticated caller must not reach. The auth gate answers before
# routing, so a misspelt path would also return 401 and prove nothing; the run
# checks each of these against the app's own route table once it holds a token.
GUARDED_ROUTES = [
    ("GET", "/api/rigs/", None),
    ("POST", "/api/effects/trigger/blackout", None),
    ("POST", "/api/dmx/channel", {"universe": 0, "channel": 1, "value": 255}),
    ("POST", "/api/effects/strobe", {}),
]

BLACKOUT_AT, RESTORE_AT, MASTER_AT, MASTER_END, MUSIC_S = 8.0, 14.0, 22.0, 30.0, 32.0
GRAND_MASTER = 0.3
# Packets are stamped in the capture process and read in a moment later; wait this
# long after a window closes before analysing it.
SETTLE_S = 0.25


def _now() -> float:
    return time.perf_counter()


async def _probe_unauthenticated(cfg: H.WireConfig) -> dict:
    out: dict = {"routes": {}}
    with httpx.Client(base_url=cfg.base, timeout=10.0) as c:
        health = c.get("/health")
        out["health"] = {"status_code": health.status_code, "body": health.json()}
        for method, path, body in GUARDED_ROUTES:
            out["routes"][f"{method} {path}"] = c.request(method, path, json=body).status_code
        out["auth_status"] = c.get("/api/auth/status").json()
    import websockets
    try:
        async with websockets.connect(f"{cfg.ws}/ws/audio"):
            out["audio_websocket_without_token"] = "accepted"
    except Exception as exc:
        out["audio_websocket_without_token"] = f"refused ({type(exc).__name__})"
    return out


async def run_lifecycle(cfg: H.WireConfig, template: str = "Small Club") -> dict:
    sa = H.synthetic_audio(cfg.backend)
    if cfg.db_path.exists():
        cfg.db_path.unlink()
    m: dict = {"template": template}
    cap = H.Capture(cfg.art_port)
    servers: list = []
    client = None
    try:
        # ---- boot 1: a brand-new install ----------------------------------
        srv = H.Server(cfg, "boot1")
        servers.append(srv)
        m["boot1_seconds_to_http"] = round(srv.wait_http(), 1)
        t0 = _now()
        await asyncio.sleep(5.0)
        m["fresh_install"] = {"seconds_watched": 5.0, "packets": len(cap.since(t0))}
        m["unauthenticated"] = await _probe_unauthenticated(cfg)

        client, token, password = await H.first_run_setup(cfg, srv)
        m["auth_status_after_setup"] = (await client.get("/api/auth/status")).json()
        spec = await client.get("/openapi.json")
        paths = spec.json().get("paths", {}) if spec.status_code == 200 else {}
        m["guarded_routes_exist"] = {
            f"{method} {path}": method.lower() in paths.get(path, {})
            for method, path, _ in GUARDED_ROUTES
        }

        # ---- a rig from a seeded template, live without a restart ----------
        items = (await client.get("/api/templates/")).json().get("items", [])
        m["templates"] = [t.get("name") for t in items]
        t_apply = _now()
        rig_id = await H.rig_from_template(client, template)
        t_active = _now()
        patch = H.read_patch(cfg.db_path, rig_id)
        (cfg.out / "patch.json").write_text(json.dumps(patch, indent=1))
        await asyncio.sleep(3.0)
        first = cap.since(t_apply)
        m["rig_live"] = {
            "fixtures": len(patch),
            "universes_patched": sorted({fx["universe"] for fx in patch}),
            "seconds_from_activate_to_first_frame":
                round(max(0.0, first[0][0] - t_active), 3) if first else None,
            "no_audio_yet": H.analyse(cap, patch, t_active + 1.0, _now()),
        }

        # ---- music, with blackout and grand master under it ----------------
        dense = sa.dense_loud_track(bpm=128.0, duration_s=MUSIC_S)
        async with H.AudioFeed(cfg, token, sa.SAMPLE_RATE, sa.CHUNK_SIZE) as feed:
            marks: dict = {}

            async def controls(t_ref: float) -> None:
                async def at(seconds: float) -> float:
                    await asyncio.sleep(max(0.0, t_ref + seconds - _now()))
                    return _now()

                marks["bo_cmd"] = await at(BLACKOUT_AT)
                r = await client.post("/api/effects/trigger/blackout")
                marks["bo_ack"], marks["bo_status"] = _now(), r.status_code
                marks["rs_cmd"] = await at(RESTORE_AT)
                r = await client.post("/api/effects/trigger/restore")
                marks["rs_status"] = r.status_code
                marks["gm_cmd"] = await at(MASTER_AT)
                r = await client.post("/api/effects/master", json={"level": GRAND_MASTER})
                marks["gm_status"] = r.status_code
                marks["gm_reply"] = r.json() if r.status_code == 200 else r.text[:200]
                marks["gm_end"] = await at(MASTER_END)
                await client.post("/api/effects/master", json={"level": 1.0})

            t_ref = _now()
            ctl = asyncio.create_task(controls(t_ref))
            t_start = await feed.play(dense.samples)
            await ctl
            t_end = _now()
            await asyncio.sleep(SETTLE_S)
            beats = t_start + dense.beat_times

            m["music"] = H.analyse(cap, patch, t_ref, t_end, beats=beats,
                                   extra={"audio": H.summarise_analysis(feed.seen, t_ref, t_end)})
            before = H.analyse(cap, patch, t_ref + 2.0, marks["bo_cmd"], beats=beats)
            last_after_ack, _ = H.last_lit(cap, patch, marks["bo_ack"], marks["rs_cmd"])
            last_after_cmd, peak_late = H.last_lit(cap, patch, marks["bo_cmd"], marks["rs_cmd"])
            held = H.analyse(cap, patch, marks["bo_ack"] + 0.5, marks["rs_cmd"])
            m["blackout"] = {
                "http_status": marks["bo_status"],
                "ack_ms": round(1000 * (marks["bo_ack"] - marks["bo_cmd"]), 1),
                "last_lit_frame_s_after_command": last_after_cmd,
                "last_lit_frame_s_after_ack": last_after_ack,
                "peak_level_later_than_0.5s": peak_late,
                "level_before": before.get("level"),
                "level_while_latched": held.get("level"),
                "dimmer_channel_max_while_latched": held.get("dimmer_channel_max"),
                "movement_while_latched": held.get("movement"),
                "transport_while_latched": held.get("transport"),
                "restore_http_status": marks["rs_status"],
                "first_light_s_after_restore":
                    H.first_lit(cap, patch, marks["rs_cmd"], marks["rs_cmd"] + 5.0),
            }
            full = H.analyse(cap, patch, marks["rs_cmd"] + 1.5, marks["gm_cmd"], beats=beats)
            scaled = H.analyse(cap, patch, marks["gm_cmd"] + 1.0, marks["gm_end"], beats=beats)
            m["grand_master"] = {
                "level_set": GRAND_MASTER, "http_status": marks["gm_status"], "reply": marks["gm_reply"],
                "level_full": full.get("level"), "level_scaled": scaled.get("level"),
                "ratio_rig_mean": round(
                    scaled["level"]["rig_mean"] / max(full["level"]["rig_mean"], 1e-6), 3),
                "movement_scaled": scaled.get("movement"),
            }

        # ---- the audio feed is gone ----------------------------------------
        t_lost = _now()
        await asyncio.sleep(22.0 + SETTLE_S)
        m["feed_lost"] = {
            "settled_10_to_22s": H.analyse(cap, patch, t_lost + 10.0, t_lost + 22.0),
            "health": (await client.get("/api/health")).json(),
        }

        # ---- music returns; then a graceful stop mid-show -------------------
        back = sa.dense_loud_track(bpm=128.0, duration_s=12.0)
        async with H.AudioFeed(cfg, token, sa.SAMPLE_RATE, sa.CHUNK_SIZE) as feed:
            t0 = await feed.play(back.samples)
            t_played = _now()
            await asyncio.sleep(SETTLE_S)
            m["music_returns"] = H.analyse(cap, patch, t0 + 4.0, t_played, beats=t0 + back.beat_times)
            t_sig = _now()
            took = srv.graceful_stop()
        t_exit = t_sig + took
        await asyncio.sleep(2.0)
        tail = cap.since(t_sig)
        final = {}
        for p in tail:
            final[int(p[1])] = {"nonzero_channels": int(sum(1 for b in p[4] if b)),
                                "max": max(p[4]) if p[4] else 0}
        m["graceful_stop"] = {
            "seconds_to_exit": round(took, 2), "exit_code": srv.proc.returncode,
            "packets_after_signal": len(tail),
            "packets_later_than_0.5s_after_exit": sum(1 for p in tail if p[0] > t_exit + 0.5),
            "final_frame_per_universe": final,
        }
        await client.aclose()
        client = None

        # ---- boot 2: power-cycle with the rig persisted, nobody logged in ---
        t_mark = _now()
        srv2 = H.Server(cfg, "boot2")
        servers.append(srv2)
        http2 = srv2.wait_http()
        deadline = _now() + 30.0
        while not cap.since(t_mark) and _now() < deadline:
            await asyncio.sleep(0.1)
        first = cap.since(t_mark)
        await asyncio.sleep(5.0)
        t_seen = _now()
        async with httpx.AsyncClient(base_url=cfg.base, timeout=30.0) as c2:
            login = await c2.post("/api/auth/login", json={"password": password})
        await asyncio.sleep(SETTLE_S)
        m["reboot"] = {
            "seconds_to_http": round(http2, 1),
            "seconds_to_first_artnet_frame": round(first[0][0] - srv2.t_spawn, 1) if first else None,
            "wire": H.analyse(cap, patch, t_seen - 4.0, t_seen),
            "login_http_status": login.status_code,
        }
    finally:
        if client is not None:
            await client.aclose()
        for s in servers:
            s.hard_kill()
        cap.close()
        m["capture_anomalies"] = dict(cap.bad)
        m["total_packets"] = cap.total
        (cfg.out / "wire_truth.json").write_text(json.dumps(m, indent=1, default=str))
    return m
