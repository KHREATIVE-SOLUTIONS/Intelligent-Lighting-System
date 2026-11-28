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
`<rig>_handoff_pack.zip`; 404 for an unknown rig. The printable patch sheet
alone: `GET /api/rigs/{rig_id}/patch-sheet` (see below). Code:
`backend/app/services/rig/handoff_pack.py`.

## What is in it

| File | What it is |
| --- | --- |
| `README.txt` | What each file is, which positions are guessed or missing, every **Fail** check, any missing file and why, and the export notes. Read it first. |
| `patch.csv` | One row per fixture (columns below). |
| `groups.csv` | `group`, `fixture_ids`: every group, its fixture ids in patch order, space separated. |
| `readiness.md` | The readiness report in words, worst first, with the time it was read (UTC). |
| `patch-sheet.html` | The printable patch sheet (below), the same page **Open printable patch sheet** shows. |
| `<rig>_ma2.xml` | grandMA2 fixture layer XML, the same bytes as `.../export/ma2-xml`. |
| `<rig>_ma2_script.txt` | grandMA2 command-line script, the same bytes as `.../export/ma2-macro`. |
| `<rig>.mvr` | MVR for MA3D, Capture or another visualiser, the same bytes as `.../export/mvr`. |
| `<rig>_ma2_starter_presets.txt` | grandMA2 dimmer, colour and beam starter presets ([CONSOLE_EXPORT.md](CONSOLE_EXPORT.md#grandma2-starter-presets)). On by default; `?starter_presets=false` leaves it out. |

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

## Printable patch sheet

Press **Open printable patch sheet** next to **Download handoff pack**. It opens
in a new tab; print it with the browser's Print (landscape, A4 or Letter). The
app fetches the sheet with the operator token and shows it from a blob URL,
because every `/api` route needs the token and a bare link would not carry it.
If the browser blocks the tab, the panel says so.

API: `GET /api/rigs/{rig_id}/patch-sheet` answers `text/html`, one
self-contained page: inline CSS, no script, no external file, every value
HTML-escaped. 404 for an unknown rig. Reads only. Code:
`backend/app/services/rig/patch_sheet.py`.

- **Head:** rig name, when it was generated (UTC), and a summary line: fixture
  count, the universes used, how many positions are guessed or not placed, and
  how many readiness checks Fail and Warn.
- **Patch:** one section per universe, each starting on a new printed page,
  the table header repeated on every page. Sorted by universe, then address,
  then fixture id. Columns: console fixture id, name, profile, mode, channels,
  universe (from 1), address, `universe.address`, position name, X/Y/Z,
  placed (`confirmed`, **GUESSED - check in the room**, or **none - not
  placed**) and groups. A guessed row is shaded and also says so in words, and
  its position name ends "(guessed)".
- **Groups:** every group, its fixture count and console fixture ids.
- **Readiness:** the overall status and each Fail and Warn check in words,
  worst first, with its console fixture ids. OK checks are left out.

`?universe=N` (from 1) prints that universe's table only; the summary, groups
and readiness still describe the whole rig. A universe with no fixtures says
"No fixtures in universe N."; 0 or less is a 422.

The rows are the same ones `patch.csv` holds (`patch_rows()` works both out),
printed in address order instead of patch order.

## When a file is missing

Each console file, and the patch sheet, is written on its own. If a writer stops with an error, that
file is left out and the rest of the pack is still built. README.txt lists it
under **MISSING FILES** and readiness.md under **Missing from this pack**, each
with the error. The readiness report's grandMA2 or MVR export check will
usually show the same failure.

## What it leaves out

- GDTF files the system does not hold are not in the MVR (the README's export
  notes name them), as with the plain MVR download.
- Demo presets have no pack: it is for a database rig, which has a readiness
  report.
