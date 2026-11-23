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

The **2D layout view** now draws the stored scanned room under the fixtures
(see "In the 2D layout view"), and **holds a drag or a palette drop to that
room** instead of to the stage deck, with its labels laid out round the room.
The room layer's own tests passed when it was built. The drag, drop and label
work's tests pass too (vitest 384, Nov 22), **but none of the 2D
room work has been seen in a browser** (see What is left).

Slice 8 makes the rest of it go by **a room that is not a box**: a suggested
row is held inside the floor outline and not only its box, a 2D drag snaps to
the scan's truss, the 2D grid is drawn across the room, and a fixture clicked
in the palette lands inside the room (see "What slice 8 built"). Its backend
unit tests pass (171 across the room-scan unit files, Nov 22). **Its frontend
tests are written and type-check but have not been run**, and none of it has
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

Dragging in the 2D layout view still saves through batch-update and does
**not** confirm a position. With a scanned room drawn it is held inside the
room's walls rather than to the stage deck (see "In the 2D layout view"). That
limit is tighter than this one: the 2D view stops at the wall, the 3D view and
the server 2 m beyond it. It snaps to the scan's truss lines and rings on the
plan as the 3D drag does, but does not take the truss's height.

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
- **Every row** comes inside the walls: 0.2 m in from the walls of the room's
  box.
- **In a room with a floor outline** (an L, a cut corner) the box is not the
  room. A row with any guess outside the outline, in the notch of an L say, is
  shifted **as one piece** by the least that puts every guess of it inside and
  0.2 m clear of every wall, in steps of 0.05 m. Of two shifts as short, the
  one that changes depth less is taken. A row already inside is left alone,
  however close to a wall of the notch it stands. A row that fits nowhere in
  one piece (corner to corner of an L) has only its guesses outside brought
  in, each on its own, and a note in the answer says the row is no longer
  straight. A guess laid along an angled line or round a ring is left on it
  unless that spot is outside the outline, which a truss the scan found never
  is. A box room, and an outline that is not one (fewer than three corners, a
  number missing, under 1 m2), is held to the box as before.

A fixture a scan may not move is never brought inside either: a tapped or
confirmed fixture standing in a notch stays there.

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

## In the 2D layout view

The rig editor's plan (`StageView2D.tsx`) draws the same stored shell, by the
same rule as the 3D view (`room_shell.source == "scan"`) and in the same axes:
metres, origin at the centre of the floor, X across, -Z upstage at the top.
What is fit to draw is decided by the 3D view's own checks (`roomOutline`,
`scanRisers`, `usableLine`, `scanRings`), so the two views agree. The shapes
come from `roomPlan` in `components/rig/roomPlan2d.ts`, which has no React in
it.

- **Walls**: the room's box, or the floor outline when the room has one, as a
  grey line with a darker floor inside it. The outline is the stored one: a
  wall is not moved out for a fixture beyond it, as the 3D view's is.
- **Raised areas**: a brown rectangle each, labelled with its name (or
  "Stage", "Riser", "Booth or counter" from its kind) and the height of its
  top above the floor.
- **Truss lines**: teal, between the line's two ends at whatever heading, as
  wide as the scan measured, labelled with the height it hangs at. The purple
  dashed TRUSS lines are still the plan's own, worked out from the fixtures.
- **Rings of truss**: a teal circle, labelled the same way.
- **Tooltips**: resting the pointer on any of them gives the longer wording
  the Room Scan dialog uses (size, underside height, which way a line runs).
- **The view grows to take the room in.** The plan used to show the stage
  and a metre round it. A scanned room that reaches beyond that is shown
  whole, with the same metre round it, so the stage is drawn smaller. The
  stage, its grid and the fixtures keep their coordinates.
- **Fixtures are drawn last**, on top of all of it, and are what a press lands
  on.

### Dragging and dropping in the room

When the room's walls are drawn, a drag and a drop from the palette are held
to the room, not to the deck (`holdOnPlan` in `roomPlan2d.ts`):

- **Inside the walls**: anywhere inside the floor outline when the room has
  one, else inside the room's box. A position beyond a wall is brought to the
  nearest point of the walls, by the 3D view's own `holdNearOutline` with no
  margin. The notch of an L is outside the room: a fixture dragged or dropped
  into it stops on the notch's wall.
- **A fixture a scan hung beyond the deck stays where it is when picked up**,
  and can be moved about out in the room.
- **Grid snap carries on past the deck** (`snapToRoomGrid`): the same
  multiples of the grid size, with no last line to stop at. A position held
  to a wall may rest between two lines.
- **The grid is drawn where it snaps** (`planGrid`): across the room's floor
  and the deck, each line for the stretches of it inside the walls or on the
  deck. In a room with a floor outline a line stops at the wall of a notch
  and nothing is drawn in the notch. A line that lies exactly along a wall
  may or may not be drawn under it.
- **A drag snaps to the scan's truss** (`planTrussTargets`,
  `snapToScannedTruss`): within 0.4 m on the plan of a scanned truss line (at
  any heading) or ring, the fixture goes onto it, by the 3D drag's own
  `snapLines` and `snapToLines`. On a ring it goes straight out from or in
  towards the centre. It is tried first in the Grid and Truss snap modes;
  out of reach, the mode carries on as before (the grid, or the depth of the
  plan's own purple truss lines). **Holding Alt** lets go of the scanned
  truss for that drag, and the snap mode **None** lets go of everything.
  Unlike the 3D drag it does not go by height (any truss on the plan is in
  reach), does not snap to the edges of raised areas, and does not change the
  fixture's height. The snapped position is then held to the room.
- What holds a drag is the walls the plan draws, so the two cannot disagree.
  A scan with truss or raised areas but no usable room draws no walls, and a
  drag is then held to the deck as with no room; it still snaps to that
  scan's truss.

### Clicking a fixture in the palette

A click, as against a drop, lets the app choose the place (`paletteClickSpot`
in `roomPlan2d.ts`, called from `RigBuilder.tsx`). With a scanned room's walls
drawn:

- **centre stage** when that is inside the room, which it is in every box
  room;
- else **the middle of the room's floor** by area, brought 0.6 m in from the
  walls where it is nearer than that (`insetPoint`): the middle of an L's
  floor can fall close to its notch;
- then stepped clear of fixtures already within 0.6 m, as before, each step
  **held to the walls** and not to the deck.

With no scanned room it is centre stage, stepped clear inside the deck, as it
always was.

### Labels

- **The plan's own labels go by the room** (`planFrame`). With walls drawn,
  "UPSTAGE — BACK WALL" stands over the scanned room's upstage wall, the
  AUDIENCE arrow and word below its downstage wall, and the scale bar over
  its upstage stage right corner: all outside the room's floor. Each goes by
  the outer of the deck and the walls, so a room smaller than the deck does
  not pull them onto the deck. The deck's own upstage and downstage edges are
  still drawn as lines.
- **The room layer's labels are kept off each other** (`planLabels`). Each
  starts where it always was: a raised area's in its middle, a truss line's
  over the middle of the line, a ring's over its upstage side. Taken in that
  order, one that would print over a label already placed is stepped away
  from its shape by 1.4 times its text height, then tried on the far side of
  the shape, then further each way; the earlier label keeps its place. One
  with nowhere clear stays where it began.
- **A truss label lies along its line.** A line more than a degree off
  straight across has its label turned to it, on the upper side, between -90
  and 90 degrees so it never reads upside down; a line running upstage to
  downstage reads up the plan. A line straight across keeps a level label.
- Text cannot be measured where this is worked out, so a label's width is
  taken as 0.55 of its text height for each character.

A rig with no scanned room (no shell, or a demo preset's shell) draws exactly
what it did: nothing is added, the view is the size it was, the labels are
where they were, and a drag or a drop is held to the deck on the deck's grid.

## What slice 8 built

- **Suggestion** (`suggest.py`): `_floor_outline` reads the room's outline by
  the position route's rule; `_shift_into_outline` finds the least shift of a
  whole row that puts it inside, using the reader's own `inside_outline` and
  `clear_of_outline`. Applying the same scan again still moves nothing: a row
  is only sent there when a guess is outside the outline, and lands 0.2 m
  inside it.
- **2D drag** (`StageView2D.tsx`, `roomPlan2d.ts`): snapping to scanned truss
  lines and rings with the 3D drag's helpers; Alt lets go.
- **2D grid** (`planGrid`): drawn across the room's floor and the deck.
- **Palette click** (`paletteClickSpot`, `RigBuilder.tsx`): into the room.

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

## What the outline is to the rest of the view

A room that is not a box used to be a box to everything but its own walls.
Now one outline (`Venue.outline`, from `buildVenue`) is read by all of it. The
maths is in `previs/outline.ts`, which has no three.js in it.

- **Beams** end on the outline's walls, the inner walls of a notch included
  (`beamRoom`, `beamLanding`), and not on the box round them. With the venue
  hidden there are still no walls.
- **Mounts and truss**: a fixture is bracketed to whichever wall of the
  outline it is against, and the view's truss stops at the walls the line
  across the room meets at its depth.
- **Walls move out** for a fixture placed beyond them, as a box room's do: the
  nearest wall goes straight out to 0.15 m past it, its ends sliding along the
  walls either side (`outlineAround`). Not for a position that is still a
  guess, and not where the move would leave something that is no longer a room;
  the fixture is then left outside.
- **Drag limits**: a position is held to within 2 m of the room itself, then
  to the box, so the depth of a notch is out of reach like anywhere else
  beyond a wall. The position route does the same two steps in the same order
  (`hold_position` in `fixture_position.py`, `clampPosition` in
  `fixtureDrag.ts`), so a fixture does not jump when a drag is saved.
- **Cameras**: a preset whose target or standing place falls outside the room
  is brought to the nearest place inside, 0.6 m clear of the walls
  (`cameraPreset`). A preset already inside is unchanged, and so is the top
  view.
- **Ceiling**: the beams and the duct the box ceiling has, cut to the outline
  (`buildOutlineCeilingDressing`).

A box room, and a shell with no outline, draw and clamp exactly as before.

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
- `frontend/src/__tests__/roomShapes.test.ts` (**passing: frontend vitest 344 passed, Nov 22 2026**): an angled bar lying on its line whichever end it is written
  from; a ring's geometry; fixtures clamped to a line or ring with no truss of
  the view's own; which outlines are taken for one; a wall per segment facing
  into the room, for corners in either order; the floor cut to the outline;
  snapping onto an angled line and a ring, and when a ring is left alone; a
  shell stored before all this drawing and snapping as it did; the dialog's
  wording.

- `backend/tests/unit/test_fixture_position_outline.py`: which rooms have an
  outline, a position held to within the margin of an L-shaped room and then
  to the box, and a box room held as it always was.
- `frontend/src/__tests__/outlineBounds.test.ts` (**passing: frontend vitest 344 passed, Nov 22 2026**):
  a beam stopping on the wall of a notch and landing as the box does when the
  outline is a box; mounts and truss against a notch; walls moving out, and
  not for a guess; drag limits; the cameras; the ceiling's beams and duct.

- `frontend/src/__tests__/roomPlan2d.test.ts` (**passing: frontend vitest 344 passed, Nov 22 2026**): the plan shapes for a box room, an outlined room, an angled
  truss, a ring of truss and a shell with nothing to draw (none, a demo
  preset's, an empty scan); a shell stored before headings and rings; the
  labels and tooltips; the view box with no room, a room inside the stage and
  a room beyond it.
- `frontend/src/__tests__/StageView2D.test.tsx` (**the tests listed in this
  item passed in the 344 run of Nov 22 2026; those in the next item were added
  to the file afterwards and have not been run**): the room layer drawn for a
  scanned room (walls, outline, raised areas, lines, a ring, each with its
  height) and under the fixtures; the same markup and view box as before for
  no shell, a null shell and a shell that is not a scan; a drag still read in
  stage metres with the view grown.
- The same file, added with the drag work (**passing, Nov 22**): a fixture
  beyond the deck not brought onto it when picked up, in each snap mode; a
  drag held at a box room's wall and to an L-shaped outline; a palette drop
  landing out in the room, on a wall, and out of a notch, and its landing
  spot shown; with no room, or a scan with no walls, a drag and a drop still
  held to the deck on its grid; the plan's own labels against the deck and
  against the room; a level label on a truss straight across, a turned one on
  an angled line, and one of two overlapping labels nudged.
- `frontend/src/__tests__/roomPlan2dLayout.test.ts` (**passing, Nov 22**):
  the same with no drawing. A position held to the deck, to a box room and to
  an L-shaped outline (inside, in the notch, beyond the box, beyond a
  corner); the grid past the deck; what the plan's labels are set against
  for no room, a room beyond the deck, inside it, past one side, and an
  outline; a label's turn from either end of a line; labels left alone when
  clear, nudged when they would overlap, and placed along an angled line.

- `backend/tests/unit/test_room_scan_shapes.py`, `TestGuessesInsideAnOutline`
  (**passing, Nov 22 2026**): a floor row in the notch of an L brought inside
  as one piece, by the least shift, keeping its spacing, height and tags; the
  same scan applied again moving nothing, for a floor row, a row brought down
  to a hanging height and a row overhanging its truss; a tapped, confirmed,
  measured or row-fitted fixture in the notch left there; a row already
  inside left alone; a guess beyond a cut corner; a row that fits nowhere in
  one piece; a scanned L; a box room and an outline that is not one moving a
  row exactly as before; a spot on a stored ring that reaches into a notch.
- `frontend/src/__tests__/roomPlan2dLayout.test.ts`, added with slice 8
  (**passing, Nov 22**): which shapes of a scan are snap targets; snapping to
  a line, its end, an angled line and a ring, the reach, the nearer of two,
  and no height window; the grid in a box room, past a deck, over a deck that
  reaches beyond the room, and cut to an L; where a palette click goes with
  no room (as before), in a box room, and in a room whose notch takes in
  centre stage.
- `frontend/src/__tests__/StageView2D.test.tsx`, added with slice 8
  (**passing, Nov 22**): a drag snapping onto a truss line, an angled line
  and a ring; Alt and the snap mode None letting go; the grid beyond a
  truss's reach; a snapped position still held to the walls; a palette drop
  not snapping; no snap with no scanned room; the grid drawn wall to wall,
  stopped at a notch, and the deck's own with no room.

## What is left

- **Checks ran on 2026-11-22, 7:44 PM ET, after slice 8 (outline-held guesses, 2D truss snap, room grid, palette click):** frontend vitest 424 passed (22 files) and the build passed; backend pytest tests/ 1632 passed, 10 skipped, 5 xfailed, including tests/integration/test_api_room_scan.py.
- **The 2D drag, drop and label work has not had its tests run.** It was
  written on 2026-11-22 after the run above, in a session that could start
  `tsc` but not vitest. `npx tsc --noEmit -p .` gives the same 13 errors with
  it as without, none in the files it touches. Run
  `npx vitest run src/__tests__/roomPlan2dLayout.test.ts src/__tests__/StageView2D.test.tsx src/__tests__/roomPlan2d.test.ts`
  from `frontend`, then the whole suite and the build. The palette-drop tests
  set the pointer position on the event by hand; if they fail and the rest
  pass, suspect the test's event before the view.
- **The 2D room layer has not been seen in a browser**: label sizes and
  nudges in a crowded room, a turned label, the tooltips, where UPSTAGE,
  AUDIENCE and the scale bar land round a real room, a drag and a palette
  drop out in the room with the view grown, a drag snapping to a truss line
  and a ring, the grid across an L-shaped floor, and where a palette click
  lands.
- **A 2D drag that snaps to truss keeps the fixture's height.** The 3D drag
  hangs the fixture at the truss's height; the 2D view saves only where it is
  on the plan. Nothing on the plan says what it snapped to, either: there is
  no readout or highlight as the 3D view has.
- **A palette drop does not snap to scanned truss**, only a drag does. A
  fixture dropped on a truss line lands on the grid next to it.
- **The 2D truss snap takes hold on the first move.** There is no 5 pixel
  threshold as in the 3D view, so a press with a wobble next to a truss puts
  the fixture on it (as a press already puts one on the grid). Alt has no
  touch equivalent.
- **Alt lets go of the scanned truss only.** The grid, or the plan's own
  truss lines, still take the fixture; set the snap mode to None for a free
  drag.
- **A row too long for any arm of the room is no longer straight.** Its
  guesses outside the walls are brought in one by one, so flash-and-tap's row
  fit does not apply to it, and if it was also centred on a truss it
  overhangs, applying the same scan again may shift it once more.
- **A row brought inside an outline may leave its truss.** A row that
  overhangs a truss into a notch is shifted whole to where it fits, which can
  be the other arm of an L. The least shift is not always the one a rigger
  would choose.
- **A room's "middle" for a palette click is the middle of its floor by
  area**, found to the nearest 0.25 m when it has to be brought in from a
  wall. It does not look for the widest part of the room.
- **A fixture already outside the walls jumps to the wall on its first 2D
  move.** The 3D view and the server let a fixture stand up to 2 m beyond a
  wall, and a fixture a person placed can stand in the notch of an L. Picked
  up in the 2D view, either comes to the nearest wall at once. Use the 3D
  view's Move fixtures to place something beyond a wall.
- **The same goes for a deck that reaches beyond the scanned room.** The room
  is the limit, so a fixture on the part of the deck outside the walls is
  brought inside them when moved in 2D.
- **The 2D and 3D limits differ by 2 m**, as above: 2D stops at the wall. The
  batch-update route the 2D view saves through holds nothing itself.
- **2D label layout is simple.** It keeps the room layer's labels off each
  other only: not off fixture names, the plan's own labels, the purple TRUSS
  lines, or the walls and shapes themselves. A nudged label can end up over
  another shape, or outside the view on a crowded edge. Width is guessed
  from the character count. A raised area's label is not kept inside a
  narrow area, and there are no leader lines back to the shape.
- **AUDIENCE stands outside the downstage wall.** It marks which way is
  downstage; it no longer sits where a crowd would stand, which in a scanned
  room is inside the walls.
- **Nothing of slice 4 has been seen in a browser**: an outlined room's walls
  from each camera, an angled bar, a ring, and a drag snapping to either.
- **Nothing of the outline work has been seen in a browser**: a beam stopping
  on the wall of a notch, a wall moved out for a fixture, the cameras in an
  L-shaped room, the ceiling's beams and duct.
- **A guess does not move an outline's wall.** A scan now suggests a place
  inside the outline for every guess it may move, but a guess the scan was
  applied without moving (the box unticked), or one added in the notch
  afterwards, is still drawn outside the walls until somebody places it.
- **Cameras are moved on a 0.25 m grid.** A preset that falls outside the room
  goes to the nearest grid point 0.6 m clear of the walls, not the exact
  nearest place.
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
- **Editing the suggestion.** A raised area or line cannot be renamed, moved or
  deleted in the UI; the choice is to store the shell or not.
- **Crowd and booth in a scanned room** are left out rather than fitted round
  what the scan found.
- **Photos to a room** (photogrammetry inside this system) is out of scope: the
  phone apps already do it for free.
