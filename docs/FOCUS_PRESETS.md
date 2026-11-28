# Focus presets

Position presets for the moving heads, worked out from where each head is in
the rig and the points the room gives to aim at, and written into the grandMA2
script and the handoff pack. The point is to walk into a venue with the focus
already roughed in, then touch each preset up in the room.

**Status:** backend, a Focus presets panel with each head's pan, tilt and DMX,
target markers in the 3D view, and a visual-only preview of a preset there
(see [In the app](#in-the-app)). The maths is checked against the 3D view's
beam drawing and covered by tests. No preset has been loaded onto a desk, and
nothing has been focused in a real room with these values.

## Computing is read-only

Nothing here sends DMX or moves a light. There is no preview route. The
preview in the app is drawn in the 3D view only, from the table below; it
never goes through the output stage, the engine or Art-Net, so a real head
does not move. Putting a real head on a target would have to go through the
output stage like any other look, and is not built. The only write
is adding or removing a custom target, which touches `rigs.focus_targets` and
nothing else (the rig's `updated_at` is left as it was).

## Endpoints

| Method | Route | What |
| --- | --- | --- |
| GET | `/api/rigs/{id}/focus-presets` | Every target against every moving head, JSON |
| GET | `/api/rigs/{id}/focus-presets.csv` | The same table as a CSV (the one in the handoff pack) |
| POST | `/api/rigs/{id}/focus-presets/targets` | Add a custom target `{name, x, y, z}`, metres. 201, or 422 with the reason |
| DELETE | `/api/rigs/{id}/focus-presets/targets/{target_id}` | Remove one. 404 if the rig has no such target |

An unknown rig is a 404 on every route.

In the JSON each target has `fixtures`, one row per moving head: `fixture_id`
(the console number), `rig_fixture_id` (the rig fixture row's own id, which
the 3D view draws the head by; the console number is given out again when two
fixtures share one or one has none), `name`, `mount`, `reachable`, `reason`,
`pan_deg`, `tilt_deg`, `pan_attr_deg`, `tilt_attr_deg`, `pan_dmx`,
`pan_fine_dmx`, `tilt_dmx`, `tilt_fine_dmx` and `throw_m`. The CSV has no
`rig_fixture_id` column.

The presets also go into:

- `GET /api/rigs/{id}/export/ma2-macro`: with `include=all` (the default) or
  `include=focus`, and `first_preset=N` (default 1). See
  [CONSOLE_EXPORT.md](CONSOLE_EXPORT.md#grandma2-command-line-script).
- The handoff pack: `focus-presets.csv`, and the presets in the script.

Demo presets (`/api/venues/presets/...`) get no focus presets: they have no
stored room to take targets from.

## Targets

Coordinates are the rig's stage axes in metres: X across, Y up from the floor,
-Z upstage (booth end), +Z downstage (crowd end), room centred on the origin.

Five default targets, always in this order, taken from the rig's stored room
(`rigs.room_shell`):

| Key | Name | Where |
| --- | --- | --- |
| `dj_booth` | DJ booth | The raised area marked as the DJ booth, 1.2 m above its deck; else the rig's booth box |
| `dance_floor` | Dance floor centre | The marked dance floor; else the room between the stage front and the downstage wall; else the room's centre. On the floor |
| `audience` | Audience | A line across that same area at 1.7 m, 80% of its width. Heads take places along it in order across X, so the beams fan out without crossing |
| `stage_front` | Stage front | The middle of the downstage edge of the stage, 1.2 m above its deck; else the booth's front edge ("Booth front") |
| `straight_down` | Straight down | The floor under each head |

A target the room cannot place is kept, with `skipped` saying why in words
("Mark the booth's raised area in the room editor"). Its preset slot stays
reserved so preset numbers do not shift when the room is filled in later.

Custom targets come after the defaults, keyed `custom_<id>`. A rig keeps at
most 50; a name is 1 to 60 characters; each coordinate is a number within
500 m; y cannot be below the floor.

## Which heads, and how they are read

- **A moving head** is a fixture whose mode has a pan or tilt channel. If the
  mode has no channel list, its fixture type decides (moving head, spot, wash,
  beam), and it is written 8-bit.
- **16-bit** when the mode has `pan_fine` / `tilt_fine` channels.
- **Hung or standing** is not stored. The tags `floor`, `standing` or
  `floor_standing` mean standing, `hung` means hung; otherwise a head under
  1 m is taken as standing and the rest as hung, and the table and the script
  say it was assumed.
- **Invert**: the `pan_invert` tag (flipped again by the older `is_inverted`
  flag) and the `tilt_invert` tag, as the 3D view reads them.
- **Swap**: the `pan_tilt_swap` tag. Nothing in the system sets it yet.
- **Range**: the profile's `pan_range` and `tilt_range`, else 540 and 270.
- A head with **no position** (tagged unplaced) is left out of every preset
  and listed in `left_out`.

## In the app

**The Focus presets panel** is in the console export, under the handoff
pack: open a rig's Import / Export dialog, or Export in the 3D view. It is
for a database rig only; a demo preset has no room to aim in.

- It lists every target in preset order: its name, Default or Custom, where it
  is (x, y, z in metres, the audience line's two ends, or "the floor under
  each head"), and how many moving heads can reach it ("2 of 3 moving heads
  can reach it"). A default target the room could not place says why
  ("Skipped: ..."). "Show the 2 that cannot" (or "the one") opens the list of
  heads that cannot reach it, each with its reason.
- Moving heads with no position are named in one line, "Left out of every
  preset". A rig with no moving heads says so, and still lists its targets.
- **Add a target:** a name and x, y, z in metres. Each field is checked
  before anything is sent, against the server's own limits (a name of 1 to 60
  characters, numbers within 500 m, y not below the floor, at most 50 custom
  targets). A comma is taken as a decimal point. Anything wrong is a sentence
  under its field; a refusal from the server is shown in its own words.
- **Remove** is on custom targets only, and asks first. The presets after it
  move up one slot in the next script and pack.
- **Show pan, tilt and DMX for each head** opens a table under the target:
  each head's number and name (with hung or standing, and 8 or 16 bit), pan
  and tilt in degrees from the centre of the travel (physical, before invert
  and swap, one decimal), and pan and tilt DMX as the API gives them: one
  number on an 8-bit axis, `coarse / fine` on a 16-bit one, after invert and
  swap. A head that cannot reach shows dashes and its reason. Click Fixture
  to sort by fixture number, up or down. The same values as the CSV.
- **Preview** (on every target with heads to aim) aims the heads in the 3D
  view; see below. It is offered while a 3D view shows the same rig (open it,
  then use Export there); otherwise it is greyed out and says so. While one is
  previewed, its button reads **Stop preview**, and a line at the top of the
  panel names it with its own Stop preview.
- **Download CSV** fetches `focus-presets.csv` (the one in the handoff pack)
  through the app's client, so it carries the operator's token.
- Nothing in the panel moves a light or sends DMX.

**The reach follows the rig.** Every rig write the app's client makes and the
server accepts (a fixture dragged in the 2D plan or the 3D view, turned,
retagged, added or removed, a rig saved, the room edited, a scan applied, a
fixture's QR code scanned) is announced, in this tab and in others
(`announceRigChange` in `utils/focusTargetsSync.ts`, from the client's
response handler in `services/api.ts`). The QR scanner and the RDM import
go through that client too (`rigsApi.scanQr`, `rigsApi.importRdmDevices`);
the RDM import's route, `/rdm/import`, names no rig, so it announces its
rig itself. No component in the app calls the rig API with bare axios or
`fetch` any more. The panel and the 3D markers read the table again 400 ms
after the last one, so a drag's run of saves is one read, and the reach
colours change without turning the markers off and on. Lighting a fixture to
find it, the identify session's keep-alive, the focus targets' own writes and
the stage plot are not counted.

**Previewing a preset in the 3D view.** Preview on a target and every moving
head that can reach it is drawn aimed at it, lit white, using the pan and
tilt the table gives. A head that cannot reach stays at home (pan and tilt at
centre) and dark, and is listed over the view with its reason, under a line
such as "Previewing DJ booth: 2 heads aimed at it. In the 3D view only;
nothing is sent to the lights." with Stop preview. Other fixtures carry on as
the engine's frames draw them.

- **Visual only.** The aim is drawn over what the view read from the engine's
  frame for that head, in the frame loop, and written nowhere: no DMX, no
  Art-Net, no engine call. The lights in the room do not move.
- Previewing a second target switches to it. The preview stops with Stop
  preview, when the 3D view leaves the rig (another rig or another page), and
  when the target is removed or can no longer be placed. Closing the export
  dialog does not stop it: that is how you see it.
- A moved fixture moves the preview too: it reads the same table.
- **Standing heads.** The 3D view draws every moving head hung, so a standing
  head's angles are turned into the hung head's that point its beam the same
  way (pan 180 - p, tilt +-180 - t), exactly, under any yaw or lean. A
  standing head aimed within 45 degrees of the ceiling needs the hung head
  tilted past its 135 each way (180 is straight up), so while it is
  previewed the view lets it go past its travel (`viewTravelLimit`) and it is
  drawn aimed, the hung model turned over in its yoke. When the preview
  stops it eases back into its travel. Live motion keeps the travel.
- Heads are found by `rig_fixture_id`. A row the view has no fixture for is
  listed ("it is not in the 3D view"), never put on another head.

**In the 3D view**, "Show focus targets in 3D" (next to "Show stage plot in
3D") puts a small marker at each target. It is off until turned on, and the
choice is kept per rig in the browser (`localStorage`,
`focusTargets3d:{rigId}`). The table is read only while the markers are on.

| Look | Means |
| --- | --- |
| Cyan ball in a ring | Every moving head can reach it |
| Orange turned cube in a ring | Some heads cannot |
| Red cross | No head can |
| Small grey ball | The rig has no moving heads to aim |

- The audience line is a thin bar between its ends, with its marker in the
  middle. "Straight down" is a different point under every head and has no
  marker; nor does a skipped target. A point on the floor is drawn 10 cm up.
- The markers take no ray hits, so Move fixtures drags straight through them.
- A target added or removed in the panel shows up on, or goes from, the 3D
  view straight away, in this tab and in other tabs of the app
  (`utils/focusTargetsSync.ts`, the same scheme as the stage plot's).

Code: `frontend/src/utils/focusPresets.ts` (reading the table, checking a
typed target, the sentences, the marker look),
`utils/focusPreview.ts` (the preview's aims and how far past its travel a
previewed head may go, pure), `utils/focusTargetsSync.ts`
(target and rig change announcements), `stores/focusPreviewStore.ts` (which
target is previewed, and which rig a 3D view shows),
`components/rig/useFocusPresets.ts`, `components/rig/FocusPresetsPanel.tsx`,
`components/rig/previs/FocusTargetMarkers.tsx`, `useFocusTargets3d.ts`,
`FocusTargets3dToggle.tsx` and `FocusPreviewNotice.tsx`; the frame loop in
`RigVisualizer.tsx` (`previewAims`). Tests: `focusPresets.test.ts`,
`FocusPresetsPanel.test.tsx`, `FocusTargets3d.test.tsx`,
`focusPreview.test.ts` (with standing heads aimed straight up and near the
ceiling against backend `aim()` numbers), `FocusPresetsPreview.test.tsx` and
`focusRigWritePaths.test.tsx` (a QR scan and an RDM import read the table
again, once, only while it is shown) in `frontend/src/__tests__`.

## The maths, in short

`backend/app/services/focus_presets/aim.py`. Pan 0 tilt 0 is straight down
the head's own axis, turned by the rig's rotation as the 3D view turns it
(`hangBeam`); a standing head is turned over, so its tilt 0 points at the
ceiling. Of the solutions inside both travels, the one nearest pan centre is
chosen (ties broken the same way on every machine). A point outside the
travel, or at the head itself, is **unreachable**, with the reason in words.

DMX follows the view's decoding: `0.5 + degrees / range` over the channel,
x65535 for 16-bit, x255 for 8-bit, invert and swap applied.

## In the grandMA2 script

One Position preset per target, at `Preset 2.<first_preset + its place>`:

```
ClearAll
ClearSelection
Fixture 1
Attribute "Pan" At -12.5
Attribute "Tilt" At -38.2
...
Store Preset 2.2
Label Preset 2.2 "Focus Dance floor centre"
ClearAll
```

- Pan and Tilt are **degrees from the centre of each channel's travel**, with
  the rig's invert and swap already applied. Patch these fixtures **without**
  Invert or Swap on the desk, or they are applied twice.
- A skipped target, or one no head can reach, is not stored; a `#` note says
  so at its slot. A head that cannot reach a target is left out of that
  preset, with its reason.
- **Guessed positions are marked.** A head whose position is unconfirmed is
  listed in the notes, and again inside every preset it is in ("position
  guessed (unconfirmed), check this one first"). Its presets are off by as
  much as the guess. Heads whose mount was assumed from height are listed too.
- A rig with no moving heads gets one note and no preset commands.
- Same rig, same bytes: heads are in fixture-id order and nothing reads a clock.

What the operator must still do:

1. **Check the degrees on the desk.** Whether grandMA2 reads `Attribute
   "Pan" At <degrees>` as these degrees depends on its fixture type's pan
   and tilt range. Not checked on a desk.
   Also unchecked: whether a negative value right after `At` (`At -12.5`) is
   taken as an absolute value or as a relative change; and whether
   `Store Preset 2.N`, run with only the last fixture selected, stores every
   fixture with values in the programmer (it depends on the desk's store
   settings). Try one preset on a test show first.
2. **`ClearAll` empties the programmer.** The script uses it before and after
   each preset: do not paste it in the middle of programming.
3. **Pick an empty preset range** with `first_preset`: storing onto an
   existing preset asks or replaces, depending on the desk's settings.
4. **Touch up every preset in the room.** These are computed from the rig's
   positions; a few centimetres of error at the truss is tens of centimetres
   on the floor.

## The CSV

`focus-presets.csv`, one row per target and head:

`target, target_name, fixture_id, name, mount, position, reachable, pan_deg,
tilt_deg, pan_attr_deg, tilt_attr_deg, pan_dmx, pan_fine_dmx, tilt_dmx,
tilt_fine_dmx, target_x, target_y, target_z, throw_m, reason`

`mount` is `hung` or `standing`, with ` (assumed)` when read from height.
`position` is `guessed` or `confirmed`. A skipped target is one row with its
reason and the head columns blank.

## Tests

- `backend/tests/unit/test_focus_presets_aim.py`: the maths, hung and
  standing, invert, swap, range limits, unreachable, 8 and 16 bit, and random
  points landing on target in the view's own beam model.
- `backend/tests/unit/test_focus_presets_table.py`: default and custom
  targets, which rows are movers and how their tags are read, the CSV, the
  MA2 presets, and row order not changing the bytes.
- `backend/tests/unit/test_focus_presets_rig_fixture_id.py`: every head's row
  names its rig fixture, also when its console number was given out again,
  and the CSV has no new column.
- `backend/tests/integration/test_api_focus_presets.py`: the routes and their
  404s and 422s, reading changes nothing, adding a target writes only
  `focus_targets`, the `ma2-macro` export and the handoff pack.

## What is left

- Not loaded onto a grandMA2 and not focused in a real room.
- The preview is in the 3D view only. Putting a real head on a target (a
  live preview through the output stage, with the operator's say-so) is not
  built.
- The preview draws a standing head on the view's hung head, turned past its
  travel when it is aimed near the ceiling: the beam is right, the housing
  is drawn hanging. The view does not yet stand a mover on its base.
- The frontend tests for this work (`focusPreview.test.ts`,
  `FocusPresetsPreview.test.tsx`, `focusRigWritePaths.test.tsx`) have not
  been run with vitest: it was refused in the worktrees they were written in.
  `npx tsc --noEmit` passes them (only the 13 older errors elsewhere), and
  the ceiling maths was checked against backend `aim()` in Python over the
  whole ceiling cone. Run them before merging.
- A rig write made outside the app (a script against the API, the database
  edited) is not announced; reopen the panel or the view.
- The QR scanner and RDM discovery dialogs are not opened from anywhere in
  the app yet. The RDM import also sends `{device_uids, rig_id}` (string
  UIDs) where the route's signature takes a bare list of integer device ids
  as the body and `rig_id` as a query parameter, so by that signature it
  would be refused (422); not tried against a server.
- Mount is guessed from height when not tagged; there is no column for it.
- grandMA3 is not targeted.
