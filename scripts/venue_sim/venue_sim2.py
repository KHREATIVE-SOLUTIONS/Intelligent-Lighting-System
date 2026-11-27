"""
Second pass: operator controls under music (the first pass called the wrong
routes), section/movement timelines, the strobe off-switch, and quiet material.

Usage: python venue_sim2.py <backend_dir> <out_dir>
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import sys
import time
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import venue_sim as V  # noqa: E402

sa, SR = V.sa, V.SR
R: dict = {}


def say(k, v):
    R[k] = v
    print(f"{k}: {json.dumps(v, default=str)[:1400]}", flush=True)


def lit_tail(cap, patch, t_cmd, t_until):
    """Seconds after t_cmd at which the last lit frame was seen, and peak level after 0.5s."""
    last, peak_after = 0.0, 0.0
    for uni, (times, frames, _) in cap.window(t_cmd, t_until).items():
        for fx in patch:
            if fx["universe"] != uni:
                continue
            lv = V.fixture_series(fx, frames)["level"]
            lit = np.where(lv > 0)[0]
            if len(lit):
                last = max(last, float(times[lit[-1]] - t_cmd))
            late = lv[times >= t_cmd + 0.5]
            if len(late):
                peak_after = max(peak_after, float(late.max()))
    return round(last, 3), round(peak_after, 3)


def first_lit(cap, patch, t_cmd, t_until):
    first = None
    for uni, (times, frames, _) in cap.window(t_cmd, t_until).items():
        for fx in patch:
            if fx["universe"] != uni:
                continue
            lv = V.fixture_series(fx, frames)["level"]
            lit = np.where(lv > 0.02)[0]
            if len(lit):
                t = float(times[lit[0]] - t_cmd)
                first = t if first is None else min(first, t)
    return None if first is None else round(first, 3)


def timeline(seen, t_start, key):
    """[(seconds into the track, value)] every time lighting[key] changes."""
    out, prev = [], object()
    for t, d in seen:
        lighting = d.get("lighting")
        if not isinstance(lighting, dict) or key not in lighting:
            continue
        v = lighting[key]
        v = json.dumps(v, sort_keys=True)[:80] if isinstance(v, (dict, list)) else str(v)
        if v != prev:
            out.append((round(t - t_start, 1), v))
            prev = v
    return out


def brief(a: dict) -> dict:
    return {k: a.get(k) for k in ("level", "flash", "movement", "beat_alignment", "dimmer_channel_max")}


async def main():
    if V.DB_PATH.exists():
        V.DB_PATH.unlink()
    cap = V.Capture()
    srv = V.Server("sim2")
    srv.wait_http()
    m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", srv.read_log())
    client = httpx.AsyncClient(base_url=V.BASE, timeout=30.0)
    r = await client.post("/api/auth/setup", json={"setup_code": m.group(1), "password": secrets.token_urlsafe(12)})
    r.raise_for_status()
    token = r.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    r = await client.post("/api/templates/2/apply", params={"rig_name": "Sim Venue"})
    rig_id = r.json()["id"]
    (await client.post(f"/api/rigs/{rig_id}/activate")).raise_for_status()
    patch = V.read_patch(rig_id)
    await asyncio.sleep(1.0)

    async with V.AudioFeed(token) as feed:
        # ---- A: intro/build/drop with timelines ---------------------------
        track = sa.intro_build_drop_track(bpm=128.0)
        t_start = await feed.play(track.samples)
        bars = 60.0 / 128.0 * 4
        say("A_truth", {"intro_ends_s": round(8 * bars + sa.LEAD_IN_S, 1), "drop_s": round(track.drop_time, 1),
                         "ends_s": round(track.duration_s, 1)})
        say("A_section_timeline", timeline(feed.seen, t_start, "section"))
        say("A_movement_timeline_first20", timeline(feed.seen, t_start, "movement")[:20])
        say("A_movement_changes_total", len(timeline(feed.seen, t_start, "movement")))
        say("A_section_intensity_timeline", timeline(feed.seen, t_start, "section_intensity")[:30])
        msgs = [d for t, d in feed.seen if t >= t_start]
        say("A_sample_lighting_msg", {k: (v if not isinstance(v, (list, dict)) else f"<{type(v).__name__} len {len(v)}>")
                                       for k, v in (msgs[len(msgs) // 2].get("lighting") or {}).items()})
        say("A_sample_pro_effects", (msgs[len(msgs) // 2].get("lighting") or {}).get("pro_effects"))
        say("A_sample_look_spec", msgs[len(msgs) // 2].get("look_spec"))
        say("A_sample_beat", msgs[len(msgs) // 2].get("beat"))
        say("A_detected_genre", msgs[-1].get("detected_genre"))
        # per-second mean rig level across the whole track
        a = V.analyse(cap, patch, "A", t_start, t_start + track.duration_s)
        d = np.load(V.OUT / "cap_A.npz")
        rig = d["rig"]
        per_s = [round(float(rig[i:i + 40].mean()), 2) for i in range(0, len(rig) - 39, 40)]
        say("A_rig_level_per_second", per_s)
        # pan trace of mover 1 (16-bit, as % of range), 2 samples/second
        mv = next(fx for fx in patch if any(c["type"] == "pan" for c in fx["channels"]))
        times, frames, _ = cap.window(t_start, t_start + track.duration_s)[mv["universe"]]
        s = V.fixture_series(mv, frames)
        pan = s["pan"][0] / 655.35
        tilt = s["tilt"][0] / 655.35
        say("A_mover1_pan_pct_2hz", [round(float(x), 1) for x in pan[::20]])
        say("A_mover1_tilt_pct_2hz", [round(float(x), 1) for x in tilt[::20]])
        jumps = np.abs(np.diff(pan))
        say("A_mover1_pan_jumps_over_3pct_in_one_frame", int((jumps > 3.0).sum()))

        # ---- B: operator controls under dense music -----------------------
        dense = sa.dense_loud_track(bpm=128.0, duration_s=58.0)
        marks = {}

        async def controls(t_ref):
            async def at(s):
                await asyncio.sleep(max(0.0, t_ref + s - time.perf_counter()))
                return time.perf_counter()

            marks["bo1"] = await at(8)
            rr = await client.post("/api/effects/trigger/blackout")
            marks["bo1_http"] = [rr.status_code, rr.text[:120], round(1000 * (time.perf_counter() - marks["bo1"]))]
            marks["rs1"] = await at(14)
            rr = await client.post("/api/effects/trigger/restore")
            marks["rs1_http"] = rr.status_code

            marks["bo2"] = await at(20)
            rr = await client.post("/api/dmx/blackout", json={"fade_time": 0})
            marks["bo2_http"] = [rr.status_code, rr.text[:120], round(1000 * (time.perf_counter() - marks["bo2"]))]
            marks["rs2"] = await at(26)
            rr = await client.post("/api/dmx/restore")
            marks["rs2_http"] = [rr.status_code, rr.text[:120]]

            marks["gm"] = await at(32)
            rr = await client.post("/api/effects/master", json={"level": 0.3})
            marks["gm_http"] = [rr.status_code, rr.text[:160]]
            marks["gm_end"] = await at(40)
            await client.post("/api/effects/master", json={"level": 1.0})

            marks["bo3"] = await at(46)
            rr = await client.post("/api/dmx/blackout", json={"fade_time": 2.0})
            marks["bo3_http"] = [rr.status_code, round(1000 * (time.perf_counter() - marks["bo3"]))]
            marks["rs3"] = await at(52)
            await client.post("/api/dmx/restore")

        t_ref = time.perf_counter()
        ctl = asyncio.create_task(controls(t_ref))
        t2 = await feed.play(dense.samples)
        await ctl
        beats = t2 + dense.beat_times

        ref = V.analyse(cap, patch, "B_ref", t_ref + 2, marks["bo1"], beats=beats)
        say("B_reference_before_controls", brief(ref))
        for tag, bo, rs, http in (("effects_trigger_blackout", "bo1", "rs1", "bo1_http"),
                                  ("dmx_blackout_fade0", "bo2", "rs2", "bo2_http"),
                                  ("dmx_blackout_fade2s", "bo3", "rs3", "bo3_http")):
            last, peak = lit_tail(cap, patch, marks[bo], marks[rs])
            held = V.analyse(cap, patch, f"B_{tag}", marks[bo] + (2.5 if "fade2" in tag else 0.5), marks[rs])
            back = first_lit(cap, patch, marks[rs], marks[rs] + 5.0)
            say(f"B_{tag}", {
                "http": marks[http], "last_lit_frame_s_after_cmd": last, "peak_level_after_0.5s": peak,
                "level_while_latched": held.get("level"), "dimmer_max_while_latched": held.get("dimmer_channel_max"),
                "movement_while_latched": held.get("movement"), "fps_while_latched": held.get("transport"),
                "first_light_s_after_restore": back,
            })
        gm = V.analyse(cap, patch, "B_gm", marks["gm"] + 1.0, marks["gm_end"], beats=beats)
        full = V.analyse(cap, patch, "B_full", marks["rs2"] + 1.5, marks["gm"], beats=beats)
        say("B_grand_master", {"http": marks["gm_http"], "full": brief(full), "at_0.3": brief(gm),
                               "ratio_rig_mean": round(gm["level"]["rig_mean"] / max(full["level"]["rig_mean"], 1e-6), 2),
                               "ratio_fixture_peak": round(gm["level"]["fixture_peak_max"] / max(full["level"]["fixture_peak_max"], 1e-6), 2)})

        # ---- C: the strobe off-switch, then the same drop -----------------
        r = await client.get("/api/effects/safety")
        say("C_safety_before", r.json() if r.status_code == 200 else r.status_code)
        r = await client.post("/api/effects/safety/profile", json={"profile": "no_strobe"})
        say("C_set_no_strobe", [r.status_code, r.text[:300]])
        t3 = await feed.play(track.samples)
        drop_t = t3 + track.drop_time
        post = V.analyse(cap, patch, "C_post", drop_t, drop_t + 12.0, beats=(t3 + track.beat_times)[(t3 + track.beat_times) >= drop_t])
        say("C_no_strobe_first_12s_after_drop", brief(post))
        d = np.load(V.OUT / "cap_C_post.npz")
        say("C_no_strobe_rig_level_first_2.5s", [round(float(x), 2) for x in d["rig"][:100]])
        r = await client.post("/api/effects/safety/profile", json={"profile": "conservative"})
        say("C_back_to_conservative", r.status_code)

        # ---- D: quiet, sparse material ------------------------------------
        quiet = sa.sparse_quiet_track()
        t4 = await feed.play(quiet.samples)
        q = V.analyse(cap, patch, "D_quiet", t4 + 3.0, t4 + quiet.duration_s, beats=t4 + quiet.beat_times)
        say("D_sparse_quiet_track", {"duration_s": round(quiet.duration_s, 1), "bpm": quiet.bpm, **brief(q)})
        say("D_sparse_quiet_sections", timeline(feed.seen, t4, "section"))

        # ---- E: a DJ mix (two records, no gap) ----------------------------
        mix = sa.dj_mix_track(bpm=126.0, outgoing_bars=16, blend_bars=8, incoming_bars=16)
        t5 = await feed.play(mix.samples)
        e = V.analyse(cap, patch, "E_mix", t5 + 2.0, t5 + mix.duration_s, beats=t5 + mix.beat_times)
        say("E_dj_mix", {"duration_s": round(mix.duration_s, 1), **brief(e)})
        say("E_dj_mix_sections", timeline(feed.seen, t5, "section"))
        d = np.load(V.OUT / "cap_E_mix.npz")
        rig = d["rig"]
        say("E_rig_level_per_second", [round(float(rig[i:i + 40].mean()), 2) for i in range(0, len(rig) - 39, 40)])

    await client.aclose()
    srv.hard_kill()
    cap.stop = True
    say("capture_anomalies", dict(cap.bad))
    (V.OUT / "report2.json").write_text(json.dumps(R, indent=1, default=str))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        for s in V.SERVERS:
            if s.proc.poll() is None:
                s.proc.kill()
