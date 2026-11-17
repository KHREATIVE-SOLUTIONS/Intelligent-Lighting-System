"""Third pass: is drop detection repeatable? Same track three times in one boot,
default (conservative) posture: cold, after dense loud music, and again."""
import asyncio, json, re, secrets, sys
from pathlib import Path
import httpx, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import venue_sim as V
sa = V.sa

def timeline(seen, t0, t1, key):
    out, prev = [], object()
    for t, d in seen:
        if not (t0 <= t < t1): continue
        l = d.get("lighting")
        if not isinstance(l, dict) or key not in l: continue
        v = str(l[key])
        if v != prev:
            out.append((round(t - t0, 1), v)); prev = v
    return out

async def main():
    if V.DB_PATH.exists(): V.DB_PATH.unlink()
    cap = V.Capture(); srv = V.Server("sim3"); srv.wait_http()
    m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", srv.read_log())
    c = httpx.AsyncClient(base_url=V.BASE, timeout=30.0)
    r = await c.post("/api/auth/setup", json={"setup_code": m.group(1), "password": secrets.token_urlsafe(12)})
    tok = r.json()["token"]; c.headers["Authorization"] = f"Bearer {tok}"
    rig = (await c.post("/api/templates/2/apply", params={"rig_name": "Sim"})).json()["id"]
    await c.post(f"/api/rigs/{rig}/activate")
    patch = V.read_patch(rig)
    await asyncio.sleep(6.0)   # same idle gap as the first pass
    track = sa.intro_build_drop_track(bpm=128.0)
    print("truth: build starts 15.3s, drop 30.3s, track ends 54.3s", flush=True)
    async with V.AudioFeed(tok) as feed:
        async def play(tag, tr):
            t0 = await feed.play(tr.samples); t1 = t0 + tr.duration_s
            V.analyse(cap, patch, tag, t0, t1)
            rigl = np.load(V.OUT / f"cap_{tag}.npz")["rig"]
            per5 = [round(float(rigl[i:i+200].mean()), 2) for i in range(0, len(rigl) - 199, 200)]
            print(f"{tag}: sections={timeline(feed.seen, t0, t1, 'section')}", flush=True)
            print(f"{tag}: rig level per 5s={per5}", flush=True)
            if tr.drop_time:
                i = int(tr.drop_time * 40)
                pre, post = rigl[i-320:i].mean(), rigl[i:i+320].mean()
                print(f"{tag}: mean level 8s before drop={pre:.3f}, 8s after={post:.3f}, peak after={rigl[i:i+320].max():.2f}", flush=True)
        await play("1_cold", track)
        await play("dense", sa.dense_loud_track(bpm=128.0, duration_s=30.0))
        await play("2_after_dense", track)
        await play("3_again", track)
    await c.aclose(); srv.hard_kill(); cap.stop = True

try:
    asyncio.run(main())
finally:
    for s in V.SERVERS:
        if s.proc.poll() is None: s.proc.kill()
