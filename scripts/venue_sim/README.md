# Wire-level venue simulation

Built for the November 2026 assessment (`docs/ASSESSMENT_AND_ROADMAP_2026-11.md`).
These are audit tools, not yet part of the test suite; gate G1 of that roadmap is to
turn them into one.

Each script starts the real backend as a subprocess against a throwaway SQLite
database, walks first-run setup with the code the backend prints, patches the seeded
"Small Club" template, plays synthetic music into `/ws/audio` at real-time pace, and
records every Art-Net packet on loopback. The capture is decoded against the patch
read straight from the database, so it is independent of the engine's own channel maps.

## Running

```bash
python scripts/venue_sim/venue_sim.py <backend_dir> <output_dir>
```

- Use the backend's Python environment.
- `<backend_dir>` must be a tree at GitHub `master` (`da3569a` or later). The scripts
  import `tests/musical/synthetic_audio.py` from it, and the older local `master` lacks
  the routes and tracks they use.
- HTTP is on 127.0.0.1:8031 and Art-Net on 127.0.0.1:16454, so nothing reaches the
  network and nothing collides with a normal backend on 8000 and 6454.
- `<output_dir>` receives the database, backend logs, per-phase captures and a JSON
  report. It is safe to delete.

## Scripts

| Script | What it measures |
|---|---|
| `venue_sim.py` | Fresh install, auth probes, music, silence, feed loss, graceful stop, reboot, hard kill. Also the shared library the others import. |
| `venue_sim2.py` | Blackout (three routes), grand master, section and movement timelines, quiet track, DJ mix. |
| `venue_sim3.py` | The same drop three times in one boot. |
| `venue_sim4.py` | Token-only safety holes: fail-open profile, manual-mode LFO strobe, universe created by a GET, writers under blackout, demo preset over a live rig. |
| `venue_sim5.py`, `venue_sim6.py` | The drop after a safety-profile call, in manual mode, and the control with neither. |
| `venue_sim7.py` | The drop in manual mode, in a boot where autopilot is first shown to catch it. |
| `venue_soak.py` | Memory, threads, CPU, frame pacing and log growth under continuous music. |

## Known limits

- Audio enters over the WebSocket, not through server-side device capture.
- One rig: no channels typed `other`, no strobe-typed channel, one universe.
- "Level" is dimmer times the brightest colour channel, a linear DMX figure. A closed
  shutter with the dimmer up would still count as lit.
- On Windows the environment's `python.exe` is a launcher stub; the real interpreter is
  its child. `venue_soak.py` sums both when it reports memory.

`reports/` holds the outputs from the 2026-11-17 audit run.
