"""Seventh pass: the drop in manual mode, in a context where autopilot is shown to catch it.
Cold drop track in auto (proves the context), then autopilot off and the same track twice."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import venue_sim as V
import venue_sim5 as P5

async def main():
    cap = V.Capture()
    srv, c, tok, patch = await P5.boot("sim7")
    await asyncio.sleep(6.0)
    async with V.AudioFeed(tok) as feed:
        await P5.drop_play(cap, patch, feed, "1_auto_cold")
        r = await c.post("/api/effects/auto-mode", json={"enabled": False})
        print("autopilot off ->", r.status_code, r.text, flush=True)
        await P5.drop_play(cap, patch, feed, "2_manual")
        await P5.drop_play(cap, patch, feed, "3_manual_again")
        r = await c.post("/api/effects/auto-mode", json={"enabled": True})
        await P5.drop_play(cap, patch, feed, "4_auto_again")
    await c.aclose(); srv.hard_kill(); cap.stop = True

try:
    asyncio.run(main())
finally:
    for s in V.SERVERS:
        if s.proc.poll() is None: s.proc.kill()
