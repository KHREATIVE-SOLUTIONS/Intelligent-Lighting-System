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

Run from the repository root, with the backend's Python environment:

```bash
python scripts/venue_sim/venue_soak.py backend .wire_out/soak_1h                 # one hour, the default
python scripts/venue_sim/venue_soak.py backend .wire_out/soak_8h --hours 8      # eight hours, the G1 soak
python scripts/venue_sim/venue_soak.py backend .wire_out/soak_smoke --minutes 2 # smoke, for CI
python scripts/venue_sim/venue_soak.py backend --evaluate .wire_out/soak_8h/soak_rows.jsonl --expect-minutes 480
```

The length is `--hours` or `--minutes`: one hour if neither is given, eight hours
(480 minutes) at most.

**Run the one-hour and eight-hour soaks outside market hours.** The soak takes about
a fifth of one core and 550 MB for its whole length, and its frame-gap figures are
only fair on a machine that is otherwise quiet: anything else busy on the box shows
up as gaps that are not the backend's. Start it in the evening or at the weekend and
read the report in the morning. The two-minute smoke can run at any time.

### What it writes

Everything goes to the output directory you name. Use a folder under `.wire_out/`,
which git ignores; do not write into `scripts/venue_sim/reports/`, which is tracked.

| File | What it is |
|---|---|
| `soak_report.md` | One page: the verdict, each check, and the figures below |
| `soak_report.json` | The same, with every minute's row and the limits used |
| `soak_rows.jsonl` | One line a minute, appended as it is measured, so an interrupted run keeps what it saw |
| `server_soak.log`, `data/` | The backend's console log and its throwaway database |

### What it measures

Each minute, from the Art-Net captured on `127.0.0.1`:

- **Frame rate** and **gaps** between frames (99th percentile and longest, including
  a stall that straddles two minutes).
- **Largest channel jump** between two consecutive frames, on any channel and on
  coarse pan and tilt. Reported, not judged: there is no agreed limit yet.
- **Flash rate**: the most whole-rig flashes in any one second, and how many single
  fixtures went over three a second.
- **Blackout and grand master**: in the first minute and every tenth after it the
  soak triggers a three-second blackout and a four-second grand master of 0.3 while
  the music plays. Blackout must be dark within 75 ms of the reply, stay dark, and
  come back; no fixture may exceed the grand master.
- **Errors**: send errors, malformed packets, breaks in the Art-Net sequence, channels
  outside the patch, audio reconnects, error lines in the backend log.
- Memory, threads and CPU of the backend's process tree.

### The verdict

The pass line is G1's: memory flat, 40 fps every minute, no gap between frames over
100 ms; plus no send errors, no channel outside the patch, no malformed packet, no
break in the Art-Net sequence, no more than three whole-rig flashes in a second, and
every blackout and grand-master probe held. The numbers are `SoakLimits` and the
constants at the top of `backend/tests/wire/soak.py`. "Flat" means the last quarter of
the run is within 20 MB or 5% (whichever is larger) of the first quarter after a
ten-minute warm-up.

| Headline | Meaning | Exit code |
|---|---|---|
| `SOAK PASS` | Every check passed. Only a 480-minute pass is the G1 soak; a shorter one says so | 0 |
| `SOAK SMOKE OK` | Nothing measured was wrong, but the run was too short (under 8 minutes) to judge memory | 0 |
| `SOAK FAIL` | A check failed, or the run did not reach its length | 1 |

Needs `psutil`.

## Audit scripts

```bash
python scripts/venue_sim/venue_sim.py <backend_dir> <output_dir>
```

| Script | What it measures |
|---|---|
| `venue_sim.py` | Fresh install, auth probes, music, silence, feed loss, graceful stop, reboot, hard kill. Also binds the library for the others, which `import venue_sim as V`. Re-run on the new library on 2026-11-20; the others were checked by name against it, not re-run. |
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
- The backend is started with `ARTNET_IP=127.0.0.1` and the receiver binds
  `127.0.0.1` only. The harness refuses to start a backend aimed anywhere else
  (broadcast, a LAN address, a host name), the wire tier asserts the backend's own
  report of its target, and the soak fails if that report ever names another address.
- The backend sends Art-Net only. There is no sACN sender in it to capture.
- `<output_dir>` receives the database, backend logs and reports. It is safe to delete.
- Packets are received and time-stamped by a small process of their own
  (`backend/tests/wire/capture_proc.py`). Stamped inside the harness process, arrival
  times also measured the harness's own pauses: the same backend read 129-194 ms worst
  gaps that way and 34 ms with the separate receiver, on the same day and machine.
  The gap figures in the 2026-11-17 reports (104 ms, 112 ms) were taken the old way;
  that they were the same artefact is inferred, not re-measured.
- The old "sequence skips" figure counted the Art-Net sequence wrapping from 255 to 1
  as a skip. `seq_breaks` counts only a frame that did not follow its predecessor.

## Known limits

- Audio enters over the WebSocket, not through server-side device capture.
- One rig: no channels typed `other`, no strobe-typed channel, one universe.
- Synthetic music only.
- "Level" is dimmer times the brightest colour channel, a linear DMX figure. A closed
  shutter with the dimmer up would still count as lit.
- Not yet run on Linux or in CI.

`reports/` holds the outputs from the 2026-11-17 audit run. New runs belong in
`.wire_out/`, not there.
