"""Fourth pass: re-verify, on the wire, the safety claims that came from reading code."""
import asyncio, json, re, secrets, sys, time
from pathlib import Path
import httpx, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import venue_sim as V
sa = V.sa

def peaks(rig, prom=0.2):
    out = []
    for i in range(1, len(rig) - 1):
        if rig[i] >= rig[i-1] and rig[i] > rig[i+1]:
            l = rig[max(0, i-8):i+1].min(); r = rig[i:i+9].min()
            if rig[i] - max(l, r) >= prom: out.append(i)
    return out

def flash_stats(tag):
    d = np.load(V.OUT / f"cap_{tag}.npz"); rig, g = d["rig"], d["grid"]
    pk = peaks(rig); tt = g[pk]
    worst = max((int(np.sum((tt >= x) & (tt < x + 1.0))) for x in tt), default=0)
    return {"luminance_peaks_ge_20pct": len(pk), "worst_peaks_in_1s": worst,
            "rig_max": round(float(rig.max()), 2), "rig_mean": round(float(rig.mean()), 3),
            "seconds": round(float(g[-1] - g[0]), 1)}

def say(k, v): print(f"{k}: {json.dumps(v, default=str)[:1100]}", flush=True)

async def main():
    if V.DB_PATH.exists(): V.DB_PATH.unlink()
    cap = V.Capture(); srv = V.Server("sim4"); srv.wait_http()
    m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", srv.read_log())
    c = httpx.AsyncClient(base_url=V.BASE, timeout=30.0)
    tok = (await c.post("/api/auth/setup", json={"setup_code": m.group(1), "password": secrets.token_urlsafe(12)})).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    rig = (await c.post("/api/templates/2/apply", params={"rig_name": "Sim"})).json()["id"]
    await c.post(f"/api/rigs/{rig}/activate")
    patch = V.read_patch(rig)
    track = sa.intro_build_drop_track(bpm=128.0)
    dense = sa.dense_loud_track(bpm=128.0, duration_s=14.0)

    async with V.AudioFeed(tok) as feed:
        await feed.play(dense.samples)   # warm up

        # 1. safety profile with an unrecognised name
        r = await c.post("/api/effects/safety/profile", json={"profile": "off"})
        say("1_profile_off_reply", [r.status_code, r.json()])
        t0 = await feed.play(track.samples); dt = t0 + track.drop_time
        V.analyse(cap, patch, "p1", dt, dt + 12.0)
        say("1_after_drop_with_profile_off", flash_stats("p1"))
        d = np.load(V.OUT / "cap_p1.npz")
        say("1_rig_level_first_2s_25ms", [round(float(x), 2) for x in d["rig"][:80]])
        r = await c.post("/api/effects/safety/profile", json={"profile": "conservative"})
        say("1_back_to_conservative", [r.status_code, r.json()])

        # 2. manual mode + no_strobe + the LFO strobe preset
        await c.post("/api/effects/safety/profile", json={"profile": "no_strobe"})
        r = await c.post("/api/effects/auto-mode", json={"enabled": False})
        say("2_auto_mode_off", [r.status_code, r.text[:80]])
        ta = time.perf_counter()
        await feed.play(dense.samples)
        V.analyse(cap, patch, "p2a", ta + 3, time.perf_counter())
        say("2a_manual_mode_no_strobe_dense_music", flash_stats("p2a"))
        r = await c.post("/api/lfo/quick/strobe")
        say("2_lfo_quick_strobe", [r.status_code, r.text[:80]])
        tb = time.perf_counter()
        await feed.play(dense.samples)
        V.analyse(cap, patch, "p2b", tb + 2, time.perf_counter())
        say("2b_manual_no_strobe_plus_lfo_strobe", flash_stats("p2b"))
        d = np.load(V.OUT / "cap_p2b.npz")
        say("2b_rig_level_1s_25ms", [round(float(x), 2) for x in d["rig"][40:80]])
        rigl = d["rig"]; spec = np.abs(np.fft.rfft(rigl - rigl.mean())); fr = np.fft.rfftfreq(len(rigl), 1/40.0)
        say("2b_dominant_flicker_hz", round(float(fr[int(spec.argmax())]), 2))
        await c.post("/api/lfo/deactivate-all")
        await c.post("/api/effects/auto-mode", json={"enabled": True})
        await c.post("/api/effects/safety/profile", json={"profile": "conservative"})

        # 3. a plain GET on an unpatched universe
        t3 = time.perf_counter()
        r = await c.get("/api/dmx/universe/5")
        await feed.play(dense.samples[: 4 * V.SR])
        w = cap.window(t3, time.perf_counter())
        say("3_after_GET_universe_5", {"http": r.status_code, "universes_on_wire": sorted(int(u) for u in w),
                                         "packets_on_5": int(len(w[5][0])) if 5 in w else 0})

        # 4. blackout latched, then other writers
        await c.post("/api/effects/trigger/blackout")
        await asyncio.sleep(0.5)
        par = next(fx for fx in patch if fx["ftype"] == "led_par")
        t4 = time.perf_counter()
        r = await c.post("/api/dmx/channel", params={"universe": 0, "channel": par["address"], "value": 255})
        await feed.play(dense.samples[: 3 * V.SR])
        a = V.analyse(cap, patch, "p4a", t4, time.perf_counter())
        say("4a_blackout_then_raw_channel_write", {"http": r.status_code, "level": a["level"]})
        t4b = time.perf_counter()
        r = await c.post("/api/dmx/test/pattern", params={"universe": 0, "pattern": "all_on"})
        await feed.play(dense.samples[: 4 * V.SR])
        a = V.analyse(cap, patch, "p4b", t4b + 0.5, time.perf_counter())
        say("4b_blackout_then_test_pattern_all_on", {"http": [r.status_code, r.text[:80]], "level": a["level"],
              "nonzero_channels_outside_patch": a["nonzero_channels_outside_patch"],
              "shutter_values": a.get("strobe_shutter_values_top"),
              "types": {k: (v["min"], v["max"]) for k, v in a["channel_types_on_wire"].items()}})
        await c.post("/api/dmx/test/stop")
        await c.post("/api/effects/trigger/restore")
        await feed.play(dense.samples[: 3 * V.SR])

        # 5. demo preset applied over a live, real rig
        r = await c.get("/api/venues/presets")
        names = list((r.json().get("presets") or r.json()).keys()) if isinstance(r.json(), dict) else r.json()
        say("5_presets", str(names)[:300])
        t5 = time.perf_counter()
        r = await c.post("/api/venues/presets/pro_beam_room/apply")
        await feed.play(dense.samples[: 5 * V.SR])
        w = cap.window(t5 + 1.0, time.perf_counter())
        out = {}
        for u, (times, frames, _) in w.items():
            mask = np.zeros(512, dtype=bool)
            for fx in patch:
                if fx["universe"] == u:
                    mask[fx["address"] - 1: fx["address"] - 1 + fx["channel_count"]] = True
            out[int(u)] = {"packets": int(len(times)),
                           "nonzero_channels_outside_real_patch": int((frames[:, ~mask] != 0).any(axis=0).sum()),
                           "highest_nonzero_channel": int(np.where((frames != 0).any(axis=0))[0].max() + 1) if (frames != 0).any() else 0}
        say("5_demo_preset_over_real_rig", {"http": [r.status_code, r.text[:120]], "wire": out})
        h = (await c.get("/api/health")).json()
        say("5_health_after", h.get("dmx_detail"))
    await c.aclose(); srv.hard_kill(); cap.stop = True

try:
    asyncio.run(main())
finally:
    for s in V.SERVERS:
        if s.proc.poll() is None: s.proc.kill()
