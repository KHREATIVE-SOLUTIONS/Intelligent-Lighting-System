"""Fifth pass. (A) Does a safety-profile call by itself lose the next drop?
(B) What does the drop look like in manual mode, the one-click UI toggle?"""
import asyncio, json, re, secrets, sys
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

def timeline(seen, t0, t1, key):
    out, prev = [], object()
    for t, d in seen:
        if not (t0 <= t < t1): continue
        l = d.get("lighting")
        if not isinstance(l, dict) or key not in l: continue
        v = str(l[key])
        if v != prev: out.append((round(t - t0, 1), v)); prev = v
    return out

async def boot(tag):
    if V.DB_PATH.exists(): V.DB_PATH.unlink()
    srv = V.Server(tag); srv.wait_http()
    m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", srv.read_log())
    c = httpx.AsyncClient(base_url=V.BASE, timeout=30.0)
    tok = (await c.post("/api/auth/setup", json={"setup_code": m.group(1), "password": secrets.token_urlsafe(12)})).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    rig = (await c.post("/api/templates/2/apply", params={"rig_name": "Sim"})).json()["id"]
    await c.post(f"/api/rigs/{rig}/activate")
    return srv, c, tok, V.read_patch(rig)

async def drop_play(cap, patch, feed, tag):
    track = sa.intro_build_drop_track(bpm=128.0)
    t0 = await feed.play(track.samples); dt = t0 + track.drop_time
    V.analyse(cap, patch, tag, dt, dt + 12.0)
    d = np.load(V.OUT / f"cap_{tag}.npz"); rig, g = d["rig"], d["grid"]
    pk = peaks(rig); tt = g[pk]
    worst = max((int(np.sum((tt >= x) & (tt < x + 1.0))) for x in tt), default=0)
    V.analyse(cap, patch, tag + "_pre", dt - 8.0, dt)
    pre = np.load(V.OUT / f"cap_{tag}_pre.npz")["rig"]
    print(f"{tag}: sections={timeline(feed.seen, t0, t0 + track.duration_s, 'section')}", flush=True)
    print(f"{tag}: 8s before drop mean={pre.mean():.3f} | 12s after: mean={rig.mean():.3f} max={rig.max():.2f} "
          f"peaks>=20%={len(pk)} worst_in_1s={worst}", flush=True)
    print(f"{tag}: first 2s after drop @25ms={[round(float(x), 2) for x in rig[:80]]}", flush=True)

async def main():
    cap = V.Capture()
    dense = sa.dense_loud_track(bpm=128.0, duration_s=14.0)

    srv, c, tok, patch = await boot("sim5a")
    async with V.AudioFeed(tok) as feed:
        await feed.play(dense.samples)
        r = await c.post("/api/effects/safety/profile", json={"profile": "conservative"})
        print("A: POST profile conservative ->", r.status_code, r.json(), flush=True)
        await drop_play(cap, patch, feed, "A_conservative_after_profile_call")
    await c.aclose(); srv.hard_kill(); await asyncio.sleep(1.5)

    srv, c, tok, patch = await boot("sim5b")
    async with V.AudioFeed(tok) as feed:
        await feed.play(dense.samples)
        r = await c.post("/api/effects/auto-mode", json={"enabled": False})
        print("B: autopilot off ->", r.status_code, r.text, flush=True)
        await drop_play(cap, patch, feed, "B_manual_mode_default_posture")
        await c.post("/api/effects/auto-mode", json={"enabled": True})
        await drop_play(cap, patch, feed, "B2_autopilot_back_on")
    await c.aclose(); srv.hard_kill(); cap.stop = True

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        for s in V.SERVERS:
            if s.proc.poll() is None: s.proc.kill()
