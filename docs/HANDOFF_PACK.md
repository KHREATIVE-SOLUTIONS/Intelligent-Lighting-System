# Venue handoff pack

Everything needed to program a venue's rig, in one zip. Press **Download
handoff pack** at the foot of the Readiness panel, or in the MA2 / MVR export
dialog. One press, no confirm step.

- If any readiness check **Fails**, a warning line shows above the button. It
  never blocks the download: the pack says the same in README.txt and
  readiness.md.
- The pack is built from the rig as it is at that moment. It **reads only**:
  nothing in the rig changes, nothing is written to disk on the server, and
  nothing is sent to a device or a console.

API: `GET /api/rigs/{rig_id}/handoff-pack` answers `application/zip`, named
`<rig>_handoff_pack.zip`; 404 for an unknown rig. Code:
`backend/app/services/rig/handoff_pack.py`.

## What is in it

| File | What it is |
| --- | --- |
| `README.txt` | What each file is, which positions are guessed or missing, every **Fail** check, any missing file and why, and the export notes. Read it first. |
| `patch.csv` | One row per fixture (columns below). |
| `groups.csv` | `group`, `fixture_ids`: every group, its fixture ids in patch order, space separated. |
| `readiness.md` | The readiness report in words, worst first, with the time it was read (UTC). |
| `<rig>_ma2.xml` | grandMA2 fixture layer XML, the same bytes as `.../export/ma2-xml`. |
| `<rig>_ma2_script.txt` | grandMA2 command-line script, the same bytes as `.../export/ma2-macro`. |
| `<rig>.mvr` | MVR for MA3D, Capture or another visualiser, the same bytes as `.../export/mvr`. |

The console files come from the same writers as the export routes, with their
defaults (no "(position unconfirmed)" in names, groups from 1, notes on). See
[CONSOLE_EXPORT.md](CONSOLE_EXPORT.md) for what still has to be done on the desk.

### patch.csv columns

| Column | Meaning |
| --- | --- |
| `fixture_id` | The console fixture id: the same number the MA2 and MVR files and `groups.csv` use. |
| `name` | The fixture's name. |
| `type` | Maker and model as a console lists them; `manufacturer` and `model` follow separately. |
| `mode`, `channels` | The DMX mode and its channel count. **Blank when the fixture has no mode** (an imported venue often has none yet; run Set modes). A guessed footprint is never written. |
| `universe`, `address` | Universe **counted from 1**, as the readiness checks and a console count it; address 1-512. |
| `position_name` | Where it hangs: the file's hang position, else the scanned truss it hangs on, else a guess from where it stands ("Front truss", "SL tower"). Blank when it has no position. |
| `x`, `y`, `z` | Metres, in this system's stage axes (X across, Y up, -Z upstage). Blank when it has no position. |
| `position` | `confirmed` (read from a file, or confirmed by a person), `guessed` (a layout guessed it and nobody has checked), or `none` (never placed). |
| `groups` | Every group it is in, the patch-sheet group first, separated by `; `. |
| `rig_fixture_id` | This system's own row id, the id the readiness API names. |

## When a file is missing

Each console file is written on its own. If a writer stops with an error, that
file is left out and the rest of the pack is still built. README.txt lists it
under **MISSING FILES** and readiness.md under **Missing from this pack**, each
with the error. The readiness report's grandMA2 or MVR export check will
usually show the same failure.

## What it leaves out

- GDTF files the system does not hold are not in the MVR (the README's export
  notes name them), as with the plain MVR download.
- Demo presets have no pack: it is for a database rig, which has a readiness
  report.
