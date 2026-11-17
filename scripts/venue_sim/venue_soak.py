"""Mini soak: 12 minutes of continuous music. Watches memory, CPU, frame pacing,
log growth and whether the show's output level drifts."""
import asyncio, json, re, secrets, subprocess, sys, time
from pathlib import Path
import httpx, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import venue_sim as V
sa = V.sa
MINUTES = 9

def rss_mb(pid):
    """RSS, threads and CPU seconds summed over the launcher stub and the real interpreter under it."""
    import psutil
    root = psutil.Process(pid)
    procs = [root] + root.children(recursive=True)
    rss = sum(p.memory_info().rss for p in procs) / 1e6
    threads = sum(p.num_threads() for p in procs)
    cpu = sum(sum(p.cpu_times()[:2]) for p in procs)
    return round(rss, 1), threads, round(cpu, 1)

async def main():
    if V.DB_PATH.exists(): V.DB_PATH.unlink()
    cap = V.Capture(); srv = V.Server("soak"); srv.wait_http()
    m = re.search(r"setup code is\s+([A-Za-z0-9\-]+)", srv.read_log())
    c = httpx.AsyncClient(base_url=V.BASE, timeout=30.0)
    tok = (await c.post("/api/auth/setup", json={"setup_code": m.group(1), "password": secrets.token_urlsafe(12)})).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    rig = (await c.post("/api/templates/2/apply", params={"rig_name": "Soak"})).json()["id"]
    await c.post(f"/api/rigs/{rig}/activate")
    patch = V.read_patch(rig)
    mix = sa.dj_mix_track(bpm=126.0, outgoing_bars=12, blend_bars=8, incoming_bars=12)
    ibd = sa.intro_build_drop_track(bpm=128.0)
    print(f"start rss/threads/cpu_s = {rss_mb(srv.proc.pid)}", flush=True)
    t_begin = time.perf_counter()
    async with V.AudioFeed(tok) as feed:
        async def sampler():
            last_pk = 0
            for minute in range(1, MINUTES + 1):
                t0 = time.perf_counter()
                await asyncio.sleep(60.0)
                t1 = time.perf_counter()
                a = V.analyse(cap, patch, f"soak{minute}", t0, t1)
                tr = a["transport"].get(0, {})
                h = (await c.get("/api/health")).json()
                print(f"min {minute:2d}: rss/threads/cpu_s={rss_mb(srv.proc.pid)} fps={tr.get('fps')} "
                      f"gap_p99={tr.get('gap_ms_p99')} gap_max={tr.get('gap_ms_max')} "
                      f"rig_mean={a['level']['rig_mean']} rig_max={a['level']['rig_max']} dark%={a['level']['pct_time_rig_dark']} "
                      f"rig_flash_worst_1s={a['flash']['rig_worst_flashes_in_1s']} stray={a['nonzero_channels_outside_patch']} "
                      f"send_errors={h.get('dmx_detail', {}).get('send_error_count')} log_kb={srv.log_path.stat().st_size // 1024} "
                      f"ws_msgs={len(feed.seen)}", flush=True)
                feed.seen.clear()
        s = asyncio.create_task(sampler())
        i = 0
        while time.perf_counter() - t_begin < MINUTES * 60 + 2:
            await feed.play((mix if i % 2 == 0 else ibd).samples)
            i += 1
        await s
    print(f"end rss/threads/cpu_s = {rss_mb(srv.proc.pid)}; tracks played={i}; capture anomalies={dict(cap.bad)}", flush=True)
    await c.aclose(); srv.hard_kill(); cap.stop = True

try:
    asyncio.run(main())
finally:
    for s in V.SERVERS:
        if s.proc.poll() is None: s.proc.kill()
