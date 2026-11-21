# Wire-level venue simulation

Built for the November 2026 assessment (`docs/ASSESSMENT_AND_ROADMAP_2026-11.md`).

The harness itself now lives in the test suite, in `backend/tests/wire/`, and the
measurements of section 4 of that document are standing tests there (gate G1). What
is left in this directory is the soak command and the one-off audit scripts, which
import the same library.

Everything here starts the real backend as a subprocess against a throwaway SQLite
database, walks first-run setup with the code the backend prints, patches the seeded
"Small Club" template, plays synthetic music into `/ws/audio` at real-time pace, and
records every Art-Net packet on loopback. The capture is decoded against the patch
read straight from the database, so it is independent of the engine's own channel maps.

## The wire tier

```bash
cd backend
pytest tests/wire --wire                      # about five minutes
pytest tests/wire --wire --wire-out ./wire    # keep logs and measurements in ./wire
```

- Skipped unless `--wire` is given or `ILS_WIRE=1` is set: it runs in real time.
- `test_wire_truth.py` runs one scripted night (`lifecycle.py`) and asserts each row
  of section 4 from it. The figures of the run are written to `wire_truth.json`.
- `test_wire_soak.py` is a three-minute soak of tracks played back to back.
- `tests/unit/test_wire_harness.py` checks the decoder and the soak verdict without a
  backend, and runs in the default suite.

## The soak

```bash
python scripts/venue_sim/venue_soak.py backend <out_dir> --hours 8
python scripts/venue_sim/venue_soak.py backend <out_dir> --minutes 30
python scripts/venue_sim/venue_soak.py backend --evaluate <out_dir>/soak_rows.jsonl --expect-minutes 480
```

One line a minute, then a verdict. The pass line is G1's: memory flat, 40 fps every
minute, no gap between frames over 100 ms; plus no send errors, no channel outside
the patch, no malformed packet and no break in the Art-Net sequence. The numbers are
`SoakLimits` in `backend/tests/wire/soak.py`. "Flat" means the last quarter of the run
is within 20 MB or 5% (whichever is larger) of the first quarter after a ten-minute
warm-up.

Each minute is appended to `soak_rows.jsonl` as it is measured, so an interrupted run
keeps what it saw. The exit code is 0 only for a complete run that passed. Needs
`psutil`.

## Audit scripts

```bash
python scripts/venue_sim/venue_sim.py <backend_dir> <output_dir>
```

| Script | What it measures |
|---|---|
| `venue_sim.py` | Fresh install, auth probes, music, silence, feed loss, graceful stop, reboot, hard kill. Also binds the library for the others, which `import venue_sim as V`. |
| `venue_sim2.py` | Blackout (three routes), grand master, section and movement timelines, quiet track, DJ mix. |
| `venue_sim3.py` | The same drop three times in one boot. |
| `venue_sim4.py` | Token-only safety holes: fail-open profile, manual-mode LFO strobe, universe created by a GET, writers under blackout, demo preset over a live rig. |
| `venue_sim5.py`, `venue_sim6.py` | The drop after a safety-profile call, in manual mode, and the control with neither. |
| `venue_sim7.py` | The drop in manual mode, in a boot where autopilot is first shown to catch it. |

These report; they do not assert. The gaps they found (section 5) are not in the wire
tier, which holds only what works.

## How it runs

- Use the backend's Python environment.
- HTTP and Art-Net each take a free loopback port per run, so nothing reaches the
  network, nothing collides with a normal backend on 8000 and 6454, and several
  checkouts can run at once.
- `<output_dir>` receives the database, backend logs and reports. It is safe to delete.
- Packets are received and time-stamped by a small process of their own
  (`backend/tests/wire/capture_proc.py`). Stamped inside the harness process, arrival
  times also measured the harness's own pauses: the same backend read 129-194 ms worst
  gaps that way and 34 ms with the separate receiver. Gap figures in the 2026-11-17
  reports (104 ms, 112 ms) were taken the old way and overstate the backend.
- The old "sequence skips" figure counted the Art-Net sequence wrapping from 255 to 1
  as a skip. `seq_breaks` counts only a frame that did not follow its predecessor.

## Known limits

- Audio enters over the WebSocket, not through server-side device capture.
- One rig: no channels typed `other`, no strobe-typed channel, one universe.
- Synthetic music only.
- "Level" is dimmer times the brightest colour channel, a linear DMX figure. A closed
  shutter with the dimmer up would still count as lit.
- Not yet run on Linux or in CI.

`reports/` holds the outputs from the 2026-11-17 audit run and later soaks.
