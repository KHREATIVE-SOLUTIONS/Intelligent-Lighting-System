"""Control for pass 5A: fresh boot, the same 14 s of dense music, NO profile call, then the drop track."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import venue_sim as V
import venue_sim5 as P5
sa = V.sa

async def main():
    cap = V.Capture()
    srv, c, tok, patch = await P5.boot("sim6")
    async with V.AudioFeed(tok) as feed:
        await feed.play(sa.dense_loud_track(bpm=128.0, duration_s=14.0).samples)
        await P5.drop_play(cap, patch, feed, "CONTROL_no_profile_call")
    await c.aclose(); srv.hard_kill(); cap.stop = True

try:
    asyncio.run(main())
finally:
    for s in V.SERVERS:
        if s.proc.poll() is None: s.proc.kill()
