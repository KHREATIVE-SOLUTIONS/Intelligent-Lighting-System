# Room builder from a phone scan

Status: **two slices. The scan reader and the API are built and tested against
rooms made in code; no file from a real phone has been read by it yet.** Treat
the first real scan as a test of the reader, not of the room. The second slice
adds correcting a suggestion by dragging the fixture in the 3D view, and
undoing the moves a scan made. The frontend unit tests pass and the bundle
builds, but **nobody has yet dragged a fixture in a browser**: the drag's
geometry is tested, the pointer handling in the canvas is not (see What is
left).

The slice called 4 adds **rooms that are not boxes, truss at an angle and rings
of truss**: the reader finds them, the suggestion lays rows along them, the 3D
view draws them and a drag snaps to them (see "What slice 4 built"). Its
backend tests pass. Its frontend tests (273) and the bundle build pass too, but none of it has
been seen in a browser (see What is left).

Everything here is free and local. Nothing is uploaded anywhere but this
system's own backend, and no outside service or model is called.

## What it is for

A rig laid out on a stage template has every fixture at a guess, in a room the
3D view invents from the stage size. A phone can scan the real room in a couple
of minutes. This reads that scan and suggests:

- the **room shell**: floor, ceiling and walls. A box, or for a room that does
  not fill its box (an L, a cut corner) the outline of its floor;
- **raised areas**: a stage, risers, a DJ booth or counter;
- **overhead lines and rings**: trusses and lighting bars at whatever heading
  they run, and rings of truss, with the height they hang at;
- **where the rig's unconfirmed fixtures should move** to agree with all that.

Every part of it is a **suggestion**. The operator sees a preview first, and
nothing is stored until they apply it. Applied, the room is scenery for the 3D
view, and the moved fixtures are still tagged as unconfirmed guesses:
flash-and-tap (Identify Lights, `FLASH_AND_TAP.md`) and dragging are still what
turn a guess into a position.

Nothing here reaches a device. The engine never reads the room shell, and a
fixture's stored position changes without any DMX being sent.

## Scanning the room

| App | Export | Read as |
| --- | --- | --- |
| Polycam, Scaniverse, 3D Scanner App | **OBJ** (best) or PLY | a mesh |
| Any LiDAR or photogrammetry app | PLY, ASCII or binary, with or without faces | a mesh or a point cloud |
| Apple RoomPlan apps | the RoomPlan **JSON**, or a USDZ that carries it | walls and objects as boxes |
| Anything writing USD | USDA, or a USDZ whose layer is **text** | a mesh, with the units and up axis the file states |

A USDZ whose only layer is binary USD (`.usdc`) **cannot be read**: reading it
needs Pixar's USD library, which is not a dependency of this project. The
server says so and names the fix: export OBJ from Polycam or Scaniverse instead.

Tips that make the reader's job easier: scan the whole room including the
ceiling, keep doors shut where you can, and export at medium detail (the reader
samples the surface, so a 2 GB mesh tells it no more than a 50 MB one). Uploads
over **200 MB** are refused with a message saying to export at a lower detail.

## Using it

Rig editor toolbar, **Room Scan**:

1. Choose the scan file. The server reads it and answers with a preview.
   Nothing is written.
2. Read the preview: the room's size, each raised area and overhead line, how
   the scan was read (units, up axis, which end was taken as upstage), any
   warnings, and a table of the fixtures that would move, from where to where
   and why.
3. If the room came out wrong, correct the guess and the preview is read again:
   **Units** (metres, centimetres, millimetres), **Up axis** (Y or Z), **Turn
   the room** in quarter turns when the wrong wall was taken as upstage.
4. **Store the room** (and, if ticked, move the listed fixtures). Untick the box
   to store the room and leave every fixture where it is.
5. **See it in the 3D view.** Then run Identify Lights: the moved fixtures are
   still unconfirmed.

### Correcting a suggestion by dragging

A moved fixture is still a guess (amber in the 3D view). To put one where it
really is, open the rig's 3D view and switch on **Move fixtures** in the
header (stored rigs only; the demo rig has no stored positions to change):

- **Press a fixture** to select it. Every fixture gets a faint sphere to grab:
  amber for a guess, grey for a confirmed position, blue for the selected one.
- **Drag** moves it along the floor plan at the height it hangs at. The camera
  holds still while a fixture is held. A readout shows where it would go.
- **Shift-drag** moves it straight up and down where it stands.
- **Arrow keys** nudge the selected fixture 0.1 m across or up and down stage,
  **Page Up / Page Down** change its height; with Shift, 1 m at a time.
- With a scanned room on the rig, a drag **snaps** to the nearest scanned truss
  line (at any heading), ring of truss or raised-area edge within 0.4 m on the
  plan, among those within 1.5 m of the fixture's height. On a ring it goes to
  the nearest point of the circle, straight out from or in towards the
  centre; a fixture dropped at the very centre is left alone. On a truss line
  or ring the fixture also takes its hanging height; on a stage or riser edge
  it keeps its own. The readout names what it is on. The **Snap**
  button turns this off; holding **Alt** lets go of it for one drag. A height
  drag does not snap.
- **Esc** cancels a drag. A press that travels less than 5 pixels on screen
  only selects: it never snaps, moves or confirms the fixture.
- **Releasing saves** through `PUT .../fixtures/{id}/position`, which confirms
  the position: the amber marker goes, and a later room scan, row fit or undo
  leaves the fixture alone. If the save fails the fixture is put back where it
  was and the reason is shown.

A position is held to within 2 m of the larger of the stage and the scanned
room, and between the floor and 2 m over the top. The view applies the same
limit the server does; the server has the last word.

Dragging in the 2D layout view is unchanged: it saves through batch-update and
does **not** confirm a position.

### Undoing the moves a scan made

Applying a scan records where each fixture it moved stood before. While that
record holds moves, **Undo room scan moves (n)** is shown in the Room Scan
dialog and in the 3D view's header. It asks once, then puts those fixtures
back. A fixture a person has tapped, confirmed, dragged or moved since the scan
is **left where it is** and named in the answer with the reason ("Left alone:
Spot 1 (...)"). The stored room stays.

**Remove the stored room** takes the room off the rig again. When the scan
moved fixtures it asks first: remove the room and put them back, or remove the
room only. Removing the room only leaves the undo available afterwards.

## The API

All routes need the operator login, like every other `/api` route.

### `POST /api/rigs/{rig_id}/room-scan`

Multipart upload, field `file`. Query parameters:

| Parameter | Values | Meaning |
| --- | --- | --- |
| `apply` | `false` (default), `true` | `false` previews and writes nothing; `true` stores the room and moves fixtures |
| `move_fixtures` | `true` (default), `false` | with `apply`: also move the unconfirmed fixtures as previewed |
| `units` | `auto`, `m`, `cm`, `mm` | the scan's units, when the guess is wrong |
| `up_axis` | `auto`, `y`, `z` | the scan's up axis, when the guess is wrong |
| `rotate` | `0`, `90`, `180`, `270` | a further turn clockwise seen from above |

The file is sent for the preview and sent again to apply. The server keeps
nothing between the two requests, and the reader is deterministic (its random
sampling is seeded), so the same file with the same options gives the same
shell: what is applied is what was previewed.

The answer, for both:

- `room_shell`: the suggested shell (below). `replaces_existing_shell` says
  whether the rig already has one.
- `summary`: width, depth, height, counts (`raised_areas`, `overhead_lines`,
  `overhead_rings`, and `walls`: 4 for a box, else the number of outline
  segments), hanging heights, units, up axis.
- `assumptions`: each guess the reader made, in words, with how to override it.
- `warnings`: what looks wrong (a 500 m high room, a sparse scan, missing
  walls, a row longer than the truss it was put under).
- `fixtures`: `total`, `unconfirmed`, `would_move`, and `moves`: each with
  `rig_fixture_id`, `name`, `group`, `from`, `to`, `reason` and
  `suggested: true`.
- `applied`: `null` for a preview. After apply: `room_shell_stored`,
  `fixtures_moved`, `fixtures_still_unconfirmed` and a message.

Refusals, each with a `detail` that says what to do:

| Status | When |
| --- | --- |
| 400 | the file is not a scan this reads (binary-only USDZ: "export OBJ from Polycam or Scaniverse"), is cut short, has no surface, or is not a room at any plausible units; or `rotate` is not a quarter turn |
| 404 | no such rig |
| 409 | `apply` would move fixtures while a locate walkthrough is running on the rig. Finish or end it first. A preview, and an apply with `move_fixtures=false`, are still answered |
| 413 | the file is over 200 MB |
| 422 | `units` or `up_axis` is not one of the values above |

### `DELETE /api/rigs/{rig_id}/room-shell`

Takes the stored room off the rig. Fixtures are left where they are unless
`restore_fixtures=true`, which also puts back the ones the scan moved. Answers
`rig_id`, `removed`, `undo_available` and, when asked to restore,
`fixtures_restored`, `fixtures_skipped`, `skipped_fixtures` and a `message`.

### `POST /api/rigs/{rig_id}/room-scan/undo`

Puts the fixtures that scans have moved since the last undo back where they
stood before the first of them, and spends the record. The stored room stays.
`GET` on the same path previews what would be restored and skipped, and writes
nothing.
Answers `restored`, `skipped`, `restored_fixtures`, `skipped_fixtures` (each
with `rig_fixture_id`, `name` and a `reason`) and a `message`. A fixture a
person has placed, confirmed or moved since is skipped, never overwritten.
409 while a locate walkthrough is running on the rig. The rig itself carries
the record as read-only `room_scan_undo`, which is how the UI knows there is
something to undo.

### `PUT /api/rigs/{rig_id}/fixtures/{fixture_id}/position`

What a drag in the 3D view saves through. Body: `position_x`, `position_z` and
optionally `position_y` (left out, the height is kept). The position is held
inside the limits above, rounded to the millimetre, and **confirmed**: the
tags become `position_source:tap` with no `position_unconfirmed`, as a tap in
flash-and-tap leaves them. Answers the fixture as stored. 404 for an unknown
rig or fixture, 409 while a locate walkthrough is running. No DMX is sent.

### Where the shell is read

`GET /api/rigs/{id}` and the rig list carry `room_shell` (null when there is
none). It is read-only there: a rig update neither sets nor clears it.

## The shell

Stored in `rigs.room_shell` (JSON, migration `006_rig_room_shell`; additive and
nullable, and applied at startup like the other migrations). Axes are the
rig's: metres, origin at the centre of the floor, X across, Y up, -Z upstage.

```
source: "scan", suggested: true, basis: "Suggested from a room scan (...)"
room:          { width, depth, height, suggested, basis,
                 outline: [ { x, z }, ... ] }     only when it is not a box
risers:        [ { center_x, center_z, width, depth, height, base_height,
                   name, kind: "stage" | "riser" | "booth", suggested, basis } ]
truss_lines:   [ { name, x1, z1, x2, z2, height, top, length, across,
                   axis: "x" | "z" | "angled", heading_deg, suggested, basis } ]
truss_rings:   [ { name, center_x, center_z, radius, height, top, across,
                   suggested, basis } ]
hanging_bands: [ { height, top, lines, rings, suggested, basis } ]
scan:          { file, format, points, triangles, point_cloud, units, up_axis,
                 wall_turn_deg, quarter_turns, walls_found, ... }
```

`room.outline` is the corners of the floor in order, clockwise seen from above,
the last joined back to the first; the walls are the segments between them, and
`width` and `depth` are then the box round the outline. A box room carries no
outline. `heading_deg` is degrees clockwise from across the room (0 across, 90
upstage to downstage). A ring's `radius` is to the middle of the truss and its
`height` is its underside, as a line's is.

A shell stored before slice 4 has no `outline`, `truss_rings`, `heading_deg` or
`rings`, and needs no migration: every reader goes by a line's two ends, and
takes a missing outline for a box and missing rings for none.

It travels under the same name as a demo preset's `room_shell`, which has other
keys (dome, balcony, LED walls). The 3D view draws whichever keys are there.

What a raised area *is* is guessed from its size alone, and its `basis` says
so: 6 m2 or more is a `stage`; smaller and at least 0.6 m high is a `booth`
("Booth or counter": a bar counter looks the same to a scan as a DJ booth);
smaller and lower is a `riser`.

## How the scan is read

`backend/app/services/room_scan/`: `mesh.py` and `usd.py` parse the file,
`extract.py` finds the room, `suggest.py` moves the guesses. In order:

1. **Points.** A mesh is sampled by area into points with normals; a point
   cloud is used as it is.
2. **Up axis.** From the file where it says (USD, RoomPlan), else guessed
   between Y and Z: the axis with most surface at its two ends.
3. **Units.** From the file where it says, else from the floor-to-ceiling
   height: under 100 is metres, under 1800 centimetres, else millimetres.
4. **Floor and ceiling.** The densest level near the bottom and near the top.
5. **Walls.** The scan is turned until its walls line up with the axes, then
   each wall is the densest plane near its side, so a scan that leaks through a
   doorway keeps its walls. That gives the room's box.
   Where the scan fills less than 95% of that box the room is not one: the
   plan is cut into cells, the edge of the cells the scan has anything in is
   traced and straightened, and each straight run is moved onto the wall the
   scan shows along it. An outline of 4 to 12 corners is kept. One that is not
   clear enough (too little floor scanned, an edge that cannot be followed, a
   scan that stops short of a corner) is **drawn as a box, with a warning**
   saying why.
6. **Raised areas.** Level patches 0.12 m to 2.2 m above the floor, at least
   1.5 m2.
7. **Overhead lines and rings.** Long thin things hanging clear of the walls
   (of the outline's walls, where there is one) in the upper room, grouped into
   hanging heights. Each patch is measured along its own long axis, so a truss
   at any heading is a line. A patch that keeps to one circle (at least 0.75 m
   in radius) for 315 degrees of the way round is a ring; a square frame of
   truss strays too far from a circle to be one.
8. **Upstage.** The side with the largest raised area becomes upstage (-Z).
   With no raised area the scan's own heading is kept. Turns are rotations,
   never a mirror, so stage left stays stage left.

## Which fixtures move, and which never do

Only a fixture tagged `position_source:template` **and** `position_unconfirmed`
is moved: a template guess nobody has confirmed. These are never moved:

| Position | Tags | Why |
| --- | --- | --- |
| Tapped in flash-and-tap, or dragged | `position_source:tap` | a person pointed at it |
| Confirmed | `position_source:confirmed` | a person agreed with it |
| Measured in a file (MVR and the like) | `position_source:mvr`, ... | the file knows more than a scan |
| Fitted between two tapped ends | `position_source:row_fit` | it follows two taps, even though it is unconfirmed |

A row (a group, or ungrouped fixtures at one height and depth) moves as one
piece, so it keeps its spacing and stays a straight line for flash-and-tap's
row fit:

- **Overhead rows** (1.9 m and up) go to the nearest thing found overhead.
  Under a line that runs across the room (within 2 degrees): its height, its
  depth, and along it far enough to hang under it, as one piece. With no line
  or ring, to the lowest hanging height found; with nothing found overhead,
  only down to hang under the ceiling.
- **A row nearest a line at any other heading, or a ring,** cannot be slid
  under it, so it is **laid out along it, spaced evenly in address order**.
  Along a line the row keeps the end its first address was at; round a ring
  the first address is upstage and the rest follow clockwise seen from above.
  Fixtures of the group that a scan may not move keep their places in the
  count and stay where they are. A row round a ring is no longer straight, so
  flash-and-tap's row fit does not apply to it.
- **Floor rows standing where the scan found a stage** go up onto it and in
  from its edges.
- **Every row** comes inside the walls.

A moved fixture keeps `position_source:template` and `position_unconfirmed` and
gains `position_hint:room_scan`. Applying the same scan again moves nothing.

## In the 3D view

For a rig with a scanned room (`room_shell.source == "scan"`):

- the walls and the ceiling are the scan's, not worked out from the stage size
  (`buildVenue`'s `room` argument). A wall still moves out for a fixture patched
  beyond it. The rig's `stage_width/depth/height` are not changed;
- **a room with an outline** has its floor and ceiling cut to the outline and
  one wall standing on each segment of it, in place of the view's box
  (`OutlineRoom` in `RoomShellView.tsx`; `ClubRoom` is told to leave its own
  floor, walls and ceiling out). As with the box, a wall is drawn only while
  the camera is on the room's side of it, so a camera outside looks in;
- raised areas are drawn as boxes and overhead lines as plain bars, each
  turned to the heading it runs at. A line straight across the room is not
  drawn where the view already hangs a truss over the fixtures under it;
- **rings of truss** are drawn as plain flat rings at their own height;
- **fixtures on a line that does not run across the room, or on a ring,** hang
  from it (within 0.3 m of it on the plan and 0.6 m of its height) and get no
  truss of the view's own. The view's truss only runs across the room, and
  would otherwise put a short stub of it over every fixture round a ring.
  This is the one thing an old stored room draws differently: one with a line
  running upstage to downstage used to get those stubs over its fixtures;
- the booth, speaker stacks, square dance floor, crowd, and the bar counter and
  door on the rear wall that the view otherwise invents are **left out**: they
  would stand through the stage and risers the scan found, or claim things about
  a real wall that nobody saw. The ceiling's beams and duct are still the
  view's own.

## What slice 4 built

- **Reader** (`extract.py`): the floor outline of a room that is not a box,
  overhead lines at any heading, and rings of truss. A box room with truss
  square to it gives the shell it always did.
- **Suggestion** (`suggest.py`): rows laid evenly, in address order, along an
  angled line or round a ring. The answer's `summary` counts rings and walls.
- **3D view** (`roomShell.ts`, `RoomShellView.tsx`, `layout.ts`,
  `ClubRoom.tsx`): the outline's floor, walls and ceiling; bars at their
  heading; rings; fixtures hung from angled lines and rings.
- **Drag** (`fixtureDrag.ts`): snapping to angled lines and to rings.
- **Dialog** (`utils/roomScan.ts`): the preview says "running at 30 degrees to
  the room", lists each ring with how far across it is, and says when the room
  is not a box and how many walls its outline has.

## What the tests cover

All scans are built in code (`backend/tests/unit/room_scan_meshes.py`); there
are no binary fixtures in the repository.

- `backend/tests/unit/test_room_scan.py`: the parsers (OBJ, PLY in three
  encodings, USDA, USDZ, RoomPlan JSON), the same room recovered whatever the
  units, axes and heading, a point cloud with no normals, a scan leaking through
  a doorway, refusals and their wording, and which rows move where.
- `backend/tests/integration/test_api_room_scan.py`: preview writes nothing;
  apply stores the shell and it comes back on the rig and in the rig list; only
  template guesses move, a row at a time, and stay guesses; tapped, confirmed,
  measured and row-fitted positions do not move; a second scan moves nothing; a
  DJ booth is suggested where there is one; the overrides; binary USDZ and other
  refusals; the size limit; the locate-walkthrough conflict; removal; a rig
  update cannot write the shell; the route is behind the login.
- `frontend/src/__tests__/roomScan.test.ts`: the scanned room's walls, ceiling,
  risers and overhead bars in the view, request parameters, and the dialog's
  wording.
- `backend/tests/unit/test_room_scan_undo.py` and
  `backend/tests/integration/test_api_position_drag_and_scan_undo.py`: the undo
  record, an undo that skips what a person placed later, removal with and
  without restoring, and the position route confirming a dragged fixture.
- `frontend/src/__tests__/fixtureDrag.test.ts`: the drag geometry with no
  canvas. A pointer ray onto the plane at the fixture's height and the rays
  that miss; the grip taken on the first move so a fixture does not jump; the
  height drag; which lines a scanned room offers; the snap radius, the height
  window, truss over edge on a tie, the truss's height taken and an edge's
  not; the limits; the drawn lift taken off again; a click next to a truss
  line not counting as a move; keyboard nudges.
- `frontend/src/__tests__/RoomScanUndoButton.test.tsx`: nothing drawn with no
  moves to undo; the first click asks and sends nothing; confirming calls the
  undo route and hands on the answer, skipped fixtures named; a refusal is
  shown with another go offered.

- `backend/tests/unit/test_room_scan_shapes.py`: an L-shaped room, a cut
  corner, a truss at 30 degrees and a 4 m ring, all built in code: the outline
  and its walls, the box drawn with a warning when a scan stops short of a
  corner, the line's heading, the ring, and rows laid along each in address
  order with placed fixtures keeping their places.
- `frontend/src/__tests__/roomShapes.test.ts` (**written and type-checked, not
  yet run**): an angled bar lying on its line whichever end it is written
  from; a ring's geometry; fixtures clamped to a line or ring with no truss of
  the view's own; which outlines are taken for one; a wall per segment facing
  into the room, for corners in either order; the floor cut to the outline;
  snapping onto an angled line and a ring, and when a ring is left alone; a
  shell stored before all this drawing and snapping as it did; the dialog's
  wording.

## What is left

- **Slice 4's frontend checks have not been run.** The session that wrote it
  could type-check (`npx tsc --noEmit` reports nothing in the files it
  touched) but could not run vitest or the build. Run
  `cd frontend; npx vitest run --passWithNoTests; npm run build` before
  relying on it. The backend tests for it ran under the system Python, not
  the project venv.
- **Nothing of slice 4 has been seen in a browser**: an outlined room's walls
  from each camera, an angled bar, a ring, and a drag snapping to either.
- **An outlined room is still a box to everything but its own walls.** Beams
  end on the box round the outline (`beamRoom`), so a beam aimed into the
  notch of an L carries on through the inner wall. Drag limits and the camera
  presets go by the box too. The outline's ceiling is plain: it has none of
  the beams and duct the box ceiling has. And where the box's walls move out
  for a fixture patched beyond them, the outline's walls stay where the scan
  put them.
- **Part of a ring is not a ring.** An arc of truss under 315 degrees, an
  oval and a square frame are read as lines or not at all.
- **One outline, no holes.** A pillar or an island wall inside the room is not
  part of the outline, and walls are straight: a curved wall comes out as a
  few straight ones or as the box.
- **The drag has not been tried in a browser.** `FixtureDragLayer.tsx` (pointer
  events, the camera held still, the marker and readout) and its wiring in
  `RigVisualizer.tsx` type-check and build, and the geometry under them is
  tested, but nobody has picked a fixture up on screen. Check in a real or
  headless browser against a running backend (`3D_PREVIEW.md` says how) before
  a venue: grab radius, the Top camera, and a drag begun over another fixture.
- **Touch.** The drag uses pointer events, so a finger should work, but Shift
  and Alt have no touch equivalent: on a tablet there is no height drag and no
  way to let go of the snap for one drag other than the Snap button.
- **One fixture at a time.** No multi-select, no dragging a whole row, and no
  rotating a fixture in the 3D view.
- **One undo, all the way back.** The record gathers the moves of every scan
  applied since the last undo, so an undo puts a fixture back where it stood
  before the first of them; one scan out of several cannot be undone on its
  own. The record is spent by an undo whether or not anything was skipped, and
  an undo cannot itself be undone. A 3D drag has no undo either: drag it back.
- **Dropping a fixture may move the camera.** Every drop lays the venue out
  again; if the room grows for a fixture put beyond a wall, the camera preset
  may be re-applied. Not checked on screen.
- **Snap targets are the scan's own lines.** The view's drawn truss rows for a
  rig with no scanned room are not snap targets, and there is no grid snap.
- **A real scan.** Polycam, Scaniverse and RoomPlan exports from a real venue
  have not been read. Expect the thresholds in `extract.py` to need tuning.
- **Binary USDZ** (`.usdc`): not read. Export OBJ.
- **Ceilings and levels.** Sloped or domed ceilings, balconies and mezzanines
  are still read as a flat ceiling over one floor.
- **The 2D layout view** does not draw the scanned room; only the 3D view does.
- **Editing the suggestion.** A raised area or line cannot be renamed, moved or
  deleted in the UI; the choice is to store the shell or not.
- **Crowd and booth in a scanned room** are left out rather than fitted round
  what the scan found.
- **Photos to a room** (photogrammetry inside this system) is out of scope: the
  phone apps already do it for free.
