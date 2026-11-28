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
unit tests pass (171 across the room-scan unit files, Nov 22), and so do its
frontend tests (vitest 424, Nov 22). None of it has been seen in a browser
(see What is left).

Slice 9 makes **correcting a suggested layout quicker** in the 2D view: a
fixture snapped onto scanned truss takes the truss's hang height and a readout
says what it is on, a palette drop snaps the same way, and a whole row can be
selected and dragged as one piece, held inside the room (see "Moving a whole
row" and "What slice 9 built"). No backend change was needed. Its tests
pass (frontend vitest 478, run after it was written). None of it has been
seen in a browser (see What is left).

Slices 10 and 11 add **Lay on truss**, and **a drag threshold, a selection
box and the keyboard** on the 2D plan. Their tests pass too (frontend vitest
495 after slice 10, 576 after slice 11).

Slice 12 makes the 2D plan **usable from a phone or a tablet at the venue**:
a long-press is the touch for Shift, the keys are also buttons over the
plan, and the plan says when the keys are going to a text field
(`planTouch2d.ts`, `PlanNudgePad.tsx`, `StageView2D.tsx`). Its tests pass (frontend vitest 654, build OK). It has not been tried on a phone, a
tablet or in any browser (see What is left).

Slice 20 **finishes raised areas**: a riser standing on a stage follows the
stage when it is moved, raised or given a quarter turn, with its own
fixtures and in the same undo step; the Add form has a base height; and a
selected raised area has corner and edge handles on the 2D plan (see "What
slice 20 built"). Its backend tests pass (pytest 1990 passed, 10 skipped,
5 xfailed, Nov 23). **Its frontend tests are written and type-checked but
have not been run**, and nor have slice 19's: the sessions that wrote both
were refused `npx vitest --run` and `npm run build`. Run both in
`frontend/` before relying on either slice (see What is left).

Slice 21 lets **a raised area stand at any heading**: a stage, riser or
booth stores `heading_deg`, the whole of it is held to the room as it
stands, the fixtures and the raised areas standing on it swing about its
middle with the turn, the 2D plan, the 3D view and the drag's snap lines
draw it turned, and it has a Heading field on its row and on the Add form
and a rotate handle on the plan (see "What slice 21 built"). **Its frontend
tests are written and type-checked but have not been run** either (see
What is left).

Slice 22 sets **heights by dragging**: while the room's items are arranged
on the 2D plan, a strip beside the plan shows the selected item from the
side, with a handle for a raised area's top and one for its base, and one
for a truss line's or a ring's trim height (see "What slice 22 built").
Frontend only. **Its tests are written and have not been run, and it has
not been type-checked or built**: the session that wrote it had no
`node_modules` and was refused `npx vitest run`, `npm run build`, `npm ci`
and `tsc`. The backend suite was run and passes (see What is left).

Slice 23 fits **the booth and the crowd to a scanned room** in the 3D view:
the desk, decks and DJ on the raised area the room calls a booth (or, marked
as a guess, on its first stage), and the crowd on the floor left open round
the stage, the risers and the booth, inside the walls. A raised area at a
heading (slice 21) is read as it stands turned (see "What slice 23 built").
Frontend only. Its tests, the type-check and the build have been run and
pass; it has not been seen in a browser (see What is left).

Slice 24 reads **binary USD** (USDC, the "crate" format), alone or inside a
USDZ, which is what Apple's RoomPlan, Polycam and Scaniverse write. Until now
a USDZ from a phone was refused unless its layer happened to be text. The
reader is pure Python: no USD library and no new dependency (see "What slice
24 built"). Backend only. Its tests pass against files written by Pixar's own
USD library; **no USDZ from a real phone has been read by it yet** (see What
is left).

Slice 25 reads **glTF 2.0** (`.glb`, and a `.gltf` with its data inside it),
which is what Polycam, Scaniverse and most LiDAR apps export by default and
was refused until now. It goes through the same preview and apply as an OBJ.
A file packed with Draco or meshopt compression, or a `.gltf` with a separate
`.bin`, is refused with the fix in the message (see "What slice 25 built").
Its backend tests pass. **No glTF from a real phone has been read**: every
file it has seen was written by the tests. The file picker's change was not
run (the worktree had no `node_modules`).

Slice 26 reads **a scan sent as a zip**, which is how Polycam and Scaniverse
often share one: a `.gltf` with its `.bin` and textures, or an `.obj` with
its `.mtl` and textures. The zip is read in memory and nothing in it is
trusted; the one model in it is the scan, and a `.gltf` finds its `.bin`
beside it (see "What slice 26 built"). Its backend tests pass. **No zip from
a real phone has been read**: every one it has seen was built by the tests.
The file picker's change was not run, for the same reason as slice 25's.

Slice 27 makes **the suggestion go by a stage that stands at a heading**. A
scan now measures a stage turned from the room's walls (5 degrees or more)
and stores its heading; a floor row suggested onto it is laid parallel to
its turned edges, as far in from them, and each fixture is turned as far;
and the scan's undo turns them back (see "What slice 27 built"). A stage
standing square is read and suggested for exactly as before. Backend only.
Its tests pass (pytest 2531 passed, 10 skipped, 5 xfailed, Nov 24). **No
turned stage from a real phone has been read** (see What is left).

Slice 29 **shows the turn in the Room Scan dialog**: the table of fixture
moves has a Turn column, and the sentence above it says how many fixtures
will be turned (see "What slice 29 built"). Frontend only. The type-check
was run and has only its 13 older errors. **Its tests are written and have
not been run, and the build was not run**: `npx vitest run` and `npm run
build` were refused in the session that wrote it (see What is left).

**A room from a walkthrough video: built, and tested everywhere except against
a real COLMAP.** COLMAP is not installed on the machine this was written on, so
the reconstruction step has only been driven with a stand-in process. Frame
sampling was run with real ffmpeg and real OpenCV; finding which way is up,
scaling, and the API are tested against a synthetic room handed over tipped and
unscaled, as a photogrammetry tool hands one over. The first real video is a
test of the COLMAP commands (see [What is left](#what-is-left)). See
[From a walkthrough video](#from-a-walkthrough-video).

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
| Polycam, Scaniverse, 3D Scanner App | **OBJ** or **GLB** (glTF binary, what most of them export by default), or PLY | a mesh |
| Anything writing glTF 2.0 | `.glb`, or a `.gltf` with its data inside it (base64), **without Draco or mesh compression** | a mesh in metres, Y-up, as glTF defines; a file with only points is a point cloud |
| Any LiDAR or photogrammetry app | PLY, ASCII or binary, with or without faces | a mesh or a point cloud |
| Polycam, Scaniverse, RoomPlan apps | **USDZ** as the app shares it | a mesh, with the units and up axis the file states |
| Apple RoomPlan apps | the RoomPlan **JSON**, or a USDZ that carries it | walls and objects as boxes |
| Anything writing USD | USDA (text) or USDC (binary), alone or in a USDZ | a mesh, with the units and up axis the file states |
| Polycam, Scaniverse, anything that shares several files | a **ZIP** as the app shares it: a `.gltf` with its `.bin`, an `.obj` with its `.mtl`, either with textures | the one model in the zip, read as that file would be on its own |

**A zip** (slice 26) is sent as it is: do not unpack it. The server reads the
model in it and, for a `.gltf`, the `.bin` files it names; textures and `.mtl`
files are never opened. If the zip holds more than one model, one is read, in
this order: `.glb`, `.gltf`, `.usdz`, `.usdc`, `.usda`, `.obj`, `.ply`,
RoomPlan `.json`. The preview's assumptions say which file was read and which
were left alone. One that cannot be read (a Draco-packed `.glb`, a `.gltf`
whose `.bin` is missing) gives way to the next, and the preview says that
too. A zip with a password, with more than 2,000 files, or that unpacks to
more than 200 MB is refused.

A USDZ is read whether its layer is text or binary USD (`.usdc`, slice 24).
OBJ is still the surest export: the binary reader has only read files written
by Pixar's USD library, not yet one from a phone. One layer of a USDZ is
read; a scan split across layers that bring each other in may come out with
parts missing or out of place, and the report says when a USDZ held more than
one. A binary layer that cannot be read (damaged, cut short, or a newer
format) is refused, and the server says why and names the fix: export OBJ
from Polycam or Scaniverse instead.

Some glTF **cannot be read**, and each is refused with the fix
in the message (slice 25):

- **Draco or meshopt compression** (`KHR_draco_mesh_compression`,
  `EXT_meshopt_compression`): unpacking it needs a decoder that is not in
  Python's standard library. Export again with compression switched off, or
  export OBJ. Quantised positions (`KHR_mesh_quantization`, which mesh
  optimisers write) are refused the same way.
- **A `.gltf` sent without its `.bin`**: the mesh is in the `.bin`, so it
  never arrives. Send the two zipped together (slice 26; the app's own zip
  is that), or export `.glb`, which is the whole scan in one file.
- **glTF 1.0**. Export glTF 2.0.

Textures are never read, so a `.glb` whose images are in separate files, or in
a format this does not know, is still read for its shape.

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
   and why. Its **Turn** column says how many degrees a fixture is turned
   with a stage that stands at a heading (clockwise seen from above), with a
   dash where it is not turned; the sentence above the table says how many
   will be. Where the room already stored has a raised area ticked as the
   **DJ booth**, one line says what applying will do to the tick: "DJ booth
   mark: kept on Riser", or a warning, "DJ booth mark will be dropped"
   (slice 31). Where you have corrected the stored room's raised areas in
   Edit Room, one more line says what applying keeps of that: "Will keep
   your edits on 2 areas" (slice 32). The same line counts overhead lines
   and rings ("2 areas and 1 overhead item"), says "Will leave out 1 area
   you deleted" where the scan reads again a raised area you took out, and
   turns into a warning with "1 to check against the new room" where
   something kept is above the new ceiling or outside the new walls (slice
   33). **Under that line is the same by name** (slice 35): one row for
   each thing, "Front truss (line): kept your edits", "Riser (raised area):
   left out (you deleted it)", "Side pipe (line): replaced (a scanned item
   overlaps it)", "Podium (raised area): added by hand, kept". The first
   five are shown; **Show all** opens the rest. **Anything lost is said in
   a warning of its own**: a truss you named or trimmed that the scan now
   reads more than 1.0 m higher or lower, or to one side of where it was,
   loses the name and trim, and the warning says where the scan read it; a
   thing you deleted that this scan did not see is no longer remembered as
   deleted, and may come back on a later scan. What is to be checked
   against the new room is said in full the same way.
3. If the room came out wrong, correct the guess and the preview is read again:
   **Units** (metres, centimetres, millimetres), **Up axis** (Y or Z), **Turn
   the room** in quarter turns when the wrong wall was taken as upstage.
4. **Store the room** (and, if ticked, move the listed fixtures). Untick the box
   to store the room and leave every fixture where it is. Where the room it
   replaces had a raised area ticked as the **DJ booth**, the tick is kept
   on the same raised area of the new room; if the new scan has none of
   that kind standing there, the dialog says the mark was dropped, and it
   is ticked again in Edit Room (slice 30). A kind you set by hand on the
   ticked raised area (a scan's riser made a booth) is kept with the tick,
   whatever the scan reads there (slice 31). **Your corrections to raised
   areas are kept too** (slice 32): a name you typed, and a height or a
   base height you set, stay on the raised area the new scan reads in the
   same place, while where it stands and how wide and deep it is are read
   again from the scan. A raised area you added is kept as it is where the
   new scan has nothing; where the scan now reads something on that spot,
   the scan's takes its place and the dialog says so. **An overhead line
   or ring keeps the name you typed and the height you hung it at** the
   same way, and one you added is kept where the scan has no truss (slice
   33). **A raised area, an overhead line or a ring you deleted stays
   deleted** (lines and rings: slice 34): the scan reads it again, and it
   is left out and the dialog says so. To have it back, use the room's Undo
   before scanning, or take the room off the rig and scan from scratch. A
   width, a depth, a length, a heading or a place you set are still the
   scan's again. Two trusses hung one above the other keep their own names
   and heights: a truss is known by where it hangs as well as where it is
   on the plan (slice 34).
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
plan as the 3D drag does, takes the truss's hang height as the 3D drag does,
and says what it snapped to. Several fixtures can be selected there and moved
as one row (see "Moving a whole row").

### Undoing the moves a scan made

Applying a scan records where each fixture it moved stood before. While that
record holds moves, **Undo room scan moves (n)** is shown in the Room Scan
dialog and in the 3D view's header. It asks once, then puts those fixtures
back. A fixture a person has tapped, confirmed, dragged or moved since the scan
is **left where it is** and named in the answer with the reason ("Left alone:
Spot 1 (...)"). The stored room stays. A fixture the scan also turned, with
a stage that stands at a heading (slice 27), is turned back as well, unless
somebody has turned it since: then it goes back to where it stood and keeps
the way it faces.

**Remove the stored room** takes the room off the rig again. When the scan
moved fixtures it asks first: remove the room and put them back, or remove the
room only. Removing the room only leaves the undo available afterwards.

### Editing the room by hand

A scan guesses; somebody who can see the room knows the "Booth or counter" is
the bar and the "riser" is a flight case. Rig editor toolbar, **Edit Room**
(`RoomShellEditDialog.tsx`, `utils/roomShellEdit.ts`). The button is there
only for a rig with a scanned room stored. Opening it first writes any drag
still waiting to be saved, and the 2D plan's keys and nudge pad are off while
it is open.

- **One row for each raised area, overhead line and ring** of the stored
  room, in that order, with its name, where its middle is, its size, its
  height and what is stored (size, height, which way a line runs). **Across**
  is metres from the centre line (stage left is positive); **Depth** is
  metres from the middle of the floor (downstage is positive, upstage
  negative). A comma is taken for a decimal point.
- **Size and height** (slice 15). A raised area has **Width** (across the
  room) and **Front to back**, a line has **Length** and **Heading**, a ring
  has **Radius**, and every row has **Height**: a raised area's deck above
  its base (the floor, unless it has a base height: see below), and the
  underside of a line or ring, which is where fixtures hang from. A heading is degrees clockwise from across the room seen from
  above: 0 runs across, 90 from upstage to downstage, and a line has no
  front, so 135 is stored as -45. A size changes about the middle; a line is
  made longer along the way it runs and turned about its middle.
- **Turn**, on a raised area's row, swaps its width and its front-to-back: a
  quarter turn. The turn is typed into the row, and is saved like any other
  change. Any other turn is its Heading.
- **Heading** (slice 21), on a raised area's row and on the Add form: which
  way its width runs, in degrees clockwise from across the room seen from
  above. 0 stands square to the room, as most of what a scan finds does (a
  scan gives a heading only to one clearly turned from the walls, slice 27); 30
  is turned 30 degrees. A rectangle looks the same after half a turn, so
  135 is stored as -45. Its width is then along its heading and its front
  to back square to it. The row, the 2D plan's tooltip and the notice say
  how far it is turned ("6.0 m by 3.0 m, turned 30 degrees, top ..."). The
  fixtures and the raised areas standing on it are swung about its middle
  by the turn when its box is ticked, and the whole of it, as it stands,
  is kept inside the room's box and the 2 m round it. It is marked
  **Resized by hand**.
- **Kind** (slice 18), on a raised area's row: a selector that makes it a
  **Stage**, a **Riser** or a **Booth or counter** where it is. Its place
  in the list is kept, and no fixture moves. One still called what its old
  kind is called ("Riser") is called what its new kind is ("Stage"); a name
  somebody gave is kept. It is marked **Kind set by hand**.
- **Base height** (slice 18), on a raised area's row: how far its underside
  is above the floor. 0 stands on the floor, as everything a scan finds
  does; more floats, as a balcony or a mezzanine does, and its top is then
  its base and its height together. The row and the 2D plan's tooltip say
  how far it floats ("top 3.00 m above the floor, floating 2.70 m above
  it"). A changed base is marked **Resized by hand**.
- **The limits.** A raised area's sides are at least 0.3 m and its deck 0.05
  to 3 m, with its top under the ceiling; its base height is 0 to 10 m. A line is at least 0.5 m long and
  a ring 0.3 m in radius; either hangs between 0.5 m and the ceiling. The
  row says so when a field is under its limit or not a number. Whether a
  size fits the room is the server's to say, and its words are shown ("...
  the room and the 2 m round it have room for 16 m").
- **Save** sends that row's changes and only what differs from what is
  stored, so a rename is never also a move, nor a move a resize. It is off
  until something is changed, and while a field cannot be saved (an emptied
  name, one over 60 characters, a position or size that is not a number, a
  size under its limit), with the reason in the row.
- **A move keeps the shape.** A line keeps its length and heading. The middle
  is held to the room's box and 2 m round it; when it was held short, the
  message says where it was put. A moved item is marked **Moved by hand**.
- **A resize keeps the whole item in the room.** The whole of a resized or
  turned item, not only its middle, is kept inside the room's box and the
  2 m round it: its middle is brought in until it is, and the message says
  where to. One too big to fit at all is refused. It is marked **Resized by
  hand**.
- **Fixtures follow their truss** (slice 17). Each line's and ring's row has
  a box, **Move the fixtures hung on it**, ticked to start with. Ticked, a
  line or ring that is moved, raised, lowered, turned or resized takes the
  fixtures hung on it along: shifted with a move, raised or lowered by the
  same amount, swung about a line's middle with a turn (and turned
  themselves, so a light square to the truss stays square to it), spread
  out or closed up along a line made longer or shorter, and moved out or in
  with a ring's radius. The message says how many moved ("2 fixtures hung
  on it moved with it."), and the 2D plan and the 3D view show them where
  they now are. A fixture hangs on a truss when it is within 0.3 m of it on
  the plan and 0.6 m of its underside: the reach "Select row" goes by.
  Unticked, the truss goes alone, as it did before slice 17, and the box
  stays unticked for that row until the dialog is opened again, or until a
  delete or an undo, which may change which row is which. A rename never
  moves a fixture.
- **Fixtures follow the raised area they stand on** (slice 18). Each raised
  area's row has the same box, worded **Move the fixtures standing on it**
  and ticked to start with. Ticked, a raised area that is moved, raised,
  lowered, resized or given a quarter turn takes the fixtures standing on
  it along: shifted with a move, raised or lowered by what its top moved
  (its height or its base height), kept at the same share of a footprint
  made bigger or smaller (half way across a stage made wider is still half
  way across), and swung a quarter turn clockwise seen from above about its
  middle with **Turn**, their heading turned with them. The message says
  how many moved ("3 fixtures standing on it moved with it."). A fixture
  stands on a raised area when it is over its footprint, or within 0.15 m
  of its edge, and between 0.05 m under its top and 0.6 m above it. One
  that hangs on a truss or ring of the room is the truss's, never the
  stage's under it; one over two raised areas (a riser on a stage) stands
  on the one whose top it is nearer. Unticked, the raised area goes alone.
  A change of kind never moves a fixture.
- **A change that would carry a fixture out of the room is refused whole**,
  with the server's words naming the fixtures and where they would have
  gone: neither the truss or raised area nor any fixture moves. "Out" is past the room's
  box and the 2 m round it, more than 2 m above the ceiling, or below the
  floor. Change the truss or raised area by less, or untick the box and
  move the fixtures afterwards.
- **Add what the scan missed**, under the rows: choose a stage, a riser, a
  booth or counter, a truss line or a truss ring, give it a name (left
  empty, it is called what it is), where its middle goes, its size and its
  height, and press **Add to the room**. Each kind starts at a usual size in
  the middle of the floor. It goes at the end of its list, is drawn and
  snapped to like anything the scan found, and is marked **Added by hand**:
  it is stored as a person's, not as a suggestion. A room the scan found
  nothing in can be added to as well. A stage, a riser and a booth also
  have a **Base height** (slice 20), 0 to start with: how far its underside
  is above the floor. Give a riser that stands on a stage the height of the
  stage's top, and it goes with the stage from then on.
- **A raised area standing on another goes with it** (slice 20): a riser
  whose middle is over a stage and whose base is within 0.1 m of the
  stage's top is moved, raised and given a quarter turn with the stage,
  and the lights on the riser with it, when the stage's box is ticked. The
  notice says how many raised areas went. It is all one step of Undo.
- **Delete asks first** ("Keep it" / "Delete it"), in the row. Fixtures hung
  on a deleted truss stay where they are, and nothing snaps to it or is laid
  along it afterwards. Fixtures standing on a deleted raised area stay where
  they are too, and the question says so.
- **Undo**, bottom left, takes back the latest change to the room: a rename,
  a move, a resize, a change of kind or base height, an added item or a
  delete. One press, one change, latest
  first, up to the last 20. The button says what it will take back ("Undo:
  Stage resized (2 more)"). The steps are kept on the server beside the
  room, so they are still there after the page is loaded again or the
  dialog is closed. They are **gone once the scan is read again** (the room
  they belong to has been replaced) and when the room is removed. An undo
  cannot itself be undone. **A truss and the fixtures it took along are one
  step**: the button says so ("Undo: Truss 1 moved, with 4 fixtures"), and
  one press puts the truss and the fixtures back exactly where they were.
  A raised area and the fixtures standing on it are one step in the same
  way. A
  fixture that somebody has moved since is left where they put it, and the
  message says how many were left.
- **One change at a time.** Each stored change, and each one undone, comes
  back as the whole room, which the plan draws and snaps to at once; the rig
  is not loaded again, unless the change moved fixtures (a truss or a raised
  area that took its fixtures along, or an undo that put them back), when it is, and the
  editor's own Undo steps are dropped because they hold the old positions.
  A save or an added item keeps what is typed in the
  other rows; a delete or an undo clears all of it, because rows may have
  changed places.
- **An item the views cannot draw is still listed** ("Not drawn: ...") and can
  be renamed or deleted. One with no position stored has its Across, Depth
  and size fields off; its height can still be set.
- **Walls** (slice 16), under the rows: one row for each corner of the room's
  floor, in order round the room. Each wall runs from one corner to the
  next, and the last back to the first. A box room has four, numbered from
  upstage stage right, clockwise seen from above. Type where a corner goes
  (**Across** and **Depth**, as above) and press **Save**; **Add after**
  puts a new corner half way along the wall that leaves that corner, where
  it changes nothing until it is moved; **Delete** takes a corner out, and
  is off once the room is down to three. **Room height** and **Set height**
  set the ceiling (1.5 to 30 m). The section says how big the walls are,
  wall to wall, measured from the corners.
- **Walls that are not a room are refused**, with the server's words: walls
  that would cross or touch each other ("the wall from corner 2 to corner 3
  would meet the wall from corner 5 to corner 6"), two corners under 0.1 m
  apart, a room under 1 m either way or with less than 1 m2 of floor, a
  corner more than 100 m from the middle of the floor, more than 64 corners.
- **Nothing is moved to suit new walls.** No fixture, raised area, truss or
  ring moves when a wall does. What the walls and ceiling as they now stand
  leave outside them is **listed in the Walls section** instead, one line
  each: "Ring 1 (overhead ring) is partly outside the walls.", "Spot 4
  (fixture) is outside the walls and above the ceiling." One that was
  already outside before the change says so. On a wall, to the centimetre,
  is inside. The list is read when the dialog opens and after every change.
- **The middle of the floor stays where it was.** Every position in the rig
  is measured from it, so a room drawn out to one side is not centred again.
- **Drag corners on the plan** closes the dialog and puts a numbered handle
  on each corner in the 2D plan (**walls mode**). Drag a handle to move the
  corner: it goes to the grid unless the snap mode is None or Alt is held.
  A press that stays within 5 pixels moves nothing, as with a fixture. Each
  drag is one request and **one undo step**. A move the server refuses goes
  back, and the strip over the plan says why. While walls mode is on,
  fixtures are drawn faint and take no press, there is no selection box,
  and the keys and the nudge pad are off. The strip over the plan says what
  the last drag did and what is now outside the walls, and has **Undo** (the
  room's own), **Back to Edit Room** and **Done with walls**.
- **Arrange room items on the plan** (slice 19), over the rows, closes the
  dialog and lets the raised areas, truss lines and rings be picked up in
  the 2D plan (**items mode**). Only what the plan draws can be: an item
  listed as "Not drawn" is still edited in its row.
  - **Drag one to move it.** Its outline follows the pointer and the words
    over it say where its middle is; it goes to the grid unless the snap
    mode is None or Alt is held. A press that stays within 5 pixels moves
    nothing and only selects it. Each drag is **one request** (the same
    `PATCH` a row's Save sends, with the middle alone) and **one undo
    step**. Where the server puts it is what is drawn: a middle beyond the
    room is held to the 2 m round it, as from a row.
  - **The selected item has handles.** A truss line has a square one on one
    end for its **length**, which changes about its middle, to the grid's
    step and never under 0.5 m, and a round one past the other end for its
    **heading**, which turns it about its middle, to 5 degrees with the
    snap on and to a tenth of a degree without. A ring has a square one on
    its stage left side for its **radius**, to the grid's step and never
    under 0.3 m. Each drag of a handle is one request, with that one field,
    and one undo step. A raised area has eight (slice 20): one on each
    **corner** and one in the middle of each **edge**. An edge changes its
    width or its front to back and a corner both, **about its middle**,
    which stays where it is, to the grid's step and never under 0.3 m. The
    words over it say its two sides. Each drag is one request, with `width`,
    `depth` or both, and one undo step. On one that stands at a heading
    (slice 21) the handles stand on it as it is turned and pull along its
    own sides. It also has a round **rotate** handle on a stalk 0.6 m past
    the edge that is upstage when it stands square: drag it to turn the
    area about its middle, to 5 degrees with the snap on, to a tenth
    without, and to 15 with Shift held either way (a truss line's rotate
    handle takes Shift the same way). One request, with `heading_deg`, when
    it is let go. Its quarter turn is still the Turn button on its row.
  - **The height strip sets its heights** (slice 22). Beside the plan, for
    the whole of items mode, is a strip that shows the selected item from
    the side: the floor at the bottom, the ceiling as a dashed line, a
    scale in metres. A raised area has two handles, side by side: **Top**
    (its deck goes up or down and its underside stays; `height` is sent,
    the deck above its base) and **Base** (the whole of it goes up or down,
    as thick as it was; `base_height` is sent, 0 stands on the floor and
    more floats). A truss line or a ring has one, **Trim**, its underside.
    Drag a handle up or down: it goes to 0.05 m, or to 0.25 m with Shift
    held or with the strip's **Step** button pressed (the touch for Shift),
    and no further than the server allows (a deck 0.05 to 3 m with its top
    under the ceiling, a base 0 to 10 m, a truss 0.5 m to the ceiling). The
    handle and the line under the strip say the live value ("trim 4.50 m",
    "top 1.00 m", "base 2.70 m", "on the floor"). A press that stays within
    5 pixels changes nothing. Let go, it is **one request and one undo
    step**; the fixtures go with it as the item's box says, and a change
    the server refuses puts the handle back with the reason in the strip
    over the plan. With nothing selected the strip says what it is for.
  - **The arrow keys nudge the selected item** by the grid step, ten steps
    with Shift, up the plan being upstage. **One request and one undo step
    for each key press**: presses are not gathered into one, and a key held
    down does not repeat. Presses made faster than the server answers are
    sent one after another, each from where the one before left the item.
    Escape, or a click on empty floor, lets go of the item.
  - **Fixtures go with it as its box says.** The boxes ticked or unticked
    in the dialog are carried over, and the strip over the plan has the
    selected item's box ("Move the fixtures hung on it" / "standing on
    it"). When fixtures moved, the rig is read again, so the 2D plan and the
    3D view show them where they now are, and the editor's own Undo steps
    are dropped.
  - **A change the server refuses goes back**, and the strip says why in
    the server's words: a carry that would take a fixture out of the room
    (422), a size that cannot fit (422), a locate walkthrough running (409).
  - While items mode is on, fixtures are drawn faint and take no press,
    there is no selection box, and the plan's other keys and the nudge pad
    are off. The strip has **Undo** (the room's own), **Back to Edit Room**
    and **Done arranging**. Items mode and walls mode are never on together.
- **The walls share the room's Undo**: a moved, added or deleted corner and
  a changed height are each one step, with the other edits, latest first.
- **Not while a locate walkthrough is running.** Every change here, Undo
  included, is refused until Identify Lights is finished or ended on the
  rig, and the dialog shows the reason.
- **No tag changes, no patch is touched and nothing is sent to a light.**
  The only fixtures that move are the ones hung on a truss or ring, or
  standing on a raised area, that is moved, raised, lowered, turned or
  resized with its box ticked, and only
  their position and their heading (`rotation_y`) change: not their address,
  universe, mode, group or tags. A guess that is carried is still a guess,
  and a tapped fixture is still a tapped one. The editor's own Undo does not
  take a room edit back (the room has its own, above). "Undo room scan
  moves" keeps its record, but a fixture a truss or a raised area has
  carried no longer
  stands where the scan put it, so that undo leaves it alone as "moved since
  the scan". Reading the scan again **replaces the edits made here, but
  for a raised area's name, height and base height and a raised area you
  added where the scan has nothing** (slice 32; the DJ booth tick is kept
  too, slices 30 and 31), **a line's or ring's name and hanging height,
  one you added where the scan has no truss, and a raised area you
  deleted, which stays out** (slice 33), **as a line or ring of the scan's
  you deleted does** (slice 34), and does not put carried fixtures back.
  The question asked before a delete says so: "It stays deleted when the
  scan is applied again. Undo here brings it back, until then." For one
  added by hand it says what it always did ("Undo here brings it back,
  until the scan is read again."): the scan never read it.

## From a walkthrough video

A phone with no LiDAR and no scanning app can still film the room. **Room
Scan**, **Or a walkthrough video** sends the video to this system's backend,
which rebuilds the room from it with free tools installed on that machine and
hands the result to the same preview and apply as any scan file.

**A scanning app is still the better route** where one is available: Polycam
and Scaniverse give a measured mesh in a minute. A video gives a sparse cloud
with no scale, after several minutes of processor time. Use it when the video
is all there is.

### What has to be installed

| Tool | For | Licence | Needed |
| --- | --- | --- | --- |
| **ffmpeg** on PATH | reading frames out of the video | LGPL/GPL, run as a separate program | this, or OpenCV |
| OpenCV (`cv2`) importable by the backend | the same, when ffmpeg is missing | Apache 2.0 | fallback only; not in `requirements.txt` |
| **COLMAP** | turning frames into a point cloud | BSD | yes |
| OpenMVS (`DensifyPointCloud`, `InterfaceCOLMAP`) | a dense cloud where COLMAP's own cannot run | AGPL, run as a separate program | no |

Nothing is installed by this system. COLMAP: download a release from
<https://github.com/colmap/colmap/releases>, unpack it, and either put its
folder on PATH or set `COLMAP_PATH` in `backend/.env` to the folder (or to
`COLMAP.bat` or the `colmap` executable), then restart the backend. A
`COLMAP_PATH` that points at nothing is reported as "not installed"; PATH is not
searched instead.

With no COLMAP the dialog says so before anything is uploaded, with the
download address and the alternative (scan with Polycam or Scaniverse, export
OBJ or PLY). `GET /api/room-scan/video/tools` gives the same answer.

Settings (`backend/.env`): `COLMAP_PATH`, `OPENMVS_PATH`, `ROOM_VIDEO_MAX_MB`
(default 500), `ROOM_VIDEO_TIMEOUT_MIN` (default 60: the whole job is stopped
after that).

### Filming

One to two minutes, walking slowly round the whole room, lights up. Keep the
floor and the ceiling in shot some of the time, keep part of what you just
filmed in view as you turn, and do not let a blank wall fill the picture:
COLMAP needs things to recognise. Hold the phone the same way up throughout.
1080p is plenty; frames are shrunk to 1600 pixels on their long side.

### Give one measurement

A video carries no real size. Choose **Ceiling height** or **Length of the
longest wall** and type it in metres (1 to 200). It can be given before the
video or after: the scale is applied when the cloud is fetched, so changing the
measurement reads the room again in a moment without rebuilding it.

With no measurement the scale is **assumed**: the phone is taken to have been
held 1.5 m above the floor (or, where the cameras' height is no use, the
ceiling is taken to be 3 m). The preview then leads with a warning that every
size is a guess. Do not apply an assumed-scale room and trust its numbers.

### What the server does

`backend/app/services/room_scan/video.py`, run as a background job by
`video_jobs.py`. One job runs at a time; a second is refused with 409.

1. **Frames.** About `3 x 150` candidate frames are taken evenly through the
   video (at most 4 a second). A frame is dropped as *blurred* when its
   sharpness (variance of the Laplacian over a 512-pixel centre crop) is under
   half that of its neighbours, and as a *repeat* when it shows what the last
   kept frame showed (the phone stood still). Repeats are judged on the whole
   frame shrunk to 32 by 32, against that frame's own contrast, so a blank
   wall in the middle of the picture or a dim room is not taken for a phone
   standing still. At most 150 are kept, the sharpest of each stretch. Fewer
   than 12 is refused with advice on filming. A video filmed upright (sideways
   pixels plus a rotation recorded beside them) comes out upright from both
   ffmpeg and OpenCV; that is tested.
2. **COLMAP**: `feature_extractor` (one camera for all frames),
   `exhaustive_matcher` up to 100 frames or `sequential_matcher` beyond,
   `mapper`, then `model_converter` to text. If the first two fail they are
   tried again asking for the CPU. Where the mapper writes several models, the
   one holding the most frames is used. COLMAP runs as a separate process at
   low priority with no window, and is killed (with anything it started) when
   the job is stopped, runs out of time, or the backend shuts down.
3. **Dense**, only when asked: COLMAP's `patch_match_stereo` and
   `stereo_fusion` (these need an NVIDIA card with CUDA), else OpenMVS where it
   is installed. Any failure falls back to the sparse cloud, with a note.
4. **Strays.** A reconstruction leaves a few percent of its points nowhere
   near the room (a bad match, a reflection, something seen through a door).
   Everything after this measures the room by where its points end, so a point
   whose sixth-nearest neighbour is three times further off than is usual in
   the cloud is dropped first. Without this a cloud with 3% strays read as a
   room a third of its real width.
5. **Up.** A photogrammetry model has no up. The average of every frame's
   image-down is close to gravity; from there the direction is searched (within
   24 degrees) for the one across which the cloud is thinnest, which is the one
   square to the floor and ceiling. The cloud is turned so that is +Y.
6. **Scale**, when the cloud is fetched: the floor and ceiling (and for a wall
   measurement the walls) are found with the scan reader's own code, and the
   cloud is scaled so the measured thing is the size given.

The cloud is written as a binary PLY in metres, Y-up, whose header carries
what is known about it (`comment room_scan_note ...`,
`comment room_scan_warning ...`, `room_scan_up_axis`,
`room_scan_metres_per_unit`). The PLY reader takes those into the preview's
"How the scan was read" and warnings, so they survive the cloud being
downloaded and sent back. Other PLY comments are ignored as before.

The video, its frames and COLMAP's database are deleted when the job ends,
however it ends. The finished cloud is kept in memory for two hours (the four
most recent), and not across a restart.

### The video API

| Route | Does |
| --- | --- |
| `GET /api/room-scan/video/tools` | what is installed: `ready`, `frames`, `photogrammetry`, `dense`, `message` (what to install; null when ready), `max_upload_mb` |
| `POST /api/rigs/{rig_id}/room-scan/video?filename=walk.mp4&quality=sparse` | starts a job. **The request body is the video itself**, not a form, so the size limit acts while it arrives. Answers `202` with the job |
| `GET /api/rigs/{rig_id}/room-scan/video/{job_id}` | the job: `state` (`queued`, `running`, `done`, `failed`, `cancelled`), `stage`, `stage_label`, `detail`, `progress` (0 to 1, by stage), `elapsed_s`, `error`, `tools`, `frames`, `cloud`, `notes`, `warnings` |
| `GET /api/rigs/{rig_id}/room-scan/video/{job_id}/cloud.ply?ceiling_height=4.2` | the finished cloud, scaled. Or `longest_wall=`; with neither the scale is assumed (`X-Room-Scale-Assumed: true`) |
| `DELETE /api/rigs/{rig_id}/room-scan/video/{job_id}` | stops a running job, or forgets a finished one |

The `cloud.ply` is then sent to `POST /api/rigs/{rig_id}/room-scan` like any
scan file, for the preview and again to apply. No route here writes to a rig.

| Status | When |
| --- | --- |
| 200 with `state: "unavailable"` | the video was sent to a machine with no COLMAP (or no frame reader). `error` says what to install or do instead. Not an error status: nothing went wrong |
| 400 | the name is not a video's (`.mp4 .mov .m4v .avi .mkv .webm .3gp`), the body is empty, both measurements were given, or the measurement is outside 1 to 200 m |
| 404 | no such rig; or no such job **on that rig** (a job is only answered for under the rig it was started for) |
| 409 | another video is being processed; or `cloud.ply` was asked of a job that is not `done` |
| 413 | the video is over the limit (checked from `Content-Length` first, and again as the bytes arrive) |

A job that fails says why in `error`, in words for the operator: which COLMAP
step failed and the end of its output, that the frames could not be joined
(with how to film again), that too few frames or points came out, or that it
ran out of time. Each ends by naming the alternative, a scanning app's OBJ or
PLY.

## The API

All routes need the operator login, like every other `/api` route.

### `POST /api/rigs/{rig_id}/room-scan`

Multipart upload, field `file`: `.obj`, `.ply`, `.glb`, `.gltf`, `.usdz`,
`.usda`, `.usdc` or RoomPlan `.json`, or a `.zip` of one of those with the
files that go with it. The reader is chosen from the file's
first bytes (`glTF` for a GLB, `ply`, a zip's `PK`, `#usda`, `PXR-USDC`), and
from its name only when the bytes do not say. A `.gltf` is JSON, as RoomPlan's
file is: it is known by its name, or by the `asset` every glTF carries when it
is named `.json`. A USDZ is a zip too: an archive named `.usdz` goes to the
USDZ reader, and an archive under any other name is read as a zip that holds
a scan (slice 26). The answer's `format` is `obj`, `ply`, `glb`, `gltf`, `usda`,
`usdc` or `roomplan`; for a zip it is the format of the model read out of it,
`file` is the zip's name, and `assumptions` begins with which file that was.
Query parameters:

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
  `suggested: true`. A move onto a stage that stands at a heading also has
  `turn_deg` (slice 27): the degrees the fixture is turned with the stage,
  clockwise seen from above, which apply takes off its `rotation_y`. A move
  that turns nothing has no `turn_deg`. The dialog shows it in the table's
  Turn column (slice 29).
- `applied`: `null` for a preview. After apply: `room_shell_stored`,
  `fixtures_moved`, `fixtures_still_unconfirmed` and a message. Where the
  room it replaced had a raised area marked as the DJ's booth (slice 30),
  also `dj_booth` (the place in the new `risers` of the raised area that
  keeps the mark, or null), `dj_booth_dropped` (true when none does and the
  mark is gone), `dj_booth_overlap` (the intersection over union it was
  kept at, or null) and `dj_booth_message` (the sentence for the
  operator). A room with no marked booth has none of the four. Where a
  kind set by hand was kept against what the scan read there, also
  `dj_booth_kind_kept` (that kind; absent otherwise, slice 31). See "What
  slice 30 built" for the rule.
- `dj_booth_mark` (slice 31): **in a preview only, and only where the room
  already stored has a marked DJ booth**; what applying would do to the
  mark. `kept` and `dropped` (one of them true), `index` (the place in
  `risers` of the raised area that would keep it, or null), `name` (what
  that raised area is called, or null), `overlap`, `kind_kept` (a kind set
  by hand that would be kept against the reading, or null) and `message`
  ("The DJ booth mark will be kept on Riser." / "The DJ booth mark will be
  dropped: no raised area in this scan stands where DJ does. Mark the DJ
  booth again in Edit Room after applying."). The `room_shell` of a preview
  is the room apply would store: it carries the kept mark, and a kept kind.
  Nothing is written.
- `hand_edits` (slice 32): **at the top of a preview, and inside `applied`
  after an apply, and in either only where there is something to say**:
  what is kept of the edits made by hand to the stored room's raised
  areas. A room with none has no such key, and every other key is what it
  was.
  - `kept`: one entry for each raised area of the new room that keeps a
    hand edit: `index` (its place in `risers`), `name`, `edits` (which of
    `"name"`, `"height"`, `"base_height"`) and `overlap` (the intersection
    over union it was matched at).
  - `areas`: how many entries `kept` has.
  - `added_kept`: the raised areas added by hand that are kept as they
    were, each `index` (at the end of `risers`) and `name`.
  - `added_replaced`: the ones added by hand that the scan now has
    something in the place of, each `name`, `by_index` and `by` (the
    scan's raised area that overlaps it most, and what that is called).
  - `message`: the sentence for the operator ("Will keep your edits on 2
    raised areas: Stage (base height), Drum riser (name, height). 1 raised
    area you added will be kept as it is: Podium."; "Kept ..." and "was
    kept" in `applied`).
  - The preview's `room_shell` and `summary.raised_areas` are of the room
    with all of it carried. See "What slice 32 built" for the rule.
  - Five more keys (slice 33), **each sent only when it has something in
    it**, so an answer about raised areas alone has the five keys above and
    no other. Any one of them is enough for `hand_edits` to be sent.
    - `overhead_kept`: one entry for each overhead line or ring of the new
      room that keeps a hand edit: `kind` (`truss_lines` or `truss_rings`,
      the list `index` is a place in), `index`, `name`, `edits` (which of
      `"name"`, `"height"`: the height it hangs at) and `overlap`.
    - `overhead_added_kept`: the lines and rings added by hand that are
      kept as they were, each `kind`, `index` (at the end of its list) and
      `name`.
    - `overhead_added_replaced`: the ones added by hand that the scan now
      has one in the place of, each `kind`, `name`, `by_index` and `by`.
    - `deleted_left_out`: the raised areas of this scan left out of the
      room because a person deleted them from the room it replaces, each
      `name` (what it was called when it was deleted), `kind` and `overlap`.
      They are not in the preview's `room_shell` or its
      `summary.raised_areas`; the room's `deleted_areas` lists them.
      **Overhead lines and rings are listed here too** (slice 34), with
      `kind` `"truss_lines"` or `"truss_rings"` where a raised area has
      `"stage"`, `"riser"` or `"booth"`; they are not in `room_shell`,
      `hanging_bands` or `summary.overhead_lines`. `message` says each
      kind in its own sentence ("Left out 1 overhead line you deleted:
      Overhead line 1.").
    - `warnings`: what is kept that the new room does not hold, each
      `kind` (`risers`, `truss_lines` or `truss_rings`), `index`, `name` and
      `reason` ("above the ceiling", "outside the walls", "partly outside
      the walls", or two of them joined by "and"). It is kept all the same.
    - `message` says all of it, in this order: left out, kept, added and
      kept, replaced, to check ("Will leave out 1 raised area you deleted:
      Riser. Will keep your edits on 1 overhead line: Front truss (name,
      hanging height). Check Podium: it is outside the walls of the room as
      this scan reads it.").
  - `items` (slice 35), **sent only when it has something in it**: all of
    the above one thing at a time, in the order `message` says them (left
    out, kept, added and kept, replaced; within each, raised areas, then
    lines, then rings). Each entry has exactly three keys:
    - `kind`: `"raised area"`, `"line"` or `"ring"`;
    - `name`: what it is called (for one replaced or left out, what the
      person's was called);
    - `outcome`: `"kept your edits"`, `"left out (you deleted it)"`,
      `"replaced (a scanned item overlaps it)"`, `"added by hand, kept"` or
      (slice 36) `"lost"`.
      The same words in a preview and in `applied`.
  - `warnings` also names **what was lost** (slice 35), after the checks.
    These entries have **no `index`** (the thing is not in the new room)
    and each has its own `message`, which `hand_edits.message` ends with.
    Any one of them is enough for `hand_edits` to be sent, with `areas` 0
    and the lists empty.
    - `reason` `"hanging height"`: a line or ring whose name or trim was
      set by hand matched nothing, and the scan read one over the same plan
      more than 1.0 m from where it read this one. `kind` (the list),
      `name`, `edits`, `read_height` (where the scan read that one), `trim`
      (the height stored on this one) and `scan_height` (where the scan
      last read this one, or null). "The scan read a truss at 2.8 m where
      Front truss was, against its trim of 3.5 m (the scan read it at 4 m
      before): more than 1 m from where the scan read it before, so its
      name and trim were not kept."
    - `reason` `"read beside"`: the same, where the scan read one that
      shares some of the plan with it but less than the half a match needs.
      `offset` (metres between the two middles) and `overlap`. "The scan
      read a truss 0.3 m from where Front truss was, sharing 33% of the
      plan with it where half is needed, so its name was not kept."
    - `reason` `"record dropped"`: the record of a deleted raised area,
      line or ring matched nothing in this scan and is gone. `kind` and
      `name`. "The scan did not see Riser; the record that keeps it deleted
      was dropped, so it may come back on a later scan."
    - A preview says "will not be kept" and "will be dropped".
    - Since slice 36 also: `"read beside"` for a **raised area** (with
      `by_index` and `by`, the new area); `"no longer read"` for a line or
      ring the scan reads nothing near ("The scan no longer reads Front
      truss; its name and trim went with it."); and `"another has it"` for
      the one of two stored items that pick one new item that does not get
      it (`kept`, `read`, `by_index`, `by`: "Near and Nearer both stand
      where the scan reads Riser: Nearer has it, so the name of Near was not
      kept."). Each of the three is in `items` with the outcome `"lost"`.
  - `carry_over` (slice 36), **sent only when it has something in it**: one
    entry for each loss with an item of the new room behind it ("hanging
    height", "read beside", "another has it"; not "no longer read" or
    "record dropped"): `kind` (the list), `old_name`, `old_trim_or_height`,
    `old_base_height` (raised areas), `edits`, `new_index`, `new_name`,
    `reason`, `warning` (its place in `warnings`) and, since slice 37,
    `warning_id` (the `id` of its warning, which the dialog matches by).
    POST `.../room-scan/carry-over` takes one as it is, and
    `.../room-scan/carry-over/all` a list. With `apply=true` the entries
    are also kept with the stored room as `room_shell.pending_carry_over`
    (each with its warning's `message`), in the answer's `room_shell` too.

Refusals, each with a `detail` that says what to do:

| Status | When |
| --- | --- |
| 400 | the file is not a scan this reads (a binary USD layer that cannot be read: the reason, then "export OBJ from Polycam or Scaniverse"; a glTF packed with Draco or meshopt: "export the scan again without Draco or mesh compression, or export OBJ"; a `.gltf` sent without its `.bin`: "zip the two together ... and send the zip, or export the scan as .glb"; a zip with a name that points outside it, a password, more than 2,000 files, more than 200 MB unpacked, no model in it, or a `.gltf` whose `.bin` is not in it), is cut short or damaged, has no triangles or points, has more than 20 million points or 40 million triangles, or is not a room at any plausible units; or `rotate` is not a quarter turn |
| 404 | no such rig |
| 409 | `apply` would move fixtures while a locate walkthrough is running on the rig. Finish or end it first. A preview, and an apply with `move_fixtures=false`, are still answered |
| 413 | the file is over 200 MB |
| 422 | `units` or `up_axis` is not one of the values above |

### `DELETE /api/rigs/{rig_id}/room-shell`

Takes the stored room off the rig, and with it the record of edits to it
that could be undone. Fixtures are left where they are unless
`restore_fixtures=true`, which also puts back the ones the scan moved. Answers
`rig_id`, `removed`, `undo_available` and, when asked to restore,
`fixtures_restored`, `fixtures_skipped`, `skipped_fixtures` and a `message`.

### `PATCH /api/rigs/{rig_id}/room-shell/{kind}/{index}`

Renames, moves, resizes, raises or turns one raised area, overhead line or
ring of the stored room (`services/room_scan/edit.py`), makes a raised area
another kind or floats it on a base height, and takes the fixtures hung on a
line or ring, or standing on a raised area, along
(`services/room_scan/carry.py`). `kind` is the list it is stored in: `risers`,
`truss_lines` or `truss_rings`. `index` is its place in that list, from 0. The
lists carry no ids, and the views leave out items they cannot draw, so this is
the place in the stored list and not the place on the plan.

JSON body, every field optional; anything left out (or `null`) is kept:

| Field | Meaning |
| --- | --- |
| `name` | the new name. Runs of spaces and line breaks become one space and the ends are trimmed; what is left must be 1 to 60 characters |
| `center_x` | where the middle goes across the room, in metres (the rig's axes) |
| `center_z` | where the middle goes in depth, in metres, -Z upstage |
| `width`, `depth` | `risers` only: its size along X and along Z, or along its heading and square to it when it has one, each from 0.3 m |
| `length` | `truss_lines` only: end to end, from 0.5 m |
| `heading_deg` | `truss_lines`, and `risers` since slice 21: degrees clockwise from across the room seen from above, -360 to 360. Stored over -90 and up to 90, to a tenth: a line has no front, and a rectangle looks the same after half a turn. A raised area that stores none stands square to the room (0) |
| `radius` | `truss_rings` only: to the middle of the truss, from 0.3 m |
| `height` | a raised area's deck above its base, 0.05 to 3 m with its top under the ceiling; the underside of a line or ring, 0.5 m to the ceiling (`room.height`; 30 m where the room has none) |
| `base_height` | `risers` only (slice 18): how far its underside is above the floor, 0 to 10 m, with its top (`base_height + height`) under the ceiling. 0 stands on the floor |
| `riser_kind` | `risers` only (slice 18): `stage`, `riser` or `booth`. Its place in the list is kept |
| `is_dj_booth` | `risers` only (slice 28): `true` marks it as the DJ's booth and takes the mark off any other; `false` takes it off this one. A change of `riser_kind` sent without it takes the mark off |
| `carry_fixtures` | whether the fixtures hung on a line or ring, or standing on a raised area (slice 18), go with it. `true` when left out or `null`. Not a change by itself: sent alone it is refused like an empty body |

- **The fixtures hung on a line or ring go with it** (slice 17,
  `services/room_scan/carry.py`) unless `carry_fixtures` is `false`:
  - *Hung on it* is within 0.3 m of the line (between its ends) or of the
    ring's circle on the plan, and within 0.6 m of its `height`: the reach
    the 2D plan's rows and the 3D view go by (`HANGER_REACH`,
    `HANGER_HEIGHT_WINDOW`). A fixture within reach of two of the room's
    lines and rings hangs on the nearer, and on the one listed first (lines
    before rings) when they are as near. Every fixture of the rig is looked
    at, whatever its tags or group.
  - *Where it goes* is worked out from the item as it was stored and as the
    edit stored it, not from the request, so a middle that was held or
    brought in is the one followed. A move shifts it by the middle's shift.
    A height adds the change in height. A turn swings it about the line's
    middle by the smaller of the two turns that give the new heading (at
    most 90 degrees either way: a line has no front) and takes that turn
    off its `rotation_y`, which runs the other way round from a heading. A
    length scales how far along the line it is from the middle, and keeps
    how far to the side. A radius keeps its angle round the ring and how
    far inside or outside the truss it is. Positions are stored to the
    millimetre; a fixture that would shift by under half a millimetre is
    left exactly as it was.
  - **Only `position_x`, `position_y`, `position_z` and (for a turn)
    `rotation_y` are written.** No address, universe, mode, group or tag.
  - **Refused whole, with 422**, when any carried fixture would end up past
    the room's box (`room.width`, `room.depth`) and the 2 m round it, more
    than 2 m above `room.height`, or below the floor: nothing is written,
    the item included. The `detail` names up to three of the fixtures and
    where they would have gone. A room with no size along an axis holds
    nothing along it.
  - A rename and an edit that changes nothing carry nothing.
- **The fixtures standing on a raised area go with it** (slice 18, the same
  file) unless `carry_fixtures` is `false`:
  - *Standing on it* is over its footprint on the plan or within 0.15 m of
    its edge, and from 0.05 m under its top to 0.6 m above it
    (`STAND_MARGIN_M`, `STAND_UNDER_M`, `STAND_WINDOW_M`); its top is
    `base_height + height`. A fixture that hangs on any line or ring of
    the room by the rule above stands on nothing. One over two raised areas
    stands on the one whose top it is nearer, and on the one listed first
    when they are as near. A raised area with a number missing, or no size,
    is stood on by nothing.
  - *Where it goes*, again from the item as stored before and after: a
    move shifts it by the middle's shift; a `height` or a `base_height`
    adds what the top moved; a `width` or `depth` keeps its place as a
    share of the footprint, measured from the middle. **A quarter turn**
    is a `width` and `depth` that changed places (and differ): the fixture
    is swung a quarter turn clockwise seen from above about the middle,
    and 90 degrees comes off its `rotation_y`. That is all a quarter turn
    is to the server, so the same two numbers typed by hand are one too.
  - The same fields only are written, and the same refusal (422, nothing
    written) applies, with "standing on" in its words. A rename, a change
    of `riser_kind` and an edit that changes nothing carry nothing.
- **The raised areas standing on a raised area go with it too** (slice 20,
  `stood_areas`, `carried_areas`), unless `carry_fixtures` is `false`:
  - *Standing on it* is the middle of its footprint inside the other's
    footprint (the edge counts) and its base within 0.1 m of the other's
    top (`STACK_BASE_WINDOW_M`). One standing on one of those is taken too:
    the whole stack above goes as one piece. The edited area is never one
    of them, and one with a number missing stands on nothing. All of it is
    read from the room as it was before the edit.
  - *Where each goes*: a move shifts it by what the edited area's middle
    shifted (a middle a resize brought in included); a `height` or a
    `base_height` adds what the top moved to its `base_height`, never to
    under the floor; a quarter turn swings its middle a quarter turn
    clockwise seen from above about the edited area's middle and swaps its
    `width` and `depth`. **A resize alone moves none of them.** One that
    shifts is marked "Moved by hand.", and one whose base changes "Resized
    by hand.".
  - *The fixtures standing on each* go with it, worked out as for the
    edited area. They turn with a quarter turn even on a square platform,
    whose own sides cannot say it was turned. A fixture stands on one area
    only, so none is moved twice.
  - *Refused whole* (422, nothing written) when a carried area's middle
    would be past the room's box and the 2 m round it, its top above the
    ceiling, or its base above 10 m; or when a fixture standing on one
    would leave the room, with that area named. The ceiling and the 10 m
    are stricter than "the box and 2 m": they are what its own row is held
    to, so a carried area can always be saved again.
  - The edited area, the areas above it and every fixture are **one undo
    step**: the step holds the whole room as it was, and the fixtures.
- **A raised area's `heading_deg`** (slice 21, `area_heading`,
  `area_turn`) stands it at any heading, about its middle:
  - It is stored folded, to a tenth of a degree, and a turn under a tenth
    is no change. One that stores none stands at 0, so 0 (or 180) sent for
    it changes nothing. A changed heading counts as a resize ("Resized by
    hand."), and the undo label says "turned".
  - *The whole of it is held as it stands*: its reach either side of its
    middle is worked out at its heading (`area_reach`), for the turn and
    for every later resize, and one too long for the room the way it would
    stand is refused (422).
  - *Standing on it* is over its footprint as it stands, for fixtures and
    for raised areas, measured along its own width and depth.
  - *What stands on it is swung about its middle by the turn*, and each
    fixture's `rotation_y` turned with it. A change of heading is taken as
    the smaller of the two turns that give it (from 80 to -80 is 20 degrees
    clockwise, not 160 back). A turn to 90 swings what a quarter turn told
    by the sides swings, and sides swapped with a heading changed in one
    request are both turns, added. A resize of a turned area keeps each
    fixture's share along the area's own sides.
  - *A raised area standing on it* is swung the same way and its own
    `heading_deg` is turned by as much, so it stays as square to what it
    stands on as it was. Its `from` and `to` in `items_moved` then carry
    `heading_deg` (only for one that has a heading before or after).
  - What the walls leave outside (the outline route's list) goes by its
    four corners where they stand (`area_corners`).
- **`riser_kind`** changes the item's `kind` where it is in its list. An
  item whose name is still what its old kind is called ("Riser") is named
  what the new kind is called, unless a `name` is sent with it; any other
  name is kept. It gets `suggested: false` and "Kind set by hand." added to
  its `basis`, once. The kind it already is changes nothing. No fixture is
  moved.
- **Which field was set by hand** (slice 32 for raised areas; slice 33 for
  overhead lines and rings, see the end of this point). The
  `basis` of a raised area also gets, once each: **"Name set by hand."**
  when a `name` is sent that differs from the one it has (`suggested` is
  left as it is: a rename does not make its place a person's);
  **"Height set by hand."** when its `height` changes; **"Base height set
  by hand."** when its `base_height` changes (both beside "Resized by
  hand."). These are what a scan applied again reads to keep the name and
  the heights. "Resized by hand." alone covers a width, a depth and a
  heading as well and says none of the three. **A line and a ring get the
  first two** (slice 33): "Name set by hand." when a `name` is sent that
  differs, with `suggested` left as it is, and "Height set by hand." beside
  "Resized by hand." when the `height` it hangs at changes. A length, a
  radius, a heading and a move leave neither. They have no base height.
  **The first time a line's or ring's `height` is set by hand it also gets
  `scan_height`** (slice 34): the height it had, which is where the scan
  read it. A scan applied again matches by that, not by the trim. Not
  written for one added by hand, and not changed by a second trim.
- **`base_height`** is stored to the millimetre and set before the height,
  whose limit goes by it (`ceiling - base_height`, at most 3 m). A top that
  would be above the ceiling is refused (422, "Give it a lower base or a
  lower height."). A changed base counts as a resize ("Resized by hand.");
  the undo label says "raised" or "lowered". An item stored with no
  `base_height` stands on the floor, and 0 sent for it changes nothing.
- The middle is a raised area's or a ring's own centre, and for a line half
  way between its two ends. One of `center_x` and `center_z` given alone keeps
  the other.
- A position beyond the room is **held, not refused**: to the room's box
  (`room.width`, `room.depth`; not the floor outline) and 2 m round it. A room
  with no size holds nothing. The result is stored to the millimetre.
- A moved line keeps its length and heading: both ends take the same shift.
- An item that actually shifts gets `suggested: false` and "Moved by hand."
  added to its `basis`, once however often it is moved. A rename, and a move
  to where it already is, change neither.
- **A size changes about the middle.** A line is made longer or shorter
  along the way its two ends run (not along its heading rounded to a tenth),
  and turned about its middle; its ends are written as a scan writes them,
  from stage right to stage left, or from upstage to downstage, and its
  `length`, `heading_deg` and `axis` (`x` within 2 degrees of across, `z`
  within 2 of upstage to downstage, else `angled`) are written again.
- **With a size or a heading, the whole item is held**, not only its middle:
  it may reach no further than the room's box and the 2 m round it. A size
  that cannot fit there wherever its middle is put is refused (422); else
  the middle is brought in until the rest fits, which counts as a move. A
  plain move still holds only the middle, so an item can be moved until half
  of it is past the margin. A room with no size allows up to 100 m.
- **A height moves a truss's `top` with it** (it stays as deep as it was),
  and the truss or ring is counted again in `hanging_bands`: taken out of
  the band it was in (a band left empty is dropped) and counted in the band
  whose range takes in the new height, or in a new band of its own
  (`suggested: false`, `basis` "by hand: ...") where none does. A raised
  area's height leaves the bands alone, as a size and a move do.
- An item whose size, height or heading actually changes gets `suggested:
  false` and "Resized by hand." added to its `basis`, once. A value it
  already has changes nothing.
- A size field that is not this list's (`radius` on a raised area) is
  refused, not ignored. A raised area's quarter turn is still its `width`
  and `depth` swapped; any other turn is its `heading_deg` (slice 21).

Answers `rig_id`, `kind`, `index`, `item` (the item as stored), `room_shell`
(the whole stored room after the change), `changed` (false when what was
sent is what was stored: nothing is written and no step is left to undo),
`undo` (`available`, `label`: see the undo route), `riser_kind` (what a
raised area now is; null for a line or ring), `first_stage` (the place in
`risers` of the first raised area that is a stage, the one a suggestion puts
floor lights on, or null), `dj_booth` (slice 28: the place in `risers` of
the raised area marked as the DJ's booth, or null; sent as `is_dj_booth`
true or false, see "What slice 28 built"), `carry_fixtures` (whether
fixtures were to go with it), `fixtures_moved` (each carried fixture's
`rig_fixture_id`, `name`, `from` and `to`, each `x`, `y`, `z` and
`rotation_y`; empty when none moved; the fixtures standing on a carried
raised area are among them), `items_moved` (slice 20: each other raised
area that went with a raised area, `kind` (`risers`), `index`, `name`,
`from` and `to`, each `center_x`, `center_z`, `width`, `depth` and
`base_height`; empty when none did, and always for a line or ring) and a
`message` ("4 fixtures hung on Truss 1 moved with it.", "3 fixtures standing
on Stage moved with it.", "4 fixtures standing on Stage, or on what stands
on it, moved with it. 1 raised area standing on it moved with it too.").
When fixtures or raised areas moved, the undo step's label says so ("Truss 1
moved, with 4 fixtures", "Stage moved, with 1 raised area and 4 fixtures"),
and a client holding the rig should read it again when fixtures did.

Refused with 409 while a locate walkthrough is running on the rig, before
anything else about the request is looked at, as every room edit is.

### `POST /api/rigs/{rig_id}/room-shell/{kind}`

Adds a raised area, overhead line or ring by hand (slice 15). `kind` is the
list it goes in. Answers 201.

| Field | Meaning |
| --- | --- |
| `center_x`, `center_z` | where its middle goes. Needed |
| `width`, `depth`, `height` | `risers`: all three needed |
| `riser_kind` | `risers` only: `stage`, `riser` or `booth`. A riser when left out or empty |
| `is_dj_booth` | `risers` only (slice 28): `true` adds it as the DJ's booth and takes the mark off any other. The answer, like the DELETE's, carries `dj_booth`: the marked place or null |
| `base_height` | `risers` only (slice 18): as for `PATCH`. On the floor (0) when left out |
| `length`, `height` | `truss_lines`: both needed |
| `heading_deg` | `truss_lines`: across the room (0) when left out. `risers` (slice 21): square to the room when left out or 0, and then not stored |
| `radius`, `height` | `truss_rings`: both needed |
| `name` | as for `PATCH`. Left out, it is called what it is: "Stage", "Riser", "Booth or counter", "Overhead line 3", "Overhead ring 1" |

- The limits are those of `PATCH`, and the whole item is held inside the
  room's box and the 2 m round it in the same way.
- A raised area's `base_height` is refused as the `PATCH`'s is (slice 20):
  a number from 0 to 10 m, and a top above the ceiling in the same words
  ("Give it a lower base or a lower height."). Its `height` is held to what
  a deck can be (0.05 to 3 m), whatever the base. Edit Room's Add form
  sends it only for a platform that floats.
- It goes **at the end of its list**, so no other item changes place. A
  shell stored before rings were read gets its `truss_rings` list. A list
  holds at most 50.
- It is stored with `added_by_hand: true`, `suggested: false` and `basis`
  "Added by hand.": a person's, not the scan's. A raised area stands on the
  floor (`base_height` 0) unless a `base_height` is given. A truss or ring is taken to be 0.3 m deep and
  0.3 m across (`top`, `across`), and is counted in `hanging_bands` as a
  raised one is.

Answers `rig_id`, `kind`, `index` (its place: the last), `item`,
`room_shell`, `undo` and a `message`.

### `GET` and `POST /api/rigs/{rig_id}/room-shell/undo`

`POST` takes back the latest edit made by the three routes above and the
`DELETE` below: one edit for each call, latest first (slice 15). The whole
room goes back to what it was before that edit, so a deleted item is in its
old place in its list and the hanging bands are what they were. No body.
Answers `rig_id`, `undone` (what was taken back: "Stage renamed"),
`room_shell`, `undo`, `fixtures_restored`, `fixtures_skipped`, `outside` and
a `message`. An undo cannot itself be undone.

**The fixtures the undone edit carried go back with it** (slice 17): each
to exactly the position and `rotation_y` it had (`fixtures_restored`, with
`from` where it stood and `to` where it is again). A fixture is put back
only while it still stands, to 5 mm, where the edit left it. One somebody
has moved since, or that is no longer in the rig, is left alone and listed
in `fixtures_skipped` with the `reason` ("it was moved since"), as the
scan's own undo does: an undo takes back the edit, not what was done after
it. No tag is touched either way. `outside` is worked out after the
fixtures are back. The same goes for the fixtures that stood on a raised
area (slice 18); the `message` then says "put back where they stood before
it".

`GET` writes nothing and answers `rig_id`, `available` (how many edits can
be undone) and `label` (what the next undo takes back, or null). The rig
itself carries the same two as read-only `room_shell_edits`, which is how
the dialog knows what its Undo button does when the page is loaded again.

The record is `rigs.room_shell_undo` (JSON, migration
`008_rig_room_shell_undo`; additive and nullable): `steps`, oldest first,
each with a `label`, an `at` and the whole `shell` as it stood before that
edit, and, where the edit carried fixtures, `fixtures`: the list the edit
answered as `fixtures_moved`, with `kind`, the list the edited item is in
(slice 18; a step stored before it has none and reads as a truss's). Whole rooms are kept, not the edits run backwards: a room is a few
kilobytes, and a delete moves places and can drop a band. Only the last 20
steps are kept. The rooms are not sent with the rig. The record is
**emptied when a scan is applied** (a preview leaves it) **and when the room
is taken off**; an edit that is refused, or that changes nothing, leaves no
step.

### `DELETE /api/rigs/{rig_id}/room-shell/{kind}/{index}`

Takes one item out, addressed the same way. No body. The items after it in
its list **move up one place**. A deleted line or ring is also taken out of
the `hanging_bands` entry that counted it: a band left with nothing in it is
dropped, and with no line or ring left in the room there are no bands at all.
Deleting a raised area leaves the bands alone. The undo route brings the item
back to the place it had. Reading the scan again replaces every edit but
those slices 32 to 34 keep.

**A deleted raised area that the scan read is remembered** (slice 33), so
that reading the scan again does not bring it back. The room gets a
`deleted_areas` list with one small record for it: `kind`, `name`,
`center_x`, `center_z`, `width`, `depth`, `heading_deg` where it stood at a
heading, and `basis: "Kind set by hand."` where its kind was a person's. The
key is stored only when there is a record, and holds 50 at most (the oldest
goes). A raised area **added by hand** leaves no record when it is deleted:
the scan never read it.

**So is a deleted overhead line or ring that the scan read** (slice 34), in
the same `deleted_areas` list. A line's record has `name`, `x1`, `z1`,
`x2`, `z2`, `across` where it stored one, and `height`; a ring's has
`name`, `center_x`, `center_z`, `radius` and `height`. Neither has a
`kind`: a record with ends is a line's and one with a radius is a ring's.
`height` is where the scan read it (`scan_height` where a trim was set by
hand), and is left out where what was stored does not say (a trim set
before slice 34). One added by hand leaves no record.

A record is part of the room, so:

- the **room's Undo** that puts the area back takes the record away (it puts
  back the whole room as it was before the delete);
- **taking the room off the rig** (`DELETE .../room-shell`) takes the records
  with it, so a scan applied to a rig with no room reads everything;
- every other edit to the room keeps them.

What a scan applied again does with a record is in "What slice 33 built"
and "What slice 34 built".

Answers `rig_id`, `kind`, `index`, `removed` (the item taken out),
`room_shell`, `undo` and a `message` ("... was taken out of the stored room.
No fixture was moved.").

### The walls: `/api/rigs/{rig_id}/room-shell/outline`

Five routes on the room's walls (slice 16, `services/room_scan/outline_edit.py`).
A corner is `[x, z]` in metres in the rig's axes (X across, -Z upstage);
`{ "x": .., "z": .. }` is taken too. A corner's `index` is its place in the
outline, from 0. A box room, which stores no outline, has four: from
upstage stage right, clockwise seen from above.

| Route | Body | What it does |
| --- | --- | --- |
| `GET .../room-shell/outline` | none | The walls and what they leave outside. Writes nothing |
| `PATCH .../room-shell/outline` | `corners` (every corner, in order), `height` (floor to ceiling); either may be left out | Redraws the walls, sets the height, or both |
| `PATCH .../room-shell/outline/corners/{index}` | `x`, `z`; one given alone keeps the other | Moves one corner |
| `POST .../room-shell/outline/corners` | `after` (a corner's index), and `x` and `z` together or neither | Adds a corner on the wall that leaves corner `after`: at `x`, `z`, or half way along it. Answers 201 |
| `DELETE .../room-shell/outline/corners/{index}` | none | Takes one corner out: its two walls become one |

What makes a room, checked in this order, each refusal a sentence (422):

- 3 to 64 corners, each two finite numbers, to the millimetre;
- no corner more than 100 m from the origin either way (so the room is at
  most 200 m a side);
- no two neighbouring corners under 0.1 m apart, and no wall over 200 m;
- no wall crossing or touching another, and none doubling back along its
  neighbour. Three corners in a straight line are let through: a corner
  added half way along a wall is exactly that;
- at least 1 m2 of floor, and at least 1 m wall to wall each way (below
  that the views do not take it for a room);
- a `height` from 1.5 to 30 m.

What is stored:

- **`room.outline`**, as `{x, z}` corners running clockwise seen from above.
  Corners sent the other way round are turned, the first staying first; the
  `index` in a corner route's answer is where the corner is afterwards.
- **`room.width` and `room.depth` are worked out again**, as a scan works
  them out from the outline it traced: the box round the walls. The origin
  does not move, so it is the box **centred on the origin**: twice the
  furthest a wall reaches either side. For walls that are centred, as a
  scan's are, that is their own size; for walls drawn out to one side it is
  wider than they are, and it is what holds a position by the far wall
  (`position_limits`, `_held`, `_fit` all go by this box).
- **A box is still a box.** Four corners square to the room and centred on
  the origin are stored as a width and a depth with no outline, so a room
  that was a box is drawn and held as one after its height is set or its
  walls are moved out evenly.
- `room.suggested` becomes false and its `basis` says "Walls set by hand."
  or "Height set by hand.", once.
- **Nothing else.** No raised area, truss, ring or fixture moves.
  `hanging_bands` are counted from the trusses and rings, which have not
  moved, so they stand as they were; the outline reaches them in a scan
  only through which scanned points count as hanging clear of a wall, and
  there are no points here to read again.

Each change answers `rig_id`, `room_shell` (the whole room), `outline` (the
corners as they now are), `box`, `height`, `width`, `depth`, `changed`
(false when what was sent is what was stored: nothing is written and no
step is left to undo), `undo`, `message` and, for the corner routes,
`index`. And **`outside`**: what the walls and ceiling leave outside them.

```
outside: { count,
  items:    [ { kind, index, name, reason, already_outside } ],
  fixtures: [ { rig_fixture_id, name, position: {x, y, z}, reason, already_outside } ] }
```

- An item is listed by the list it is stored in and its place there. Its
  `reason` is "partly outside the walls" when some of it is beyond a wall
  (a raised area's middle and four corners; a line walked every 0.25 m; a
  ring's middle and 24 points round it), "outside the walls" when all of
  those are, "above the ceiling" when a raised area's top or a truss's
  underside is, or two of them joined with "and".
- A fixture is listed when its place on the plan is beyond a wall or its
  height is above the ceiling.
- Within 1 cm of a wall is inside: a 2D drag holds a fixture exactly on the
  wall, and that is not worth a warning.
- `already_outside` is true for what was outside before this change too.
  `GET` and the undo route, which have no "before", say false.

A change to the walls is one step of the room's undo, with a label of its
own ("Walls redrawn", "Walls: corner 3 moved", "Walls: corner added after
corner 2", "Walls: corner 4 deleted", "Room height set to 4.5 m"), and is
replaced by reading the scan again like any other edit. `POST
.../room-shell/undo` now also answers `outside`.

Refusals beyond the 422s above: 404 for no such rig, a rig with no scanned
room, and a corner `index` (or `after`) that is not there ("The room has no
corner number 7 (it has 6)"); 409 while a locate walkthrough is running (all
but the `GET`), for a `DELETE` that would leave two corners, a `POST` to a
room that has 64, and a room with neither an outline nor a size; FastAPI's
own 422 list for an `index` or `after` that is not a whole number and an
`x`, `z` or `height` that is not a number at all. `corners` is not typed in
the request model, so that a raw `Infinity` anywhere in it is refused in a
sentence and not by a refusal that cannot be written (see below).

`outline` is not one of the room's lists: `POST .../room-shell/outline` and
`PATCH .../room-shell/outline/0` are answered 404 by the list routes.

For all of these routes: no fixture is retagged, no fixture's patch is
touched, the scan's undo record (`room_scan_undo`) is left alone, and
nothing reaches a device. The only fixtures moved are the ones hung on a
line or ring that the item `PATCH` moves, raises, turns or resizes with
`carry_fixtures` not false, and the ones the undo route puts back (slice
17). One hung on a deleted truss stays where it is, and a change to the
walls moves none.

**All of them but the `GET` answer 409 while a locate walkthrough is running
on the rig** (slice 15), with the `detail` the scan routes give ("A locate
walkthrough is running on this rig. Finish or end it, then edit the room.").
The walkthrough places fixtures against the room as it stands, and holds
its own copy of each position, which a truss carrying its fixtures would go
behind. Unlike the scan routes, which refuse only a
request that would move a fixture, these refuse every one. A walkthrough on
another rig holds nothing here.

Refusals. Nothing is written by a refused request, and no undo step is left:

| Status | When |
| --- | --- |
| 404 | no such rig ("Rig not found"); `kind` is not one of the three lists (`room`, `hanging_bands` and the rest cannot be edited; the `detail` names the three); the rig has no room stored, or its shell is not from a scan (`source` is not `"scan"`, as a demo preset's); or, for `PATCH` and `DELETE`, there is no item at `index` (negative, past the end, or not an object). That `detail` says how many the list has and to load the rig again, since the room may have been changed elsewhere. Checked in that order |
| 409 | a locate walkthrough is running on the rig. `PATCH` only: a centre, a size or a heading was given for an item with no usable position stored (a line missing an end, a centre that is not a number); it can still be renamed, raised or deleted. `POST` to a list: it already holds 50. `POST .../undo`: there is no edit left to undo |
| 422, `detail` a sentence | a name with nothing in it, or over 60 characters once trimmed; a number that is not finite; a size, height or heading outside its limits ("The width of a raised area must be between 0.3 m and 100 m; 0.1 m is not."); a size too big for the room ("... the room and the 2 m round it have room for 16 m."); a size field that is not this list's ("A raised area has no radius to set. It takes: width, depth, height, base height."); a heading for a line with both ends at one point and no length given. `PATCH` only: a body with nothing in it ("Nothing to change: give a name, a centre, a size, a height, a heading, a base height or a kind."), and a `riser_kind` that is empty. `POST` only: no centre, a size or height the kind needs left out. Both: a `riser_kind` that is not one of the three, or one given for a line or ring; a `base_height` outside 0 to 10 m, or one that puts a raised area's top above the ceiling |
| 422, `detail` FastAPI's list of errors | `index` is not a whole number; no body; a `name` over 200 characters as sent; a field that is not a number at all (`"wide"`) |

A number that is not finite is refused by `edit.py`, in a sentence, and not
by FastAPI's own check: JSON has no infinity, but a client can send
`Infinity` all the same, and FastAPI's refusal then cannot write the value
back and the request ends as a 500. (Before slice 15 a centre sent that way
did.)

The order they are checked in: FastAPI's own 422s first, before the rig is
looked up (so a bad `index` on a rig that does not exist is 422, not 404);
then "Rig not found"; then the locate walkthrough's 409 (so an edit that
would have been a 404 or a 422 for another reason is a 409 while one runs);
then the other 404s; then the fields; then the other 409s.

### `POST /api/rigs/{rig_id}/room-scan/carry-over`

The body is one entry of an applied scan's `hand_edits.carry_over`, as it
came (keys it does not read, such as `reason` and `warning`, are passed
over), with an optional `carry_fixtures` (default true, as for a PATCH). It
puts the fields named in `edits` (`name`, `height`, `base_height`) onto the
item at `kind`/`new_index`, marked as set by hand, as one step of the
room's Undo; fixtures move only by Edit Room's carry rules. The answer has
`kind`, `index`, `item`, `room_shell`, `changed` (false where the item
already had all of it), `undo`, `fixtures_moved`, `items_moved` and a
`message`. **409** where the item at `new_index` is gone or no longer
called `new_name`; **422** for an entry that is not one; **404** with no
room. Slice 36. Since slice 37 the answer also has `pending_carry_over`
(what is still open after it), and the entry, with every other one for the
same item, is gone from the stored list, even where nothing changed.

### `POST /api/rigs/{rig_id}/room-scan/carry-over/all`

"Keep all" (slice 37). The body is `{entries, carry_fixtures}`, `entries` a
list of `carry_over` entries as they came (from the applied answer, or from
the stored list below). Each is carried as the route above carries one, onto
the room the entries before it left, and the whole lot is **one step of the
room's Undo** ("2 names and trims kept from the last scan"; one entry's own
label for one). **All or none**: the first entry refused refuses the whole
request with its status (**409** stale, **422** not an entry or a trim the
room does not hold) and nothing is written. **422** before any is tried for
`entries` that is not a non-empty list of objects, and for **two entries
pointing at the same item** (the detail names both old names and the item:
one would silently overwrite the other). **422** also for a fixture that two
of the entries would each move (the moves are worked out from where the
fixtures stand and made together). The answer: `carried` (per entry, in the
order sent: `warning_id`, `kind`, `index`, `old_name`, `new_name`, `item`,
`changed`, `fixtures_moved`, `message`), `room_shell`, `changed`, `undo`,
`fixtures_moved`, `items_moved`, `pending_carry_over` and a `message`.

### `GET /api/rigs/{rig_id}/room-scan/carry-over`

What the last scan applied lost that can still be put back (slice 37):
`{rig_id, carry_over, count}`. Each entry is as the applied answer gave it,
with the `message` of its warning. The same list is in the stored room as
`room_shell.pending_carry_over` (and so in `GET /api/rigs/{id}`), left out
when empty. Writes nothing.

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

Walls drawn by hand (slice 16) are stored the same way, to the millimetre,
with two differences from a scan's. The origin is not moved to the middle of
the new walls, so `width` and `depth` are the box round the outline that is
*centred on the origin*, which for walls drawn out to one side is wider than
the walls are. And a room whose walls are made a centred box again loses its
`outline`. The room then has `suggested: false` and a `basis` ending "Walls
set by hand." or "Height set by hand.".

Edit Room writes into the same shape. An item a person has moved or resized
has `suggested: false` and says so at the end of its `basis` ("Moved by
hand.", "Resized by hand."); so has a raised area whose kind a person set
("Kind set by hand."). A raised area's `base_height` is how far its
underside is above the floor: a scan always writes 0, and Edit Room can set
it (slice 18), so its top is `base_height + height`. One a person added has `added_by_hand: true`,
`suggested: false` and `basis` "Added by hand."; nothing the scan found
carries `added_by_hand`. A hanging band started by a truss or ring set to a
height where nothing hung has `suggested: false` and a `basis` beginning "by
hand:". After any edit every line and ring is counted in one band, and no
band is empty.

A shell stored before slice 4 has no `outline`, `truss_rings`, `heading_deg` or
`rings`, and needs no migration: every reader goes by a line's two ends, and
takes a missing outline for a box and missing rings for none.

It travels under the same name as a demo preset's `room_shell`, which has other
keys (dome, balcony, LED walls). The 3D view draws whichever keys are there.

What a raised area *is* is guessed from its size alone, and its `basis` says
so: 6 m2 or more is a `stage`; smaller and at least 0.6 m high is a `booth`
("Booth or counter": a bar counter looks the same to a scan as a DJ booth);
smaller and lower is a `riser`. Edit Room's kind selector sets it by hand
(slice 18).

## How the scan is read

`backend/app/services/room_scan/`: `detect.py` picks the reader, `mesh.py`
(OBJ, PLY), `gltf.py` (GLB, glTF, slice 25), `usd.py` (USD text, RoomPlan) and
`usdc.py` (binary USD, slice 24) parse the file, `bundle.py` (slice 26) takes
the model out of a zip and hands it to one of those, `extract.py` finds the
room, `suggest.py` moves the guesses. In order:

1. **Points.** A mesh is sampled by area into points with normals; a point
   cloud is used as it is. A glTF's meshes are first put where its nodes place
   them (each node's matrix, or its translation, rotation and scale, times its
   parent's), so a scan an app wrote lying down and stood up with a node is
   read standing.
2. **Up axis.** From the file where it says (USD, RoomPlan; glTF is always Y-up
   and in metres, so it counts as saying both), else guessed
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
   1.5 m2, each measured along the room's axes. One that clearly stands
   turned from the walls is measured along its own sides instead and given a
   heading (slice 27, `_turned_box`): the box round the patch is tried at
   every heading within 45 degrees of square, and the smallest is kept when
   it is turned 5 degrees or more, is at most 0.9 of the box along the
   room's axes, and is at least 0.8 filled by the patch. No scan format
   says which way a stage faces, so this is read from its shape alone.
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
- **Where that stage stands at a heading** (slice 27), the row goes onto it
  **turned with it**. The row is read as drawn for a stage standing square
  where this one's middle is, fitted by the rule above (up onto it, 0.3 m in
  from its edges), and then swung about the stage's middle by the heading.
  It ends parallel to the stage's turned edges, as far in from them, with
  its spacing and its place across the stage kept; a row drawn at the front
  is at the turned front. Each fixture is turned by the heading as well
  (`turn_deg`; its `rotation_y` loses that much), so a light square to the
  stage's front stays square to it. Then the walls: the row is shifted as
  one piece into the room's box and its outline, a guess at a time only
  where it fits nowhere whole, and nothing is lifted to within 0.3 m of the
  ceiling. **A row a scan has already moved** (`position_hint:room_scan`)
  is read as already laid on the turned stage: it is fitted to it and never
  swung or turned again. A stage at heading 0, or with none stored, takes
  the rule above unchanged.
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
- raised areas are drawn as boxes, from their base height up, and overhead
  lines as plain bars, each turned to the heading it runs at. A line straight across the room is not
  drawn where the view already hangs a truss over the fixtures under it;
- **rings of truss** are drawn as plain flat rings at their own height;
- **fixtures on a line that does not run across the room, or on a ring,** hang
  from it (within 0.3 m of it on the plan and 0.6 m of its height) and get no
  truss of the view's own. The view's truss only runs across the room, and
  would otherwise put a short stub of it over every fixture round a ring.
  This is the one thing an old stored room draws differently: one with a line
  running upstage to downstage used to get those stubs over its fixtures;
- the booth against the upstage wall, the speaker stacks, the square dance
  floor, and the bar counter and door on the rear wall that the view otherwise
  invents are **left out**: they would stand through the stage and risers the
  scan found, or claim things about a real wall that nobody saw. The ceiling's
  beams and duct are still the view's own;
- **the booth and the crowd are fitted to the room** (slice 23,
  `scanFloor.ts`). The desk, decks and DJ stand on the raised area the room
  calls a booth, facing the open floor. A room with no booth and a stage gets
  them at the downstage middle of the first stage, marked in amber as a guess;
  a room with neither gets none. The crowd stands on the open floor: inside
  the walls, 0.5 m from them and from every raised area, and out of the metre
  in front of the booth. A raised area at a heading (slice 21) is read as it
  stands turned, and the booth on it is turned with it. Both are placed again
  when the room is edited. See "What slice 23 built";
- **the raised area marked as the DJ's booth has the desk, and the DJ and
  Floor cameras look at the booth that is drawn** (slice 28, `boothPick.ts`,
  `boothCamera.ts`). See "What slice 28 built".

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
  top above the floor. The tooltip of one with a base height also says how
  far it floats (slice 18).
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
  reach) and does not snap to the edges of raised areas. The snapped position
  is then held to the room.
- **On the truss, the fixture takes its hang height** (`onPlanTarget`,
  `rowMove2d.ts`), as in the 3D drag: the height is saved with the position,
  in the same batch-update. Carried off the truss again in the same drag, it
  goes back to the height it was picked up at, so brushing past a truss does
  not change a fixture's height. A snapped position the walls then held off
  the truss (a stored truss that runs out through a wall) does not take it.
- **A readout says what it snapped to** (`snapReadoutText`): "On Truss 1 ·
  hangs at 4.20 m", in the scan's teal, just above the fixture under the
  pointer, for as long as it is on the truss. A ring whose name does not say
  so is called one: "On Overhead A (ring) · hangs at 4.80 m".
- **A palette drop snaps the same way**: dropped within 0.4 m of a scanned
  truss line or ring the new fixture lands on it, at its hang height, and
  the landing spot shows the same readout while the fixture is held over it.
  Out of reach it lands on the grid, at the height of the nearest fixture in
  depth as before. Alt, and the snap mode None, let go as they do for a drag.
- What holds a drag is the walls the plan draws, so the two cannot disagree.
  A scan with truss or raised areas but no usable room draws no walls, and a
  drag is then held to the deck as with no room; it still snaps to that
  scan's truss.

### Moving a whole row

A scan's suggestion moves a row as one piece, and so can a person
(`StageView2D.tsx`, `rowMove2d.ts`, `RigBuilder.tsx`):

- **Shift-click, Ctrl-click or Cmd-click** adds a fixture to the selection,
  or takes a selected one back out. A press without a modifier on a fixture
  that is not selected selects it alone, as before.
- **Select row** in the toolbar, or a **double-click on a fixture**, selects
  every fixture of its row (`rowOf`), read the way `suggest.py` reads one:
  the fixtures of its **group**; else, for a fixture with no group, the
  ungrouped fixtures hanging from the **same scanned truss line or ring**
  (within 0.3 m on the plan and 0.6 m in height, the 3D view's own reach),
  which is how a row laid along an angled truss or round a ring is found
  again; else the ungrouped fixtures at the **same height and depth**, to
  0.1 m. The button goes by the first selected fixture in the rig's order.
- **Dragging any selected fixture moves them all** by one shift, so spacing
  and shape are kept exactly. The fixture under the pointer goes where it
  would alone (the scanned truss snap, then the snap mode), and the others
  take the same shift.
- **No member may leave the room** (`holdRowShift`). The shift is cut short
  by however far the worst-placed member would be past a wall, so the whole
  row stops when its leading fixture reaches a wall: the walls of a box
  room, the floor outline of a room that has one (a notch is outside), or
  the deck where there is no scanned room. A row that fits no nearer the
  pointer stays where it was.
- **A member already outside the walls** when the row is picked up (a guess
  left in a notch) is not held until the row has brought it inside: holding
  it at once would mean closing the row up or refusing to move it. From
  then on it is held like the rest.
- **The row snaps onto scanned truss with the fixture under the pointer.**
  Each member that is then on that truss line or ring (within 5 cm) takes
  its hang height; a member off it (a row longer than the truss, or not
  lying along it) keeps the height it was picked up at. The readout counts
  them: "Row of 4 on Truss 1 · hangs at 4.20 m", or "3 of 4 on Truss 1 ...".
- **Moved guesses stay guesses.** The row is saved through batch-update, all
  of it in one request, which leaves every tag as it is: nothing is
  confirmed, and the fixtures are still amber in the 3D view.
- **One undo puts the whole row back**, with the heights a snap changed: the editor's Undo
  takes one step for the whole drag, as it does for one fixture, and Redo
  moves it again. (This is the editor's own undo, not "Undo room scan
  moves": that one will now leave these fixtures alone, as "moved since the
  scan".)
- A press on one of several selected fixtures that is let go without moving
  selects that fixture alone. With several selected the properties panel is
  put away, since it edits one fixture, and a line says how many are
  selected.

With one fixture selected, or none, a drag is what it was.

### Clicks, a selection box and the keyboard

Correcting guesses means a lot of clicking, so a click must never move
anything, and a selection should be quick to build and to shift
(`planSelect2d.ts`, `StageView2D.tsx`, `RigBuilder.tsx`):

- **A press is a drag only from 5 screen pixels** (`pastDragThreshold`).
  Until the pointer is that far from where it went down, nothing moves, so
  a click, a press with a wobble or a double-click that slips moves no
  fixture and no row, puts no off-grid guess on the grid or a truss, saves
  nothing and adds no undo step. Once past it the drag is what it was,
  back near where it began too. A press that never gets that far is a
  click: on one of several selected fixtures it selects that one alone.
  A palette drop has no press and is unchanged.
- **A drag over empty floor draws a selection box**, past the same 5
  pixels. Let go, every fixture whose marker centre is inside it is
  selected (`fixturesInBox`), whichever way the box was dragged; a centre
  on its edge is inside. **Shift, Ctrl or Cmd** held at the press adds
  them to the selection and takes nothing out (`boxSelection`). A plain
  box over nothing selects nothing. A box carried off the plan takes what
  it held when it left. Under 5 pixels it is still a click on empty floor,
  which clears the selection as before.
- **Escape** clears the selection, or lets go of a box being drawn and
  leaves the selection as it was.
- **R** selects the row of the selected fixture, as the Select row button
  does (the first selected fixture in the rig's order).
- **The arrow keys nudge the selection** by the grid step, ten steps with
  Shift (`nudgeShift`): left and right across the plan, up upstage, down
  downstage. Every selected fixture takes the one shift, cut short where
  any of them would leave the room, by the rule a row drag is held by
  (`nudgeMoves`, which calls `holdRowShift`): the walls, the floor outline,
  or the deck with no scanned room. Spacing is kept. A selection already
  against the wall it is pushed at does not move, and nothing is saved.
- **A nudge is a step, not a snap.** It adds the step to where the fixture
  is and does not put it on the grid or on a truss, and it **never changes
  a height**. Positions are kept to the millimetre.
- **One press is one batch-update and one undo step.** The plan reports a
  nudge the way it reports a drag (picked up, moved once, let go), so the
  editor saves and undoes it by the same code. Tags are not touched:
  nudged guesses stay guesses. **A key held down does not repeat**: it
  would fill the 50-step undo history in a couple of seconds and send a
  request for each repeat. Shift is the way to go further.
- **Whose key it is** (`keysBelongElsewhere`). Keys are ignored while the
  focus is in an input, a textarea, a select or a contenteditable element,
  in a drawn drop-down or menu (the snap mode's), or in a dialog; with
  Ctrl, Cmd or Alt held (Ctrl+R reloads, Alt+Left goes back); and while
  the pointer is holding a fixture or drawing a box. With nothing selected
  an arrow key is left to scroll the page. The plan only listens when the
  editor says so (`keyboard`): while the 2D view is shown and neither the
  Identify walkthrough nor the Room Scan dialog is open.

With no scanned room and one fixture, a drag past 5 pixels reports exactly
what it did.

### Laying a row along a truss

A drag carries a row and never respaces it. **Lay on truss** in the toolbar
does the other thing: it spreads the selected fixtures evenly along scanned
truss, as a scan's suggestion lays a row along an angled truss or round a
ring (`layRowOnTruss` in `rowMove2d.ts`, `RigBuilder.tsx`,
`RigEditorToolbar.tsx`). The button is there only in a rig whose scan found
truss, and needs two or more fixtures selected.

- **Which truss**: the scanned line or ring nearest the middle of the
  selection on the plan (`nearestTruss`), the first the scan listed where
  two are as near. A ring is as near as its centre or its circle, whichever
  is nearer, so a row drawn straight through a ring belongs on it. Any
  truss on the plan is in reach, at whatever height. The button's tooltip
  names the truss before anything moves.
- **Where each goes** (`spotsOn`) is `suggest.py`'s own rule (`_spots_on`).
  Along a line: the whole length shared out with half a space at each end,
  so four fixtures on 8 m hang 2 m apart and 1 m in. Round a ring: the
  first upstage, the rest clockwise seen from above.
- **In address order** (`addressOrder`: universe, address, id), and along a
  line the row keeps the sense it had: if its first address was towards
  stage left before, it still is.
- **Every one takes the truss's hang height.**
- **All of it or none of it.** If any place on the truss is outside what a
  drag is held to (the walls, or the deck where the scan has no usable
  room), nothing moves and a message says how many places are outside. A
  stored truss that runs out through a wall is the case.
- **Saved and undone as a row move is**: one batch-update, no tag touched
  (guesses stay amber), and one Undo puts every fixture back, heights
  included. A message says what was done: "Laid 4 fixtures along Truss 1,
  2.00 m apart, at 4.20 m.", with a word more when they come under 0.3 m
  apart. Pressed again on a row already laid, it moves nothing and says so.
- Unlike a scan's suggestion it lays out what is **selected**, whatever its
  tags: a tapped or measured fixture that is selected moves too, and the
  unselected fixtures of a group keep no place in the count.

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
A drag of one fixture reports a position and no height, and no readout is
drawn. What is new there needs more than one fixture selected: a row can be
selected and carried on the deck too, held to the deck's edges.

## What slice 37 built

Keep all, and the carry-over list outlives the dialog. Slice 36 put one lost
name and trim back at a time, from buttons that lived only in the answer to
the apply. This slice keeps them all at once, keeps the open ones with the
stored room, and ties each button to its warning by an id.

- **Warning ids** (`keep_edits.py`, `warning_id()`). Each lost warning that
  has a `carry_over` entry has an `id` (`"lost-0"`, `"lost-1"`, ...: its
  place among the losses, not the item it points at, as two losses can
  point at one item), and its entry the same as **`warning_id`**. `warning`
  (the place in `warnings`) is kept. The dialog matches by id
  (`handEditWarningEntries`), and by the server's place only for an entry
  without one.
- **The list kept with the room** (`pending_carry.py`). Applying a scan
  stores its entries in the room as **`room_shell.pending_carry_over`**,
  each with its warning's `message`; the key is left out when there are
  none, so such a room is stored as before. The apply answer's
  `room_shell` is the room as stored, list and all (a preview stores
  nothing and has none). An entry is **dropped** when:
  - it is carried over (with any other entry for the same item, which the
    new name would make stale);
  - Edit Room changes its item's `name`, `height` or `base_height` (a
    PATCH, or a raised area carried by another); a move keeps it;
  - its item is deleted; the entries of the items after it in that list
    move up one place, so none points at its neighbour;
  - the room is read again (the new apply's list replaces it, or none) or
    taken off.
  Every step of the room's Undo keeps the room as it was, so **Undo brings
  an entry back** with whatever dropped it: a carry-over, a rename, a
  delete. No new column.
- **`GET .../room-scan/carry-over`** lists them; the same list comes with
  the rig as read.
- **"Keep all"** (`carry_all()` and `refuse_shared_targets()` in
  `carry_over.py`; `POST .../room-scan/carry-over/all`). Every entry in one
  request, as **one Undo step**, all or none; two for one item are a 422
  that names both, and so is a fixture two of them would each move. Edit
  Room's carry rules for each item are passed in by the route, so the pure
  function is tested without a database.
- **The dialog** (`RoomScanDialog.tsx`; `pendingCarryOverOf`,
  `carryOverKey`, `keepAllButtonText`, `roomScanCarryOverAllPath`;
  `roomScanApi.carryOverAll`). With two or more entries, **"Keep all N"**
  (`room-scan-carry-over-all`) sends every one not yet kept, then reads
  "Kept all", disabled; a refusal shows the server's words and leaves every
  button as it was. Kept entries are tracked by `carryOverKey` (the warning
  id), not by place, and another entry for an item something was kept on
  is spent with it (disabled, and not sent with Keep all), as the server
  drops it. **Opened again** with no scan on screen and no file
  chosen, it shows the stored entries (`room-scan-pending-carry-over`), each
  in a warning with its sentence and its "Keep Front truss on this one"
  button, and "Keep all". They come in as the prop `pendingCarryOver`, which
  RigBuilder reads from the rig it already has, so opening makes no request.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_all.py` (18): two real
  losses (a line read at another height, a ring read beside) with their ids
  and stored sentences; keep all of them; one stale entry (first or last)
  refuses all; one that is not an entry; two for one item (422 naming
  both); lists that are not one; a fixture moved twice; the list dropped on
  a rename or re-trim and kept on a move; a delete dropping one and moving
  a later one up; carried entries going with their twins; a new reading
  with no list; an Undo step keeping it.
  `tests/integration/test_api_room_scan_keep_all.py` (16), over HTTP with
  slice 36's room: the list stored, in the GET and in the rig; carried, gone,
  and back with Undo; renamed (then a 409), and back with Undo; re-trimmed;
  deleted; read again; removed; Keep all as one Undo step answering per
  entry; two entries on two lists as one step ("2 names and trims kept from
  the last scan") that one Undo takes back whole; one stale entry writing
  nothing; two for one item a 422; six bodies that are not a list of
  entries (two with a `kind` or `new_index` that cannot be compared: a 422
  in a sentence, not a 500). Frontend,
  `RoomScanDialogKeepAll.test.tsx` (12): buttons in their warnings by id
  (with places given crossed and a warning passed over); Keep all sending
  both and then disabled; Keep all after one is kept sending the other; a
  refusal leaving every button; no Keep all for one entry; the reopened
  dialog showing the stored sentences and buttons, sending one, then the
  rest with Keep all; nothing shown with none stored or once a file is
  chosen; the helpers.
- **Existing tests changed** (in 295d9da, which lists each): exact warning
  and `carry_over` dicts gain `id` / `warning_id` (seven in the unit tests,
  two in `test_api_room_scan_keep_named.py`), and one assertion that the
  preview's, the answer's and the stored room were equal now says the
  stored room and the answer have the list and the preview does not.
- **What was run** (Nov 27). Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2833 passed, 10 skipped, 5 xfailed**; then,
  after the unhashable-target fix and the two-entry test (written after
  that run), the four carry-over and keep-all files on their own: 51
  passed. Frontend: `npx tsc --noEmit -p .` gave the 13
  older errors and none new. **`npx vitest run` was not run** (not allowed
  in the session): the 12 new frontend tests are checked by the
  type-checker only.
- **No Art-Net, no DMX, no network call, no new dependency, no new
  column.**

## What slice 36 built

Carry a lost name and trim over, and say every loss. Slice 35 named three
losses and left three silent; this slice names those too, gives each loss
that has an item of the new room behind it in a form a program can act on,
and lets the operator put the old name and trim onto that item with one
button.

- **Every loss said** (`keep_edits.py`, `LOST_GONE`, `LOST_OTHER`, and
  `LOST_BESIDE` for raised areas). Three more entries in
  `hand_edits.warnings`, each with its own `message`, and each listed in
  `items` with the new outcome **`"lost"`**:
  1. **A raised area read to one side** (`"read beside"`). One with a name,
     height or base height set by hand that matched nothing, where the
     reading has a raised area no stored one is that shares some floor with
     it but less than the half a match needs. The warning names it and the
     new area.
  2. **A line or ring no longer read at all** (`"no longer read"`). One
     with a name or trim set by hand that matched nothing and has nothing
     of the reading near it: "The scan no longer reads Front truss; its
     name and trim go with it." There is nothing to carry it onto.
  3. **Of two stored items that pick one new one, the one that loses**
     (`"another has it"`). Where it had something set by hand and was not
     added by hand (that one is replaced and named as before). The warning
     names both.
- **`hand_edits.carry_over`** (`KeptEdits.carry`). One entry for every loss
  with a new item behind it ("hanging height", "read beside", "another has
  it"): `{kind, old_name, old_trim_or_height, edits, new_index, new_name,
  reason, warning}`, and `old_base_height` for a raised area. `kind` is the
  list (`risers`, `truss_lines`, `truss_rings`), `edits` which fields would
  be put back, `new_name` what the new room calls the item, `warning` the
  place of its warning in `warnings`. Sent only when it has something in it,
  in a preview and in `applied` alike. Nothing is written for it.
- **`POST /api/rigs/{rig_id}/room-scan/carry-over`** (`carry_over.py`, the
  route in `endpoints/room_scan.py`). Takes one entry as the answer gave it
  and writes only the fields in its `edits` with Edit Room's own edit
  (`edit_item`: the ceiling and floor limits, the top of a truss, the bands
  counted again), then **marks each as set by hand** with the basis markers
  Edit Room writes ("Name set by hand.", "Height set by hand.", "Base height
  set by hand.", with "Resized by hand." for a size) **whether or not the
  value changed**, so the next scan keeps it. A line's or ring's trim keeps
  the height the scan read as `scan_height` (slice 34). An entry for a trim
  alone does not write the scan's name or mark it.
  - **Fixtures move only as Edit Room's rules move them**: the PATCH's carry
    logic is shared (`_with_what_it_carries`, `_store_edit`), so the
    fixtures hung on a truss whose trim changes go with it, and what stands
    on a raised area whose height changes; `carry_fixtures: false` leaves
    them. One that would leave the room refuses the whole carry-over.
  - **One step of the room's Undo** (`POST .../room-shell/undo`), labelled
    "Overhead line 1 given the name and trim of Front truss".
  - **409 on a stale entry**: the item at `new_index` is gone or no longer
    called `new_name` (the room was edited, or the same entry was already
    carried over). **422** for an entry that is not one (an unknown `kind`,
    a `new_index` that is not a whole number, `edits` empty or naming a
    field that list cannot carry, a blank name, a trim that is not a
    number). Nothing written either way. Refused during a locate
    walkthrough, as every room edit is.
- **The dialog** (`RoomScanDialog.tsx`; `handEditCarryOver`,
  `carryOverButtonText`, `roomScanCarryOverPath` in `utils/roomScan.ts`;
  `roomScanApi.carryOver`). After Apply only (before it nothing is stored
  to put it on), each `carry_over` entry has a **"Keep Front truss on this
  one"** button (`room-scan-carry-over`) inside the warning it belongs to;
  one with no warning place sits under the warnings. It sends the entry as
  it is, shows the server's message, tells the rig it changed, and then
  reads "Kept Front truss on Overhead line 1", disabled. A 409 shows the
  server's words and leaves the button to try again.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_lost.py` (27): the
  three new warnings, their `items` entries and `carry_over` entries, and
  the carry-over entries of slice 35's two warnings.
  `tests/unit/test_room_scan_carry_over.py` (7): a real entry of each kind
  (a raised area read beside with all three fields, a ring trim alone, a
  line read at another height, both "another has it") fed to
  `carry_over()` with the room the scan left: none stale, the markers on,
  the same reading applied again keeping them; an entry carried twice is a
  409; no room is a 404.
  `tests/integration/test_api_room_scan_carry_over.py` (10), over HTTP with
  the truss read 1.2 m lower: the entry as given puts the name and trim
  back, marked, with `scan_height`, no fixture moved, and the same reading
  applied again keeps them; one Undo puts the room back as the scan left
  it; the same entry sent twice is a 409; an index past the end is a 409;
  six entries that are not one are 422s, none writing anything. Frontend,
  `RoomScanDialogCarryOver.test.tsx` (5): no button before Apply; the
  button in its warning calling `carryOver` with the entry and saying what
  was done; a 409 shown; the helpers.
- **Existing tests changed** (all in step 1's commit, f9b3efd, which lists
  each): key sets that gain `carry_over`, and five tests where a truss or
  riser lost without a word is now said.
- **What was run** (Nov 27). Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2795 passed, 10 skipped, 5 xfailed**,
  then `test_room_scan_carry_over.py` (unit, 7), written after that run,
  on its own: 7 passed. Frontend: `npx tsc --noEmit -p .` gave the 13
  older errors and none new. **`npx vitest run` and `npx vite build` were
  not run** (refused in the session): the dialog change and its 5 tests
  are checked by the type-checker only.
- **No Art-Net, no DMX, no network call, no new dependency, no new
  column.**

## What slice 35 built

A scan applied again says by name what it kept, left out and lost. Until
now the answer counted ("1 overhead item you deleted") and a sentence named
things only in `hand_edits.message`, which is not on screen; and three
things were lost without a word: a name and trim on a truss re-trimmed by
more than 1.0 m, a name and trim on a truss read to one side, and the
record that keeps a deleted thing deleted.

- **The list** (`keep_edits.py`, `KeptEdits.report`; `ITEM_WORDS`, `KEPT`,
  `LEFT_OUT`, `REPLACED`, `ADDED_KEPT`). `hand_edits`, in a preview and in
  `applied`, gains `items`: one entry for each thing acted on, `kind`
  (`"raised area"`, `"line"`, `"ring"`), `name` and `outcome` (`"kept your
  edits"`, `"left out (you deleted it)"`, `"replaced (a scanned item
  overlaps it)"`, `"added by hand, kept"`). It is built from the lists the
  answer already had, in the order `message` says them, so the two cannot
  disagree. The outcome is worded the same before and after Apply. A name
  is read from the room as it will be stored, as the other lists read it.
  **The key for what happened is `outcome`**: the task named the other two
  keys and not this one. Sent only when it has something in it.
- **`message`, `areas` and every list the answer had are what they were.**
  `message` gains a sentence only for a new warning (below).
- **Nothing lost silently** (`keep_edits.py`: `_near_miss`, `_lost_words`,
  the third value `_leave_out` returns; `KeptEdits.lost`). Three more kinds
  of entry in `hand_edits.warnings`, each with a `reason` and its own
  `message`, after the checks slice 33 put there:
  1. **`"hanging height"`.** A line or ring with a name or a trim set by
     hand (not one added by hand) matched nothing, and the reading has one
     that shares half the plan with it and was passed over only for hanging
     more than `HANG_MATCH_M` from where the scan read this one. The
     sentence gives where the scan read that one, this one's trim, and,
     where the trim was set by hand, where the scan read this one before:
     the 1.0 m is measured from the last reading (slice 34), so "2.8 m
     against its trim of 3.5 m" alone would read as inside it.
  2. **`"read beside"`.** The same, where the reading has one within the
     height that shares some of the plan with it and less than the half a
     match needs: read to one side, or much shorter. The sentence gives the
     distance between the two middles and the share of the plan. Any
     overlap at all counts, as the task says, so a truss read up to 0.6 m
     to one side is said; read clear of where it was, nothing is.
  3. **`"record dropped"`.** A record of a deleted raised area, line or
     ring that matched nothing in this reading (or lost the item to another
     record) and is not carried on: "The scan did not see Riser; the record
     that keeps it deleted was dropped, so it may come back on a later
     scan."
  - **Only items of the reading that no stored item is are looked at**
    for 1 and 2 (the same "who has it" that settles two stored items
    picking one new one). So the other truss of a stack is itself, not the
    lower one read 1.3 m higher, and a truss that crosses is itself, not
    this one read beside. This fails without the rule: the stack test and
    the crossing test are in the unit file.
  - Height is asked before beside; of several, the greatest overlap.
  - **`hand_edits` is now sent for a warning alone.** Until this slice a
    dropped record or a name lost to the height gave no `hand_edits` at
    all; now it is there with `areas` 0, the lists empty, `warnings` and
    the sentence. The room is still the reading as it came, the same
    object: a warning writes nothing.
  - These entries are kept apart from slice 33's checks inside
    (`KeptEdits.lost`, not `KeptEdits.warnings`): a check has an `index`
    in the new room and a lost thing has none.
- **The route** is not changed but for its log line, which counts what was
  lost, and its docstring.
- **The dialog** (`RoomScanDialog.tsx`; `handEditItems`,
  `handEditItemText`, `handEditWarnings`, `HAND_EDIT_ITEMS_SHOWN` in
  `utils/roomScan.ts`). Under the line of counts
  (`room-scan-hand-edit-items`): one row for each entry, "Front truss
  (line): kept your edits". With more than five, the first five and a
  button, "Show all 7", which becomes "Show fewer"
  (`room-scan-hand-edit-items-toggle`); a new preview closes it again.
  Under that, **each entry of `hand_edits.warnings` as a warning of its
  own** (`room-scan-hand-edit-warning`), as the scan's own warnings are
  shown: the server's `message` for what was lost, and for a check, which
  has none, "Check Podium: it is outside the walls of the room as this
  scan reads it." as the server's `message` words it. So the checks of
  slice 33 are on screen by name too.
  - **The line of counts is what it was.** "N to check against the new
    room" counts only warnings with a place in the new room: a lost name
    or a dropped record is not something to check against it, and is said
    in full underneath. An answer with only those has no line of counts.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_named.py` (32): the
  four outcomes' words; one of each thing listed in order, the same before
  and after Apply, beside counts and a sentence that are what they were; a
  name the DJ booth mark gives afterwards; no list where nothing was done;
  a name lost to the height, with a trim set by hand, a trim alone, a
  ring; a trim far from the reading that is no loss; inside the tolerance;
  the other truss of a stack; a truss no longer read; one added by hand; a
  name lost 0.3 m to one side, read much shorter, read a little off and
  read clear; a truss that crosses; a ring; height before beside; a
  dropped record of a raised area, a line and a ring, said once, beside
  what was left out, of two that pick one area, with no name; a check
  before what was lost; neither room changed.
  `tests/integration/test_api_room_scan_keep_named.py` (5), over HTTP with
  readings made in the test (the truss hung 1.2 m lower, read 0.3 m to
  one side, the riser gone): the list in a preview that writes nothing and
  in the apply, the same in both; the re-trim warning with its numbers,
  said once; the offset warning; a dropped record named, the room without
  its `deleted_areas`, and the riser back at the scan after. Frontend,
  `RoomScanDialogHandEditItems.test.tsx` (13): the list under the line, no
  toggle for five, the toggle opening and closing seven, no list where
  none was sent, after Apply; the warnings as alerts with no line; a check
  said in full beside the count; the helpers.
- **Existing tests changed, because the behaviour was.**
  - **`items` is a new key** wherever something was kept, left out or
    replaced. Seven assertions held the exact keys or the whole answer:
    `test_a_preview_and_an_apply` (unit, keep_edits); the two whole-answer
    equalities of `test_a_raised_area_added_by_hand_is_kept_where_the_
    scan_has_nothing` and `..._is_replaced_where_the_scan_overlaps_it`
    (integration, keep_edits); `AREA_KEYS` (integration, keep_overhead,
    used by two tests); and `test_what_is_said_before_apply_and_after_it`,
    `test_what_is_said_of_each_kind_and_which_keys_are_sent` and
    `test_nothing_is_flagged_and_no_key_sent_where_the_room_holds_it_all`
    (unit, keep_overhead). They hold the same and `items`.
  - **`not got.any` no longer holds where something is lost.** Four unit
    tests in keep_overhead: the two `test_a_record_the_reading_has_
    nothing_for_is_dropped_...` (raised areas; lines),
    `test_a_record_of_a_line_is_never_asked_of_raised_areas_or_rings` and
    `test_one_read_within_the_tolerance_is_the_same_and_one_beyond_it_is_
    not`. They hold what they held of the room (the reading, the same
    object; nothing left out or kept) and the warning.
  - No frontend test was changed: the older fixtures' warnings all have an
    `index`, so the line of counts is what it was for them.
- **What was run** (Nov 24). Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2758 passed, 10 skipped, 5 xfailed**
  (2721 before; the 37 new ones are the two files above), run again after
  the last change to the wording of a warning. **Frontend: nothing was run.**
  `npx vitest run` and `npx vite build` were refused in the session, and
  the worktree has no `frontend/node_modules`, so `npx tsc --noEmit -p .`
  found no compiler. The dialog change and its 13 tests are unchecked by
  any tool. See "What is left".
- **No Art-Net, no DMX, no network call, no new dependency, no new
  column, nothing new stored in the room**: the list and the warnings are
  in the answer only.

## What slice 34 built

Three points slice 33 left open: a deleted overhead line or ring stays
deleted, two trusses hung one above the other keep their own edits, and the
question asked before a delete says what now happens.

- **A deleted line or ring leaves the record a raised area leaves**
  (`edit.py` `delete_item`, `tombstone(item, kind)`). The record goes in the
  same `deleted_areas` list, shaped as the item was so the one matcher can
  be asked of it: a line's ends, `across` and height; a ring's centre,
  radius and height; the name of each. It stores **no `kind`**: a line and a
  ring of a reading have none, and `best_match` wants kinds equal. Which
  list a record belongs to is read from what it stores (ends: a line;
  a radius: a ring; else a raised area), as `_footprint` already reads an
  item. One added by hand leaves no record, as before.
- **A scan applied again leaves it out** (`keep_edits.py` `_leave_out`, now
  run over the three lists; `best_match` and the slice 33 footprints, no
  second matcher). Each record is asked only of the list it was deleted
  from. One that matches is left out of the new room, **taken out of
  `hanging_bands`** as Edit Room's delete does (a band left empty goes),
  and reported in `hand_edits.deleted_left_out` with `kind`
  `"truss_lines"` or `"truss_rings"`. Its record goes on to the new room
  with the ends (or centre and radius) and the height this reading gave. A
  record that matches nothing is dropped. All of it is done before anything
  else is matched, as for raised areas, so a truss deleted and put in again
  by hand is kept as the person's. `message` has a sentence for each kind
  ("Left out 1 overhead line you deleted: Overhead line 1."); the sentence
  for raised areas alone is what it was, and an answer with nothing left
  out has exactly the keys it had.
- **Hanging height is part of the match for a line and a ring**
  (`keep_mark.py` `best_match`, `HANG_MATCH_M` = **1.0 m**). One of the new
  reading whose `height` is more than 1.0 m above or below where the scan
  read the stored one is not a match, whatever the plan says. A scan reads
  the same truss within centimetres, and a truss flown under another hangs
  more than a metre below it. This holds for everything `best_match` is
  asked about a line or ring: names and trims kept, records of deleted
  ones, and whether one added by hand "is" a scanned one. **A raised area's
  height is still never compared**, and the DJ booth rule is unchanged: the
  rule applies only to an item that stores ends or a radius.
- **The height compared is the scan's reading, not a trim set by hand**
  (`edit.py` `SCAN_HEIGHT_KEY`, `scan_read_height`). The task as written
  compared the candidate with "the stored" height. Done literally that
  would throw away every trim moved by more than 1.0 m, because the stored
  height of a hand-trimmed truss is the trim (a truss the scan reads at
  4.2 m, hung by hand at 3.0 m, would never match its own reading again;
  slice 33's own tests hold that case). So a line or ring whose
  height is set by hand now also stores **`scan_height`**: `edit_item`
  writes it the first time a trim is set (the height it had), and
  `keep_edits` writes it again at every reading that keeps the trim (the
  height that reading gave). The match, and the record of a deleted one,
  use `scan_height` where there is one, else the `height` where that is
  the scan's own. **Where neither says what the scan read, heights are not
  compared**, which is the slice 33 behaviour: a trim set by hand before
  this slice (no `scan_height`; it gets one at the next reading that keeps
  it), and a line added by hand.
- **The delete question** (`utils/roomShellEdit.ts` `deleteQuestionText`).
  For an item the scan read: "It stays deleted when the scan is applied
  again. Undo here brings it back, until then." (it was "Undo here brings
  it back, until the scan is read again."). "Until then" because an applied
  scan empties the room's Undo steps. For one **added by hand** the old
  sentence stays: no record is kept of it, so "stays deleted" would be a
  promise about nothing. Edit Room's help text says a line or ring of the
  scan's that was deleted stays out.
- **The dialog's line** (`handEditsLine`): a left-out line or ring counts
  as an overhead item ("Will leave out 1 area and 2 overhead items you
  deleted"); it was counted as an area.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_overhead.py` (+19,
  53): the record a line and a ring leave and what leaves none; the record
  holding the scan's height and not a trim; a line and a ring left out,
  the bands still adding up, the record carried on with the new reading's
  numbers, twice; the only line of a room; the words and keys for each
  kind; a record dropped, and a line read over the same floor more than
  1.0 m higher not being it; deleted and put in again by hand; **two
  trusses with one footprint read in the other order keeping their own
  names and trims** (this fails with the height rule taken out: checked),
  also at the reading after and with the lower one trimmed to beside the
  upper; a deleted one of a stack taking out only its own; inside and
  outside the tolerance; a ring; a trim from before `scan_height`;
  `scan_height` written once and never for one added by hand or a raised
  area; a raised area's height not compared; a stack nobody edited coming
  back as the same object. `tests/integration/
  test_api_room_scan_keep_overhead.py` (+2, 10): over HTTP, a deleted
  truss left out in a preview that writes nothing and in two applies, and
  the room's Undo forgetting it. Frontend: `roomShellEdit.test.ts` (+1)
  and `RoomScanDialogHandEditsOverhead.test.tsx` (+1).
- **Existing tests changed, because the behaviour was.**
  - `test_a_scan_read_again_replaces_the_edits` and
    `test_a_scan_read_again_clears_the_steps` deleted the scan's truss and
    held that it was back after the scan. It now stays out: they hold the
    empty line list, no bands and the record.
  - `test_one_added_by_hand_and_deleted_and_a_deleted_line_leave_nothing_
    behind` (integration) is now `..._and_deleted_leaves_nothing_behind`
    and deletes a line added by hand; the unit test that held a deleted
    line and ring leave no record lost those two lines and its name says
    so.
  - Three vitests held the old delete question
    (`RoomShellAdjustDialog.test.tsx`, `RoomShellRaisedDialog.test.tsx`,
    `roomShellEdit.test.ts`): they hold the new one.
- **What was run** (Nov 24): see the end of this section's list in "What
  is left" for what was not. Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2721 passed, 10 skipped, 5 xfailed** (2700
  before; the 21 new ones are in the two files above). Frontend:
  `npx tsc --noEmit -p .` only the 13 older errors. **`npx vitest run` and
  `npx vite build` were refused in the session.**
- **No Art-Net, no DMX, no network call, no new dependency, no new
  column**: the records and `scan_height` are in the room's own JSON.

## What slice 33 built

The three points slice 32 left open: overhead lines and rings keep what a
person set on them, a raised area a person deleted stays deleted, and what
is kept is checked against the new room.

- **Still one matcher** (`services/room_scan/keep_mark.py`). `best_match`
  and `footprint_overlap` are not changed. What is new is what a footprint
  is, in `_footprint`, read from what an item stores:
  - **an overhead line** (it stores ends): the strip that runs along it
    from end to end, **0.6 m wide** (`LINE_STRIP_M`), or as wide as the
    truss's own `across` if that is more. The strip is built from the two
    ends, not from the heading (kept to a tenth of a degree). A truss is
    about 0.3 m across, and at that width two readings of the same truss
    0.1 m apart would share half and pass only just. Read a distance d to
    one side, two strips of width W share (W - d) / (W + d), so the same
    truss is matched up to 0.2 m off, and trusses hung 0.6 m apart or more
    share nothing;
  - **a ring** (it stores a radius): the disc it goes round, as a polygon
    of 24 sides.
  A line and a ring have no kind, so none is compared. A line is only ever
  asked of the new reading's lines and a ring of its rings. Heights are not
  looked at, as for a raised area. (*Changed by slice 34:* a line's and a
  ring's hanging height is now compared.)
- **What says a field of a line or ring was set by hand** (`edit.py`).
  There was none, so `edit_item` now writes for all three lists what it
  wrote for raised areas: **"Name set by hand."** when a rename changes the
  name (`suggested` left alone), and **"Height set by hand."** beside
  "Resized by hand." when the height it hangs at changes. A length, a
  radius, a heading and a move write neither. One **added by hand**
  (`added_by_hand`) has its height from a person, and its name too unless
  it is "Overhead line 3" or "Overhead ring 1", what it is called when
  nobody names it.
- **Lines and rings across a reading** (`keep_edits.py`: the slice 32 loop,
  now run over `risers`, `truss_lines` and `truss_rings`; `_plan`).
  1. A stored line or ring with a name or a hanging height set by hand that
     matches a new one gives it **the name and the hanging height**, and
     the new one's `basis` gets the same marks, so they hold at the reading
     after. A kept height takes `top` with it (the truss stays as deep as
     the scan reads it) and the line is counted again in `hanging_bands`,
     as Edit Room does, so the bands still add up and
     `summary.hanging_heights` and the suggested fixture moves use the kept
     trim.
  2. **Its ends, length, heading, radius and place are the scan's.**
  3. **One added by hand that matches nothing is kept as it is**, at the
     end of its list and counted in `hanging_bands`, **unless the new
     reading has a line (or ring) sharing more than a fifth of the two
     footprints with it** (`CROSSING`, 0.2). Then the scan's takes its
     place and the answer names both. A fifth, and not any overlap at all
     as for raised areas, because trusses cross and hang side by side: two
     3 m trusses that cross share about a tenth, and a pipe 0.4 m beside a
     truss shares exactly a fifth.
  4. One added by hand that the scan now reads (it matches) gives the
     scan's line its name and height, and is no longer `added_by_hand`.
  5. Two stored that pick the same new one, and one added exactly over the
     scan's own: as for raised areas (slice 32, points 3 and 8).
- **Raised areas deleted by hand** (`edit.py` `delete_item` and
  `tombstone`; `keep_edits.py` `_leave_out`).
  1. **Deleting a scanned raised area leaves a record** in the room's
     `deleted_areas`: its kind, its name, its footprint, and that its kind
     was set by hand if it was. Not for one added by hand, a line or a
     ring (*a scanned line and ring leave one since slice 34*). (The API
     section on DELETE has the fields.)
  2. **A scan applied again asks each record which raised area of the new
     reading it is, by `best_match`**: the same kind (any kind, if the
     kind was set by hand before it was deleted), half the two footprints
     shared. One that matches is **left out of the new room** and reported
     (`deleted_left_out`, "Left out 1 raised area you deleted: Riser."); a
     preview reports the same and writes nothing.
  3. **The record goes on to the new room**, standing where this reading
     has the area, so the reading after leaves it out too.
  4. **A record that matches nothing is dropped**: the scan no longer reads
     anything there.
  5. **This is done first.** Names, heights, added areas and the DJ booth
     mark are then asked of the room without those areas. So a raised area
     a person deleted and put in again by hand, their way, is kept as
     theirs: the scan's is left out, and theirs then overlaps nothing.
  6. **What forgets a record**: the room's Undo taking the delete back (the
     record is part of the room, and Undo puts back the whole room as it
     was before); taking the room off the rig, so that the next scan is
     read from scratch. Nothing else: an apply empties the Undo steps, so
     after a scan is applied again the way back is the room taken off and
     scanned afresh.
- **Checks** (`keep_edits.py` `_checks`, asking
  `outline_edit.outside_report` of the room that will be stored: no new
  rule for walls or ceilings). What is kept is kept whatever the new room
  is, and flagged in `hand_edits.warnings` where:
  - **a kept height is above the new ceiling**: a raised area whose height
    or base height was kept and whose top is over it, or a line or ring
    whose hanging height was kept and is over it. An item that kept only a
    name is not flagged: its height is the scan's own reading;
  - **an item added by hand and kept as it is** has any part outside the
    new walls, or is above the new ceiling.
- **The answers.** `hand_edits` gains `overhead_kept`,
  `overhead_added_kept`, `overhead_added_replaced`, `deleted_left_out` and
  `warnings`, **each only when it has something in it**, and `message`
  says them. The five keys it had are as they were, and still speak of
  raised areas only, so an answer about raised areas alone is exactly what
  it was. With nothing kept, replaced or left out there is no `hand_edits`
  at all, as before. The route is not changed but for its log line:
  `keep_hand_edits` was already called once for a preview and an apply.
- **Edit Room's help text** (`RoomShellEditDialog.tsx`) says what is now
  kept, and that a deleted raised area stays out. The question asked
  before a delete is not changed ("Undo here brings it back, until the
  scan is read again"): it is still true, but does not say that a raised
  area then stays deleted. (*Changed by slice 34.*)
- **The dialog** (`handEditsLine` in `utils/roomScan.ts`; no change to
  `RoomScanDialog.tsx`). The one line counts the new things: "Will keep
  your edits on 2 areas and 1 overhead item", "1 overhead item you added
  will be kept", "Will leave out 1 area you deleted" (said first), and "1
  to check against the new room" (said last). The line is a warning when
  something added is replaced, as before, and now also when something is
  to be checked. Strings for raised areas alone are what they were.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_overhead.py` (34):
  the strip and the disc and what they share; the marks Edit Room writes
  on a line and a ring and what is not one; a line's name kept read a
  little off; a trim kept with `top` and the bands; holding at the reading
  after; a ring; the next truss along and a line only moved keeping
  nothing; an added line and ring kept, one that crosses kept, one beside a
  truss replaced, one over the scan's own, one the scan now reads; the
  record a delete leaves and what leaves none; an area left out and its
  record carried on twice; the words; a record dropped; a kind set by hand
  before the delete; deleted and put in again by hand; an edit kept beside
  one left out; a kept height above the ceiling, a kept name that is not
  flagged, an added item outside the walls; no key where nothing is
  flagged; nothing carried with no edits.
  `tests/integration/test_api_room_scan_keep_overhead.py` (8): over HTTP,
  a line's name and trim kept twice running; an added line kept, and
  replaced; a deleted raised area left out in a preview that writes
  nothing (room, undo steps, fixtures) and in two applies; the room's Undo
  forgetting the record; a room taken off and read from scratch; nothing
  left behind by deleting an added area or a line, with both answers' keys
  exactly what they were; a room read at half the size flagging an added
  area outside the walls and an added line above the ceiling. Frontend,
  `RoomScanDialogHandEditsOverhead.test.tsx` (7).
- **One existing test was changed, because the behaviour was.**
  `test_a_rename_changes_the_name_and_nothing_else` (unit) held, since
  slice 32, that a renamed overhead line is the old one but for its name.
  Its `basis` now also says "Name set by hand."; the test holds that for a
  line and a ring. No other existing test changed: no existing test
  compared a whole room after deleting a scanned raised area.
- **What was run** (Nov 24). Backend, with the main checkout's venv, after
  the last backend change: `python -m pytest tests/ -q` **2700 passed, 10
  skipped, 5 xfailed** (2658 before; the 42 new ones are the two files
  above). Frontend: `npx tsc --noEmit -p .` only the 13 older errors, none
  in `roomScan.ts` or the new test file. **`npx vitest run` and `npx vite
  build` were refused in the session**, so the 7 new frontend tests and
  the 8 of slice 32 against the changed helper have not been run, and the
  bundle has not been built with this change. See "What is left".
- **No Art-Net, no DMX, no network call, no new dependency, no new
  column**: the records are in the room's own JSON.

## What slice 32 built

The operator's corrections to raised areas are kept when the scan is
applied again. Until now a scan applied again wrote a whole new room and
kept only the DJ booth mark and that booth's kind: a name typed in Edit
Room, a height set there and a riser added there were all thrown away, so
scanning a venue a second time cost every correction made since the first.

- **No second matcher** (`services/room_scan/keep_mark.py`, `best_match`).
  The loop that decided which raised area of a new reading is the marked
  booth is now a function of its own, and `keep_dj_booth` calls it. Slice
  32 calls the same function for every stored raised area with something
  to keep: the same kind unless the kind was set by hand, footprints turned
  to their headings overlapping by an intersection over union of 0.5 or
  more, the greatest overlap, the earlier of two equal.
- **What says a field was set by hand** (`edit.py`; read by `hand_edits`
  in `keep_edits.py`). Two of the three had no mark, so this slice adds
  them where `edit_item` writes the field:
  - **"Name set by hand."** in the `basis`, when a rename changes a raised
    area's name. `suggested` is not touched: where it stands is still the
    scan's guess. The name a change of kind gives ("Booth or counter") is
    not marked.
  - **"Height set by hand."** and **"Base height set by hand."**, when
    those change, each beside "Resized by hand." as before. "Resized by
    hand." alone could not be used: it is written for a width, a depth and
    a heading too.
  - **`added_by_hand`** (already stored): its height and base height are
    the person's, and its name too unless it is only what its kind is
    called (added without a name).
- **The rule** (`services/room_scan/keep_edits.py`, `keep_hand_edits`):
  1. A stored raised area with any of those that matches a new one gives
     it **the name, the height and the base height that were set by hand**,
     and nothing else. The new one's `basis` gets the same marks (and
     "Resized by hand." with a height, `suggested` false), so the reading
     after this one keeps them too. It is carried and reported whether or
     not the scan happens to read the same value: a height read 2 cm
     different next time must not win.
  2. **The footprint is the scan's**: `center_x`, `center_z`, `width`,
     `depth` and `heading_deg` are the new reading's, whatever was dragged
     or typed. So is the kind (but for the marked DJ booth, slice 31).
  3. **Two stored areas that pick the same new one**: the greater overlap
     has it, the earlier of two equal; the other is treated as matching
     nothing.
  4. **A raised area added by hand that matches nothing and shares no
     floor with any raised area of the new reading is kept as it is**,
     appended after the scan's, so every place the scan gave is what it
     was. It stays `added_by_hand`, and is kept again at each reading.
  5. **One added by hand that matches nothing but shares floor with a new
     raised area is not kept: the new one wins**, and the answer names it
     and what replaced it (the new one it overlaps most). Two that only
     touch along an edge share no floor.
  6. One added by hand that *does* match (the scan now reads it) falls
     under point 1: the scan's footprint with the person's name and
     heights, and no longer `added_by_hand`.
  7. Anything else that matches nothing is not carried and not reported.
  8. **Every stored raised area is asked which new one it is**, with or
     without anything to keep, before point 3 is settled. A riser a person
     added exactly over the scan's own riser therefore does not rename or
     lift the scan's riser when it is read again: the scan's riser is
     itself (the earlier of two equal), and the added one is replaced (5).
  - Pure: neither room is changed, and with nothing to carry the reading
    comes back as the same object.
- **The route** (`api/endpoints/room_scan.py`). `keep_hand_edits` is called
  once, before the mark and before the moves, for a preview and an apply
  alike; `keep_dj_booth` is then asked of the room it returns. That order
  is what makes a marked booth added by hand keep its mark (it matches its
  own kept copy at 1.0), and the mark's sentence use a kept name. The
  moves are suggested for the room with everything carried.
- **The answers.** `hand_edits`, at the top of a preview and inside
  `applied`, **only where something was kept or replaced**: `kept`
  (`index`, `name`, `edits`, `overlap`), `areas`, `added_kept`,
  `added_replaced` (`name`, `by_index`, `by`) and `message`. With no hand
  edit the keys of both answers are exactly what they were. The preview's
  `room_shell` and `summary.raised_areas` are the room apply would store.
- **The dialog** (`RoomScanDialog.tsx`, `handEditsLine` in
  `utils/roomScan.ts`). One line under the DJ booth line
  (`room-scan-hand-edits`): "Will keep your edits on 2 areas", and after
  Apply "Kept your edits on 2 areas"; "1 area you added will be kept" and
  "1 area you added will be replaced by the scan" are joined on with a
  semicolon, and the line is a warning when one is replaced. Nothing where
  the server sends no `hand_edits`.
- **Edit Room's help text** (`RoomShellEditDialog.tsx`) no longer says a
  scan read again replaces every change: it says what is kept.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_edits.py` (24, one
  of them an area added exactly over the scan's own riser): the
  marks Edit Room writes and what is not one (a width, a move, a kind,
  "Resized by hand." alone); a name kept on a raised area read a little
  off; a height and a base height kept against the reading; the footprint
  and the kind the scan's; holding at the reading after and the one after
  that, each mark once; another kind or too far keeping nothing; two
  stored that pick one new area; nothing carried with no hand edits, no
  room, or only a move; an added area kept, replaced, kept when it only
  touches, and matched; a marked added booth keeping its mark; the mark's
  sentence with a kept name; a hand-set kind on the marked one still said;
  the words of a preview and an apply.
  `tests/integration/test_api_room_scan_keep_edits.py` (7): over HTTP, a
  name kept twice running; heights kept; an added area kept where the scan
  has nothing and replaced where it overlaps; a marked added booth; nothing
  carried and no new key with only a move and a width; a preview that says
  what will be kept, writes nothing (room, undo steps, fixtures) and is
  then applied to the room it showed. Frontend,
  `RoomScanDialogHandEdits.test.tsx` (8): the line for kept edits, an
  added area, a replaced one as a warning, nothing sent, after Apply, and
  the helper.
- **Six existing tests were changed, because the behaviour was.**
  - `test_a_rename_changes_the_name_and_nothing_else` (unit) and
    `test_a_rename_is_stored_and_changes_nothing_else` (API) held a
    renamed raised area equal to the old one but for its name: its `basis`
    now also says "Name set by hand.". The unit test gained a line holding
    that an overhead line's rename still changes only the name.
  - `test_a_scan_read_again_replaces_the_edits` and
    `test_a_scan_read_again_clears_the_steps` renamed the stage "Main
    stage" and held the room to be the scan's own afterwards. The name is
    now kept; the deleted line still comes back (*until slice 34*) and the
    undo steps are still cleared.
  - `test_the_same_scan_applied_again_keeps_the_mark` and
    `test_a_preview_over_a_marked_room_writes_nothing_and_says_the_mark_
    will_be_kept` named the marked riser "DJ" and expected "kept on
    Riser"; it is "kept on DJ", and the stored riser carries the name.
- **What was run** (Nov 24). Backend, with the main checkout's venv, after
  the last code change: `python -m pytest tests/ -q` **2658 passed, 10
  skipped, 5 xfailed** (2626 with slice 31's flaky strobe test passing;
  the 31 new ones are the two files above, and one line was added to an
  existing unit test). Frontend: `npx tsc --noEmit -p .` only the 13 older
  errors, none in `roomScan.ts`, `RoomScanDialog.tsx`,
  `RoomShellEditDialog.tsx` or the new test file. **`npx vitest run` and
  `npx vite build` were refused in the session**, so the 8 new frontend
  tests have not been run and the bundle has not been built with this
  change. See "What is left".
- **No Art-Net, no DMX, no network call, no new dependency.**

## What slice 31 built

The preview says what will become of the DJ booth mark, and a kind set by
hand no longer loses it. Slice 30 kept the mark on apply and said so
afterwards; the operator found out only once the room was replaced, and a
scan's riser made a booth by hand lost the mark at every reading, because
the scan calls it a riser again.

- **One rule, asked once** (`api/endpoints/room_scan.py`). The route calls
  `keep_dj_booth` once, before it knows whether this is a preview or an
  apply, and before the fixture moves are suggested. A preview answers
  from the result; an apply stores it. There is no second copy of the
  rule: what a preview says is what `keep_mark.py` would do, and it is
  pure, so asking writes nothing.
- **The preview's answer.** `dj_booth_mark`, **only in a preview and only
  where the room already stored has a marked booth** (`KeptMark.preview()`):
  `kept`, `dropped`, `index` and `name` (the raised area of the new room
  that would keep the mark), `overlap`, `kind_kept` and `message`. A
  preview over a room nobody marked has exactly the keys it had.
  - The preview's `room_shell` is now **the room apply would store**: it
    carries the kept mark and a kept kind. Before, it was the bare reading
    and never carried a mark. With no mark to keep it is the same object as
    before.
  - It is worked out against the room as stored when the preview is read.
    Apply asks again, of the room as it stands then.
- **The kind rule** (`keep_mark.py`, `kind_set_by_hand`). **A kind is "set
  by hand" when the stored raised area says so**: its `basis` contains
  "Kind set by hand." (`KIND_BY_HAND`, which `edit_item` writes whenever a
  kind is changed, in Edit Room or through the API), or it is `added_by_hand` (a person made
  it, kind and all). Nothing new is stored to decide it.
  - For such a marked raised area **the kind is not compared**: a raised
    area of the new reading of any kind whose footprint overlaps by 0.5 or
    more is the same one. The greatest overlap still takes it, and of two
    equal the earlier; a same-kind candidate is not preferred over a
    better-overlapping one of another kind.
  - The one that takes the mark **keeps the person's kind**. It is changed
    as Edit Room would change it: `kind` set, `suggested` false, "Kind set
    by hand." added to its `basis` once, and a name that was only the
    scan's word for what it read ("Riser") becomes the kept kind's
    ("Booth or counter"). The `basis` is what makes it hold at the reading
    after this one, and the one after that.
  - It is any hand-set kind, not only booth: a scan's booth made a riser
    and marked stays a riser.
  - Where the reading agrees with the hand (the scan now reads a booth
    there itself), only the mark is written and nothing is said of the
    kind: the raised area is the scan's again.
  - A marked raised area whose kind was **not** set by hand is matched on
    its kind exactly as in slice 30.
  - `applied` gains `dj_booth_kind_kept` only where a kind was kept, and
    `dj_booth_message` then reads "The DJ booth mark was kept on Booth or
    counter. It stays a booth, as set by hand: this scan reads it as a
    riser."
- **The moves follow the room that would be stored.** `suggest_positions`
  is now given the shell with the kept kind, since it reads the room's
  first stage. For every room without a kept kind the shell differs from
  the reading only by the mark, which the suggestion does not read.
- **The dialog** (`RoomScanDialog.tsx`, `djBoothPreviewLine` in
  `utils/roomScan.ts`). Under the "This is a preview" note, before Apply:
  "DJ booth mark: kept on Riser" as a plain line, or "DJ booth mark will be
  dropped" as a warning (`room-scan-dj-booth-preview`). A kept kind adds
  "(stays a booth, as set by hand)". Nothing for a room with no marked
  booth, and the line goes once the scan is applied: slice 30's warning
  speaks then.
- **Tests.** Backend, `tests/unit/test_room_scan_keep_mark.py` (+13, 52):
  what says a kind was set by hand; a hand-set booth read as a riser and as
  a stage keeps mark and kind, with the reading's place and size; the same
  at the reading after and the one after that, the basis saying it once;
  the overlap still asked (near is dropped, a half is enough); the greatest
  overlap of any kind; a reading that agrees left the scan's; a name the
  scan did not give left alone; a hand-set riser and an added booth; and
  what a preview says for kept, dropped, a kept kind and no mark.
  `tests/integration/test_api_room_scan_keep_mark.py` (+5, 13; the fifth,
  a stage made a booth by hand whose previewed moves are the ones applied,
  was added after the full run below and run with these two files, 65
  passed): a preview
  that says kept, writes nothing (room, undo steps, fixtures) and is then
  applied to the same room it showed; a preview that says dropped and
  writes nothing; a preview that says a hand-set kind will be kept; a
  preview over an unmarked room with exactly its old keys; a hand-set kind
  applied twice over HTTP; a kept mark with no kind to speak of. Frontend,
  `RoomScanDialogDjBoothPreview.test.tsx` (8): both lines in the dialog,
  the kept kind, nothing without a mark, gone after Apply, and the helper.
- **Two existing tests were changed, because the behaviour was.**
  `test_a_kind_changed_by_hand_drops_the_mark` is now
  `..._keeps_the_mark_and_the_kind`: it asserted the very loss this slice
  removes. `test_a_preview_over_a_marked_room_writes_nothing_and_says_
  nothing_of_the_mark` is now `..._says_the_mark_will_be_kept`: its
  `marked(preview["room_shell"]) == []` no longer holds, the preview
  showing the room apply would store; what it checked about writes is kept
  and widened. One unit test's comment was corrected, not its assertions.
- **What was run** (Nov 24). Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2625 passed, 1 failed, 10 skipped, 5
  xfailed** (2609 passed before the slice; the 17 new ones are in the two
  files above). The one failure is not this slice's:
  `tests/integration/test_dmx_review_fixes.py::test_strobe_test_pattern_
  stays_under_the_show_flash_limit` counts flashes over one second of wall
  clock, counted 4 against a limit of 3 while the type-check was running
  beside it, and passed when its file was run again alone (22 passed). The
  room scan, room shell and DJ booth tests run on their own: 1080 passed.
  Frontend: `npx tsc --noEmit -p .` only the 13 older errors, none in
  `roomScan.ts`, `RoomScanDialog.tsx` or the new test file. **`npx vitest
  run` and `npx vite build` were refused in the session**, so the 8 new
  frontend tests have not been run and the bundle has not been built with
  this change. See "What is left".
- **No Art-Net, no DMX, no network call, no new dependency.**

## What slice 30 built

The DJ booth mark is kept when the scan is read again. Slice 28 put the
mark on one raised area of the stored room; a scan applied again writes a
whole new room, whose raised areas carry no mark and no id, so the mark was
lost every time.

- **The rule** (`services/room_scan/keep_mark.py`, `keep_dj_booth`). On
  apply, with the room being replaced still in hand:
  1. The old room's marked raised area is found (`dj_booth_place`: the
     first, should a shell written by hand mark two). With none, nothing is
     done and the answer is what it always was.
  2. A raised area of the new reading can take the mark only if it is **the
     same kind** (`stage`, `riser` or `booth`) as the marked one is now, and
     **its footprint overlaps the marked one's by an intersection over union
     of 0.5 or more** (`MATCH_IOU`). The footprints are the rectangles on
     the plan turned to their headings (`area_corners`), cut against each
     other as polygons: a booth standing at a heading is compared as it
     stands, a reading a few degrees further round still matches, and the
     same rectangle stored as 2 x 1 at 0 degrees or 1 x 2 at 90 is the same
     footprint. Heights are not looked at.
  3. **Of several that pass, the greatest overlap takes it; of two that
     overlap exactly as much, the earlier in the list.**
  4. **With none that passes, the mark is dropped**, and the answer says so.
     It is never given to the nearest raised area or to the scan's first
     booth: a mark set by hand is kept where it was or not at all.
  - Half is what lets a 2 m booth be read 0.6 m off and refuses one read
    0.7 m off; two booths side by side share nothing.
  - *Only the mark is carried.* The name, kind, size and place set by hand
    on the old raised area are not: the new room is the scan's, and the
    kept raised area is still its suggestion (`suggested`, `basis` as read).
    (Slice 31 carries a kind set by hand as well, and does not compare it.
    Slice 32 carries a name, a height and a base height set by hand, for
    every raised area and not only the marked one.)
  - *One at a time.* The kept mark is the only one in the new room.
  - Pure: neither room is changed, and a room with no mark to keep comes
    back as the same object.
- **The route** (`POST /api/rigs/{id}/room-scan?apply=true`). The stored
  room and the answer's `room_shell` carry the kept mark. `applied` gains
  `dj_booth` (the place, or null), `dj_booth_dropped`, `dj_booth_overlap`
  and `dj_booth_message` ("The DJ booth mark was kept on Booth or counter."
  / "The DJ booth mark was dropped: no raised area in this scan stands where
  DJ did. Mark the DJ booth again in Edit Room."), **only where the room
  replaced had a mark**; `applied.message` is not changed. In this slice a
  preview looked at nothing and said nothing of the mark; since slice 31 it
  says what apply will do.
- **The room's Undo is emptied by an apply, as before.** Its steps were
  edits to the room that was replaced, so after a scan is applied again
  there is nothing to take back: a dropped mark is not brought back by
  Undo, and a kept one is not a step. This was so before the slice and is
  not changed; the next edit (taking the kept mark off, say) is step one
  and can be undone. *Undo room scan moves* is about fixtures and is not
  touched by the mark.
- **The dialog** (`RoomScanDialog.tsx`, `djBoothDroppedText` in
  `utils/roomScan.ts`). After Apply, where `dj_booth_dropped` is true, a
  warning under the stored message with the server's sentence (or the
  dialog's own, `DJ_BOOTH_DROPPED_TEXT`, where none was sent). Nothing is
  shown for a kept mark, a room that had none, or a preview (a preview has
  its own line since slice 31).
- **Tests.** Backend: `tests/unit/test_room_scan_keep_mark.py` (39): the
  overlap in numbers worked by hand (a shift, one inside another, a quarter
  turn stored either way, two squares 45 degrees apart sharing an octagon,
  +30 against -30, an area with a number missing); the same booth read a
  little off keeps the mark and only the mark; the mark following the booth
  to another place in the list; no match dropped with its sentence; a booth
  that only stands near, and the half exactly; another kind in the same
  place; a kind changed by hand; a marked stage with a riser on it; two
  candidates in either order; two equal ones; a booth at a heading read 3
  degrees further round, stored the other way round, swung across itself,
  and read square; a room with no mark; a room marking two; a reading that
  came marked; neither room changed.
  `tests/integration/test_api_room_scan_keep_mark.py` (8): over HTTP, the
  same scan applied again keeps the mark in the answer, the column and the
  rig, moving no fixture; a booth nudged 0.3 m by hand is kept (overlap
  1.7 / 2.3); one moved 4 m and one made another kind are dropped and said;
  the room's Undo emptied by the apply, not bringing a dropped mark back,
  and working again for the next edit; an unmarked room's `applied` has
  exactly the keys it had; a preview writes nothing; the room read a
  quarter turn round drops it. Frontend:
  `RoomScanDialogDjBoothDropped.test.tsx` (6): the warning with the
  server's sentence beside the stored message, the dialog's own words,
  nothing for a kept mark or no mark or a preview, and the helper.
- **No existing test was changed.**
- **What was run** (Nov 24). Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2609 passed, 10 skipped, 5 xfailed** (2562
  before the slice; the 47 new ones are the two files above). Frontend:
  `npx tsc --noEmit -p .` only the 13 older errors, none in `roomScan.ts`,
  `RoomScanDialog.tsx` or the new test file. **`npx vitest run` and
  `npx vite build` were refused in the session**, so the 6 new frontend
  tests have not been run and the bundle has not been built with this
  change. See "What is left".
- **No Art-Net, no DMX, no network call, no new dependency.**

## What slice 29 built

The Room Scan dialog shows the turn. Slice 27 turns each fixture of a row
laid on a stage that stands at a heading, and the answer says by how much
(`turn_deg`), but the dialog's table had no column for it: the only word of
it was in the move's reason. Frontend only; no backend file was changed.

- **The words** (`utils/roomScan.ts`). `RoomScanMove` has `turn_deg`, which
  the server sends only where a fixture is turned.
  - `turnText(move)` is the cell: "30 deg", "-12.5 deg", to a tenth of a
    degree (what a heading is stored to) and with its sign, clockwise seen
    from above as the server gives it. A dash (`NO_TURN_TEXT`) for 0, for a
    move with no `turn_deg`, for anything that is not a number, and for a
    turn too small to show as a tenth, so there is never a "0 deg".
  - `turnedCount(moves)` counts the moves whose cell is not a dash.
  - `turnSummaryText(moves, applied)` is the sentence: "2 of them will also
    be turned with the stage, which stands at a heading." ("All 3", "Both"
    or "It" where every move turns), in the past once applied ("were",
    "was"), and nothing at all when no move turns. `fixtureMoveText` is not
    changed, so a room standing square reads word for word as it did.
- **The dialog** (`RoomScanDialog.tsx`). A **Turn** column between the
  positions and Why, with a tooltip saying which way round it is. The
  sentence above the table has the turned count after the count of moves.
  After Apply the table and the column stay; the sentence says how many
  were turned only when fixtures were moved, so storing the room with the
  box unticked does not say a fixture was turned.
- **No ghosts, so none turned.** The dialog draws no fixture at its
  suggested place, in 3D or in 2D: the preview is held in the dialog alone
  and handed to no view. No preview was added.
- **Tests.** `roomScan.test.ts` ("the turn of a move", 6 tests): the text to
  a tenth and with its sign; the dash for 0, -0, no key, null, a string, NaN,
  infinity and 0.04 either way; the count; the sentence for some, all, both
  and one, before and after apply; and `fixtureMoveText` unchanged.
  `RoomScanDialogTurn.test.tsx` (7 tests, the dialog drawn with a mocked
  API and a file chosen): the five headers in order; 30, -12.5, 0 and a
  missing key in their rows, the cell fourth in its row; the sentence with
  the count and with "All 3"; no word of a turn where none turns, the whole
  sentence as it was; and after Apply, the count in the past with fixtures
  moved and nothing with only the room stored.
- **What was run** (Nov 24). `npx tsc --noEmit -p .`: the 13 older errors
  and no other, none in `roomScan.ts`, `RoomScanDialog.tsx` or either test
  file. **`npx vitest run` and `npm run build` were refused in the session**
  (in both shells), so the 13 new tests have not been run and the bundle
  has not been built with this change. The backend was not touched and its
  suite was not run again. See "What is left".
- **No Art-Net, no DMX, no network call, no new dependency.**

## What slice 28 built

"This one is the DJ's booth", and cameras that look at it. Until now the
desk went on the first raised area of kind `booth`, which a scan also calls
a bar counter, and the DJ and Floor cameras looked at the booth the view
makes up against the upstage wall whatever the room had.

- **The mark** (`edit.py`). `is_dj_booth: true` on one raised area of the
  stored room. It is kept on the raised area itself, not as a place in the
  list: the lists carry no ids, and a place would have to be counted again
  at every delete. So it goes where its raised area goes, goes out with it,
  and comes back with it when the room's Undo puts the room back.
  - *One at a time.* Marking one takes the mark off every other in the same
    edit. One that is not marked stores no key at all (never `false`), so a
    room nobody marked one in is byte for byte what it was.
  - *Any kind.* A stage or a riser can be marked as well as a booth: the DJ
    who plays on the stage, in a room whose only "booth" is the bar.
  - *A change of kind takes it off*, unless the same request sets it: it
    was the booth as what it was. Edit Room's row sends the mark along when
    its box is ticked, so changing the booth's kind there keeps it.
  - *A deleted booth takes its mark with it.* Nothing is promoted in its
    place; the view then goes back to the first `booth`, or its guess.
  - *It moves nothing*, and does not make the raised area a person's
    (`suggested` and `basis` are left): it says whose it is, not where.
  - *A stack.* A riser carried with the stage under it is written back from
    the room as it was (`carry.apply_areas`); where that riser was the booth
    and the same edit marked the stage, `one_dj_booth` takes its mark off.
  - `dj_booth_place(shell)` is the marked place, or None: the first, should
    a shell written by hand mark two. Only a stored `true` is a mark.
- **The routes.** `PATCH .../room-shell/risers/{index}` and
  `POST .../room-shell/risers` take `is_dj_booth`; both answers and the
  DELETE's carry `dj_booth` (the marked place or null). Refused with 422 in
  a sentence: anything but true or false (a raw `Infinity` included), and a
  truss or a ring. 404 for a raised area the room does not have. 409 during
  a locate walkthrough, before the body is looked at, as every room edit.
  One undo step each ("Decks marked as the DJ booth", "... no longer marked
  as the DJ booth"); marking the one already marked writes nothing and
  leaves no step. The mark is read back with the rig like the rest of the
  room. No migration: the room is one JSON column.
- **Which booth** (`previs/boothPick.ts`, `pickDjBooth`). The marked raised
  area (`'marked'`); else the first of kind `booth` (`'scan'`); else the
  first stage (`'guess'`); else none. One function for the 3D view and the
  2D plan, over the same list (`scanRisers`), so they cannot disagree.
- **The desk** (`scanFloor.ts`, `placeScanBooth`). How a booth is drawn now
  goes by what the raised area is, not by how it was chosen: a stage is
  played from its downstage edge with a desk half its width; anything else
  is a booth facing the open floor, the counter itself from 0.6 m and a
  platform with a desk under that. With no mark a guess is always on a stage
  and a scan's booth never is, so those rooms come out exactly as they did
  (tested as a deep-equal booth and the same crowd). **The amber mark is
  drawn only for a guess**, as before: a marked booth has none.
- **The cameras** (`previs/boothCamera.ts`, `boothCameraPreset`). In a
  scanned room with a booth, the DJ and Floor cameras are worked out in the
  booth's own frame: forward is the way it faces and right is
  `(faceZ, -faceX)`, so a booth at a heading has its cameras at that heading.
  - *Floor.* Straight out from the middle of the booth's front face, 0.85 m
    short of the wall it faces (`distanceToWall`), looking at the front face
    1.55 m above the decks. Where that spot is within 0.6 m of another wall
    or over a raised area it comes back towards the booth 0.1 m at a time,
    never nearer than 1 m. With nowhere on that line (a booth facing a
    wall) it stands where it did and is turned to the booth.
  - *DJ.* 1.25 m behind the DJ and 0.95 m to the booth's right, 2.3 m above
    what the DJ stands on. Where a wall is within 0.3 m behind that spot, or
    in front of it, a metre behind that wall instead: every wall is drawn
    only from its room side (`ClubRoom.tsx`, `RoomShellView.tsx`), so the
    camera looks straight in. It looks 0.375 m and 0.35 of the floor between
    the booth and the wall it faces out in front, at 1.2 m, brought 0.6 m in
    from a wall with `insetPoint`.
  - *The numbers are the made-up booth's own*, read from the room and not
    from the layout: a booth standing where the view's own would stand has
    both cameras exactly where they always were (tested against
    `cameraPreset`).
  - *Left alone:* `cameraPreset` is not changed. A room with no scan, a
    scanned room with no booth, and the Iso, Top, Front and Audience cameras
    get the preset back as it is, the same object.
  - *The crowd* leaves room where the Floor camera now stands. In a scanned
    room whose booth is not upstage centre that is a different place, so
    that room's crowd is a different crowd from before this slice.
  - The view's key (`scanFloorKey`) carries `is_dj_booth` only where it is
    true, so marking a booth places the booth and the crowd again and an
    unmarked room's key is the text it was.
- **Edit Room** (`RoomShellEditDialog.tsx`, `roomShellEdit.ts`). A "DJ
  booth" box on each raised area's row, beside its Kind. It is saved with
  the row's Save, like the kind, and taken back by the dialog's Undo. Once a
  row is saved as the booth, a box ticked on another row and not saved is
  let go, so two rows never show as the booth. The mark is not a change that
  carries fixtures (`withCarry`). The Add form has no box: add the raised
  area, then tick its row. Items mode on the plan edits no kind and has no
  box either.
- **The 2D plan** (`roomPlan2d.ts`, `djBoothTag`; `StageView2D.tsx`). The
  raised area the 3D view puts the DJ on has a small "DJ" above its label,
  or an amber "DJ?" where it is only a guess, with a tooltip that says how
  it was chosen and to mark the right one in Edit Room. No label, tooltip or
  bound of the room layer is changed by it.
- **Tests.** Backend: `tests/unit/test_room_scan_dj_booth.py` (22) and
  `tests/integration/test_api_room_shell_dj_booth.py` (9): marking, one at a
  time, any kind, a change of kind with and without the mark, the words for
  the undo, delete and add, the stack, the refusals, the round trip through
  `GET /api/rigs/{id}` and the database column, three undo steps walked
  back, and the locate walkthrough. Frontend: `boothPick.test.ts` (the
  pick, the scanFloor choice, the plan's tag in numbers),
  `StageView2DDjBooth.test.tsx` (the tag drawn), `boothCamera.test.ts`
  (heading 0, a booth elsewhere, turned 30, -60 and 90 against the heading-0
  result turned in the test, a booth `placeScanBooth` placed, the view's own
  booth, a room with no scan) and `RoomShellDjBoothDialog.test.tsx` (the
  box, what it sends, Undo, one at a time, the helpers).
- **What was run** (Nov 24). Backend, with the main checkout's venv:
  `python -m pytest tests/ -q` **2562 passed, 10 skipped, 5 xfailed** (2531
  before the slice; the 31 new ones are the two files above). **The frontend
  was run afterwards** (Nov 24): `npx vitest run` 59 files, 1222 passed;
  `npm run build` OK; `npx tsc --noEmit` only the 13 older errors; and the
  backend again 2562 passed, 10 skipped, 5 xfailed. When the slice was
  written none of the frontend was run: the worktree had no
  `frontend/node_modules`, and `npm ci`, `npx vitest run`, and `node` on the
  main checkout's `tsc` were each refused, so the expected numbers in the
  tests were worked out by hand. It has not been seen in a browser: see
  "What is left".
- **No Art-Net, no DMX, no network call, no new dependency.**

## What slice 27 built

The suggestion goes by a stage that stands at a heading. Until now
`suggest.py` read the first stage's middle and sides and nothing else, so a
row was fitted to a turned stage as though it stood square: parallel to the
walls, and partly off the deck. Backend only.

- **The suggestion** (`suggest.py`, `_onto_turned_stage`). The stage's
  heading is read with slice 21's own `area_heading`, and a row is swung
  with `carry.py`'s `_swung`, so the plan is turned the same way round here
  as when a stage is turned by hand in Edit Room.
  - *The rule* is the square rule, in the stage's own two ways. The row's
    place from the stage's middle is taken along the stage's width and from
    its back to its front; it is fitted there as it always was (the same
    test for "is this row the stage's", the same lift onto its top, the
    same 0.3 m in from its edges, the same note when it is wider than the
    stage); and the result is swung about the stage's middle by the
    heading. What comes out is what the old rule gives for the stage
    standing square, turned as a person turning the stage with its box
    ticked would turn it.
  - *A row no scan has moved* was drawn for a stage standing square, so its
    place from the stage's middle is taken as it is and the whole row is
    swung. *A row a scan has moved* (`position_hint:room_scan` on any
    fixture of it) is already turned: it is un-swung to be read, fitted,
    and put back, and nothing is turned. That is what makes the same scan
    read twice move nothing, at 90 degrees too, where a swung row looks
    like one that was never swung.
  - *Aim.* Each move carries `turn_deg`, the heading. `turned_rotation`
    takes it off `rotation_y`, which runs the other way round from a
    heading: the sign `carry.py` uses.
  - *The walls and the ceiling* are held on the swung places: one shift for
    the row into the room's box (0.2 m in), then into the floor outline;
    a guess at a time only where the row fits nowhere whole, with the old
    notes. Nothing is lifted to within 0.3 m of the ceiling (`CEILING_DROP`).
  - *Settled at once.* A fit to a turned stage and a hold to the walls pull
    along different ways, so doing both twice need not give the same place
    twice, as it does when both go along the room's axes. So where the
    walls moved a row, the stage's rule is asked once more from where the
    walls left it and its answer is taken if the walls let it stand; and a
    laid row that stands inside the walls, which the walls would move
    again, stays where it is.
  - *Heading 0 or none is the old code*, not the new code given a zero: the
    branch is taken only when `area_heading` is not 0, so 0, 180, 360, a
    string, a boolean and a number past 360 all leave the old lines to run
    untouched. A stage with a number missing (no height, say) cannot be
    stood on at any heading: the row is held to the walls as though there
    were no stage, where it used to stop the scan with an error.
  - *A row that is not the stage's* (downstage of its turned front, or off
    its width) falls through to the walls, as before. Overhead rows never
    read the stage.
  - *The corner and the ungrouped row.* A stage across a corner is written one way (heading over -45, up to 45, never dropped at -45), and ungrouped floor fixtures a scan has swung are one row by their depth on the stage, not in the room (each within 0.05 m of the next, `SWUNG_ROW_GAP`, not by a rounded depth), so a row wider than the stage is not closed up a fixture at a time on the next scan.
- **The route** (`POST .../room-scan`). Apply writes `rotation_y` for a move
  with a `turn_deg`, and the fixture's entry in the undo record keeps
  `rotation_y_before` and `rotation_y_after`. The answer's moves have
  `turn_deg` only where a fixture is turned, so every other answer is what
  it was.
- **The undo** (`undo.py`). A fixture the scan turned is turned back with
  its position, when it still faces the way the scan left it (to 0.01 of a
  degree). One somebody has turned since goes back to where it stood and
  keeps the way it faces. A second scan over the first keeps the first's
  `rotation_y_before`. An entry for a move that turned nothing has neither
  key, and a record written before this slice is read as it was.
- **The scan finds a turned stage** (`extract.py`, `_turned_box`,
  `_turn_box`). Without this the rule above could never run from a scan: a
  scan measured every raised area along the room's axes, and
  `suggest_positions` is only ever given the shell the scan just made.
  - *No format gives it.* A RoomPlan object's transform and a glTF node's
    rotation are already applied to the vertices by the readers, and a
    stage is not a named object in any of them: it is a level patch found
    among the points. So the heading is read from the patch's shape, which
    works for every format alike.
  - *How.* The box round the patch's points is measured at each heading
    from -45 to 45 degrees (half a degree apart, then a twentieth round the
    best), and the smallest is the patch's own. It is kept only when it is
    turned 5 degrees or more (`RAISED_TURN_MIN_DEG`), is at most 0.9 of the
    box along the room's axes (`RAISED_TURN_MAX_SHARE`; a rectangle turned
    5 degrees is under 0.86 of it), and the patch fills at least 0.8 of it
    (`RAISED_TURN_MIN_FILL`). A stage standing square, one a degree or
    three off, a round riser, an L and a corner piece fail one of those and
    are measured exactly as before.
  - *What is stored.* Its own middle, `width` along the heading, `depth`
    square to it, and `heading_deg` to a tenth, as Edit Room stores one.
    The heading is over -45 and up to 45, with the sides changed places
    where needed, so `depth` runs to the edge that faces most nearly
    downstage: that edge is its front. A quarter turn of the room
    (`rotate`, or the turn that puts the stage upstage) turns it with the
    room. Its `basis` and a line in `assumptions` say it stands turned, and
    that Heading 0 in Edit Room squares it.
  - *Left as it was:* which wall is upstage still goes by the box round the
    stage along the room's axes; a turned stage's edges are not snapped to
    a wall 0.15 m away; and a raised area with no heading has the same keys
    and numbers as before.

## What slice 26 built

A scan sent as a zip: `POST /api/rigs/{rig_id}/room-scan` takes a `.zip` and
reads the scan inside it. Polycam and Scaniverse often share a scan that way,
a `.gltf` with its `.bin` and textures or an `.obj` with its `.mtl` and
textures. Until now a zip was taken for a USDZ and refused, and a `.gltf`
with a separate `.bin` could not be sent at all.

- **The reader** (`backend/app/services/room_scan/bundle.py`, `parse_zip`,
  standard library only): Python's `zipfile` over the uploaded bytes. Nothing
  is unpacked to disk, so no name in the archive is ever a path on this
  machine. It ends in the same `ScanMesh` every other reader makes, so
  `extract.py`, `suggest.py` and the route's answer are unchanged.
- **Which reader** (`detect.py`). A USDZ is a zip too, and both start `PK`.
  An archive named `.usdz` goes to the USDZ reader, as before. An archive
  under any other name (`.zip`, or none) is read as a zip that holds a scan.
  A USDZ that has been renamed `.zip` is still read: its USD layer is a model
  like any other, a layer named `.usd` included. A file named `.zip` that
  does not start like one is sent to the zip reader all the same, so that
  the refusal says "the zip is damaged" and not "this is not a scan"; a GLB
  or a PLY given the name `.zip` is still known by its first bytes.
- **A zip is not trusted.** Checked before a byte of any file is unpacked,
  and each a 400 with the fix in its words:
  - *Names.* An absolute name (`/x`, `C:/x`, `\\server\x`) or one that climbs
    out with `..` refuses the whole zip, a good scan beside it included.
    Nothing would have been written there; a zip like that is not a scan
    export, and it is said so. `my..scan/model..v2.obj` is only a name.
  - *How many.* More than 2,000 files (`MAX_ZIP_ENTRIES`). The count and the
    size of the zip's directory are read from the record at the end of the
    file first (the zip64 one too, past 65,535 files), so a zip that lists a
    million files is refused before `zipfile` reads the list.
  - *A password.* One encrypted file refuses the zip: "Zip the scan again
    without a password."
  - *How big.* The sizes the zip gives for its files, added up over every
    file in it (textures and junk too), may not pass the upload limit, 200 MB
    (`MAX_UPLOAD_BYTES`, now in `mesh.py`, and the route imports it). A zip is
    held to what a file sent on its own would be. This is the check a zip
    built to swell runs into: five megabytes of zeros in a few kilobytes is
    refused on what the zip says, with nothing unpacked.
  - *What it then unpacks to.* A file is read to the size the zip gave for it
    and no further (`zipfile` stops there, and the read here asks for one
    byte more to see). One that holds more, or less, than was said fails its
    checksum or its length and is refused as damaged. Every line of the
    directory pointing at the same packed bytes is counted once for each
    line, and unpacked once.
  - *Damage.* Not a zip, cut short, a changed byte (the checksum), or a
    compression `zipfile` does not have (the message says to zip again with
    ordinary compression): each in words, never a 500.
- **Only the scan is unpacked**: the model, and the buffers a glTF names.
  Textures, `.mtl` files and everything else are never opened, so a texture
  packed some way `zipfile` cannot read does not matter.
- **Which file is the scan.** Left out of the search: folders, macOS's
  `__MACOSX` copies, and anything in a folder or with a name that starts
  with a dot (`.DS_Store`, `._scene.gltf`). A model is a file ending `.glb`,
  `.gltf`, `.usdz`, `.usdc`, `.usda`, `.obj`, `.ply` or `.json` (and `.usd`,
  which is taken with `.usdc` and read as whichever form its first bytes
  say). A `.json` counts only when it holds `"walls"` (RoomPlan) or is a glTF, so an app's
  own notes about the scan (`mesh_info.json`) are not taken for it and not
  mentioned. A zip inside the zip is not opened.
  - *Several models* are taken in that order, the whole scan in one file
    first; of two of a kind the one nearer the top of the zip, then the first
    in the archive. The first assumption in the preview is "Read
    'scan/scene.gltf' from the zip.", and another names the models that were
    left alone (the first five, then how many more).
  - *One that cannot be read gives way to the next.* A Draco-packed `.glb`
    beside an `.obj` gives the `.obj`, and the preview says the `.glb` "was
    tried first and could not be read", with the reason. This is more than
    was asked for: the alternative was refusing a zip with a readable scan
    in it and telling the operator to export the OBJ that was already there.
    When none can be read, the refusal is the first one's, with its name.
  - *No model*: "The zip holds no scan this can read", with the endings that
    are read and the first three files that were found.
- **A `.gltf` and its `.bin`** (`gltf.py`). `parse_gltf` and `parse_glb` take
  an optional `resolve(uri)`, which `bundle.py` gives them: the reader knows
  nothing of zips, and the zip knows nothing of glTF but where to look. A
  buffer's `uri` is looked up relative to the `.gltf`'s own folder,
  percent-decoded first (`my%20scan.bin` is `my scan.bin`) and then as
  written (some apps do not encode, and a file can really be named
  `a%20b.bin`), with a backslash read as a slash and capitals let off when
  no name matches exactly. `../buffers/scene.bin` is followed while it stays
  inside the zip. A `uri` that leaves the zip, starts with `/`, or has a
  scheme (`file:`, `https:`, `C:`) is refused; nothing is ever fetched from
  outside the upload. A `data:` URI is read as before. A file in `__MACOSX`
  or a hidden folder is not a buffer.
  - *A missing `.bin`*: "'scan/scene.gltf' in the zip could not be read. It
    needs 'scene.bin', and that file is not in the zip. Zip the .gltf
    together with its .bin and send that, or export the scan as .glb".
  - *A `.gltf` sent on its own* whose buffers are `data:` URIs is read, as
    since slice 25. With a separate `.bin` it is still refused, and the
    message now says how to get it in: "keeps its mesh in a separate file
    ('scene.bin'), and only one file was sent. Zip the two together (with
    any other .bin beside them) and send the zip, or export the scan as
    .glb, which is the whole scan in one file, or export OBJ."
- **The answer.** `file` is the zip's name, as is `room_shell.scan.file` once
  applied; `format` is the model's (`gltf`, `obj`, ...), never `zip`. Which
  file was read is in `assumptions`.
- **The dialog** (`frontend/src/utils/roomScan.ts`, `RoomScanDialog.tsx`):
  `.zip` is the last ending in `ROOM_SCAN_ACCEPT`, and the help text says
  "If the app shares a zip (a glTF with its .bin, or an OBJ with its
  textures), choose the zip as it is." The server's "send one of these"
  names a zip too.
- **Tests.** Every zip is built in the test with `zipfile` (`write_zip` in
  `room_scan_meshes.py`, which now takes a compression). The ones `zipfile`
  will not write are made by changing bytes of one it did (`forged` in
  `test_room_scan_zip.py`: a file's flags, compression method and stated
  size, in both of its headers).
  - `backend/tests/unit/test_room_scan_zip.py` (88): a `.gltf` and its `.bin`
    give the mesh the `.glb` does, stored and deflated; the `.bin` found in a
    folder, up and across, percent-encoded, not encoded, really named with a
    `%20`, with other capitals and with a backslash; two `.bin` files; a
    `.gltf` with its data inside it; a `.glb` with a buffer beside it; a
    missing and a cut-short `.bin`; seven URIs that point outside the zip; a
    lone `.gltf` told to send the zip. An `.obj` with its `.mtl` and textures
    giving the room its `.obj` gives; each of the eight formats from a zip; a
    USDZ renamed `.zip`; a layer named `.usd` in either form; `.usdz` still
    going to the USDZ reader; a file named `.zip` with its first bytes gone,
    and a GLB named `.zip`; a zip in a
    zip, and a `.glb` that is really a zip, not opened. The order of the
    eight, pair by pair and all at once; two of a kind; a Draco `.glb` and a
    `.gltf` without its `.bin` giving way to the `.obj`; none readable; an
    empty model; an app's own JSON; RoomPlan JSON beside a model. `__MACOSX`
    and dot files; a zip of only junk. Eight names that point outside; the
    2,000-file limit at and over it; a forged count and an over-long
    directory refused before `zipfile` is called; 65,540 files through the
    zip64 record. Sizes added up before anything is unpacked, exact to the
    byte; a file holding more and less than the zip says, stored and
    deflated; two names for one file. A password; an unknown compression on
    the model and on a texture; not a zip; cut at every seventh length; a
    changed byte; and 400 copies with bytes changed at random, each read or
    refused in words.
  - `backend/tests/integration/test_api_room_scan_zip.py` (5), through the
    route with the hall of the glTF tests: a deflated zip of a `.gltf`, its
    `.bin`, a texture and macOS's leftovers previews as the same room as the
    `.glb`, to the last digit, names the file it read and writes nothing; a
    zip of an `.obj`, `.mtl` and textures is applied and read back off the
    rig; a zip of three models reads the `.glb` and names the other two; a
    missing `.bin`, a lone `.gltf`, a climbing name, a password, not a zip,
    a cut-short zip, no model and a lying size are each a 400 with their
    words and nothing stored; and a zip over the upload limit is a 413.
  - `frontend/src/__tests__/roomScan.test.ts`: the exact-order test of the
    accept list holds nine endings, `.zip` last. **Not run** (below).
- **What was run** (Nov 24), from `backend/` with the main checkout's venv:
  `pytest tests/unit tests/integration -k room_scan`: 779 passed (686 before
  this slice; 88 and 5 more). The whole suite, `pytest -q -p
  no:cacheprovider`: 2389 passed, 10 skipped, 5 xfailed
  (2296 passed before this slice, by the same count: 93 more).
- **What was not run.** The frontend, again: this worktree has no
  `frontend/node_modules`, and `npm ci` and `npx vitest run` were both
  refused, so `npx tsc --noEmit` and `npx vite build` could not run either.
  The frontend change is one ending added to a constant, one sentence of
  help text, a comment and one changed test, none of it executed. In
  `frontend/`: `npx vitest run`, `npx tsc --noEmit` (13 older errors
  expected) and `npx vite build`. **No zip from a real phone or app has been
  read**, and the dialog has not been opened in a browser with one.
- **Nothing here sends Art-Net or DMX**, opens a socket or calls an outside
  service. No new dependency and no migration.

## What slice 25 built

glTF 2.0 import: a `.glb` or a `.gltf` goes through `POST
/api/rigs/{rig_id}/room-scan` and is previewed and applied like an OBJ. Until
now a GLB was refused with "not read yet", and it is the default export of
Polycam, Scaniverse and most LiDAR apps.

- **The reader** (`backend/app/services/room_scan/gltf.py`, standard library
  and numpy, no new dependency): `parse_glb` (the 12-byte header, the JSON
  chunk, the BIN chunk) and `parse_gltf` (the JSON, its buffers as base64
  `data:` URIs). Both end in the same `ScanMesh` the OBJ and PLY readers
  make, so `extract.py` and `suggest.py` are unchanged.
- **What is read.** Every mesh the default scene draws (`scene`, else the
  first scene, else every node that is nobody's child; with no nodes at all,
  every mesh where it lies). Each primitive's `POSITION` (FLOAT, VEC3), by the
  buffer view's `byteOffset` and `byteStride` and the accessor's own
  `byteOffset`, so an interleaved buffer reads. Indices as UNSIGNED_BYTE,
  UNSIGNED_SHORT or UNSIGNED_INT; a primitive with none is three corners to a
  triangle in turn. Triangles (mode 4), strips (5) and fans (6) become
  triangles. Points (mode 0) and lines (1, 2, 3) have no surface: a file
  with no triangle at all is read as a point cloud of their points, like a
  PLY with no faces, and beside a mesh they are left out and the preview
  says so.
- **Nodes.** A mesh is put where its nodes place it: each node's `matrix`
  (sixteen numbers, column by column) or its translation, rotation (a
  quaternion, x y z w) and scale, times its parent's. A mesh drawn by two
  nodes is read twice. The walk is a loop with a list, not recursion, and a
  node reached twice (a loop in the file) is refused.
- **Axes and units.** glTF is Y-up and in metres by definition. Nothing is
  turned or scaled in the reader: the mesh says `up_axis: y` and
  `metres_per_unit: 1.0`, as a USD layer does, and the preview's assumptions
  read "the file says so". The dialog's Units and Up axis still win over the
  file, for an exporter that wrote something else.
- **Refusals**, each a 400 whose `detail` says what to do:
  - `KHR_draco_mesh_compression` or `EXT_meshopt_compression` in
    `extensionsRequired`, or a primitive whose points are only in its Draco
    data: "Export the scan again without Draco or mesh compression, or export
    OBJ." A required extension that is not about the mesh (a texture format)
    is no reason to refuse.
  - A buffer with a `uri` that is a file name: "keeps its mesh in a separate
    file ('scene.bin') ... Export the scan as .glb, which is the whole scan in
    one file, or export OBJ."
  - Points stored as whole numbers (`KHR_mesh_quantization`), a sparse
    accessor, glTF 1.0: each named, with OBJ as the way out.
  - Cut short or damaged: a GLB shorter than its header says, a chunk or an
    accessor that runs past the end, JSON or base64 that cannot be read, an
    index that points at nothing, a size that is not a number. Whatever goes
    wrong inside the reader comes out as a `RoomScanError` and never as a 500.
  - No triangles and no points: "there is no room in it to read".
  - More than `MAX_VERTICES` (20 million) points or `MAX_FACES` (40 million)
    triangles, the limits `mesh.py` already had. They are counted as the scene
    is walked, before anything is copied, because a file of a few kilobytes
    can draw one mesh ten thousand times. The upload limit is the route's own
    200 MB.
- **Which reader** (`detect.py`): a file starting `glTF` is a GLB whatever its
  name. A file starting `{` is a `.gltf` when it is named `.gltf` (or `.glb`),
  or when it carries glTF's `asset` and one of `accessors`, `meshes`,
  `buffers`, `scenes`, `nodes`; otherwise it is RoomPlan JSON, as before.
- **The dialog** (`frontend/src/utils/roomScan.ts`, `RoomScanDialog.tsx`):
  `.glb` and `.gltf` are in the file picker's accept list
  (`ROOM_SCAN_ACCEPT`), and the help text names glTF.
- **Tests.** All files are written in the test with `struct` and `json`
  (`gltf_scene`, `write_glb` and `write_gltf` in
  `backend/tests/unit/room_scan_meshes.py`); none is on disk.
  - `backend/tests/unit/test_room_scan_gltf.py` (71): a `.glb` and a `.gltf`
    of one scene give the same points and triangles; which reader a file goes
    to, a `.gltf` named `.json`, a GLB whose buffer is a data URI; a node's
    translation, rotation and scale, a matrix, a node under a node (the
    expected points worked out from an axis and an angle, not from the
    reader's quaternion formula), a mesh drawn twice, the default scene only,
    no scene; each index width, no indices, an interleaved buffer with a
    stride and both offsets, a strip and a fan, points alone, lines beside a
    mesh left out and lines alone read as points, a point cloud of 60,000
    points read for its room, a bad index kept off the next part's points;
    the lopsided test room turned
    25 degrees coming back the right way round from both, a Z-up mesh stood
    up by its node, the same room as its OBJ gives, the operator's units over
    the file's; and the refusals: Draco and meshopt (both files), Draco not
    marked required, a required texture extension that is read anyway, a
    separate `.bin`, sparse, quantised, no mesh, glTF 1.0, a GLB cut at every
    length from one byte to one short of whole (and again with its header
    rewritten to agree), a `.gltf` cut short, base64 cut short, 24 ways a file
    can fail to hold together, the two limits, and one mesh drawn 5,000 times.
  - `backend/tests/integration/test_api_room_scan_gltf.py` (4), through the
    route: a box room 10 by 8 by 4 m with a stage block against the upstage
    wall, off to stage right, sent as OBJ, GLB and `.gltf`, each finding the
    room and the stage where they are and the three agreeing with each other,
    the GLB's units and up axis coming back as `m` and `y` from the file, and
    nothing written; the same room lying Z-up in two parts and placed by a
    parent and a child node; a non-indexed, interleaved GLB applied and read
    back off the rig; and Draco, meshopt, a separate `.bin`, a cut-short GLB
    and `.gltf` and an empty scene each a 400 with its words, with nothing
    stored.
  - `backend/tests/unit/test_room_scan.py`: the GLB row in "the message says
    what is wrong" now expects the refusal of a file that is four bytes of a
    GLB and nothing after (it names glTF 2.0), not "not read yet".
  - `frontend/src/__tests__/roomScan.test.ts`: one test that the accept list
    holds `.glb` and `.gltf` beside what it had. **Not run** (below).
- **What was run** (Nov 24), from `backend/` with the main checkout's venv:
  `pytest tests/unit/test_room_scan.py tests/unit/test_room_scan_gltf.py`
  133 passed; `pytest tests/integration/test_api_room_scan_gltf.py
  tests/integration/test_api_room_scan.py` 28 passed; the whole suite,
  `pytest tests/ -q -p no:cacheprovider`: 2105 passed, 10 skipped, 5 xfailed (2029 passed before this slice).
- **What was not run.** The frontend: this worktree has no
  `frontend/node_modules`, `npm ci` was refused, and `npx vitest run` and
  `npx tsc --noEmit` both stopped for want of the packages. The frontend
  change is one constant, one sentence of help text and one test, none of it
  executed. **No glTF from a real phone or app has been read**, and the
  dialog has not been opened in a browser with one.
- **Together with slice 24** (Nov 24). This slice was written beside binary
  USD and then put on top of it; the counts above are from before that. With
  both in: the accept list is `.obj,.ply,.glb,.gltf,.usdz,.usdc,.usda,.json`,
  the dialog and the server's "send one of these" name glTF and binary USD,
  and the test of the list's exact order in `roomScan.test.ts` holds all
  eight. Run from `backend/`: the five room-scan files (`test_room_scan.py`,
  `test_room_scan_gltf.py`, `test_room_scan_usdc.py`, `test_api_room_scan.py`,
  `test_api_room_scan_gltf.py`) 352 passed. `npx tsc --noEmit`: the 13 older
  errors, none in these files. **Not run:** `npx vitest run` was refused
  again, so `roomScan.test.ts` is still unexecuted with both slices in.
- **What is left**: Draco and meshopt unpacking, and a real export from each
  app. A `.gltf` with its `.bin` was left here too; slice 26 reads the two
  from a zip. See What is left.
- **Nothing here sends Art-Net or DMX**, opens a socket or calls an outside
  service. No new dependency and no migration.

## What slice 24 built

Binary USD read directly, so a USDZ can go from the phone to the room without
being exported again as OBJ. A USDZ is a ZIP, and the layer inside it is
nearly always binary USD (USDC, which USD calls the "crate" format): that is
what RoomPlan, Polycam and Scaniverse write. It was refused; only a text
layer was read.

- **The reader** (`backend/app/services/room_scan/usdc.py`, `parse_usdc`):
  numpy and the standard library. Pixar's USD library is not used and
  nothing was added to `requirements.txt`.
  - *The file.* The header (`PXR-USDC`, three version bytes, where the table
    of contents is), the table of contents, and the six tables it names:
    TOKENS (every name, once), STRINGS, FIELDS (a name and a value), FIELDSETS
    (which fields a prim or attribute has), PATHS (the tree of prims and
    their attributes) and SPECS (which path is a prim, which an attribute).
  - *Unpacking.* The tables are packed with LZ4 and it is undone here
    (`lz4_block`; `decompress` for USD's wrapping of it: a count of chunks,
    0 meaning one block). Tables of whole numbers are first written in USD's
    own coding, each number as its difference from the one before in as few
    bytes as it needs (`decode_integers`, 32-bit and 64-bit), done with numpy
    a million numbers at a time.
  - *The path tree* is walked with a list of what is still to visit, not by
    a function calling itself, so a deep or looping file cannot run it out
    of stack.
  - *Values.* A value is 64 bits: flags for array, held-in-place and packed,
    a type, and the value or where it is. Read: whole numbers, floats,
    doubles and halves; tokens and strings; vectors, quaternions and
    matrices; arrays of those, packed or not; lists of tokens; and of time
    samples the first. Only what a room needs is ever decoded. Everything
    else in the file (normals, texture coordinates, materials, custom data,
    dictionaries, list ops) is stepped over without being looked at.
  - *The stage.* `upAxis` and `metersPerUnit` from the layer. The prims in
    the order USD walks them (each prim's `primChildren`), leaving out a
    prim the file marks `over`, `class` or inactive. Each prim typed `Mesh`
    gives its `points`, `faceVertexCounts` and `faceVertexIndices`; faces
    of more than three sides are cut into triangles round their first
    corner. A layer with no `Mesh` that holds points anywhere (a point
    cloud) has those read.
  - *Placing.* By the transform ops of the prim and of every prim above it,
    in each one's `xformOpOrder`: translate, scale, orient, rotateX/Y/Z and
    the three-axis orders, and a 4x4 transform, with any `:suffix`.
- **A three-axis rotate was wrong, and is fixed** (found by the `variety`
  fixture below, which put half points 0.72 m from where Pixar's library
  puts them). The value of `rotateZYX` is the degrees about X, about Y and
  about Z, in that order, whatever the op is called; the name is the order
  they are turned in (Z first, then Y, then X; as row vectors, Rz Ry Rx).
  `_op_matrix_numbers` had paired the first letter of the name with the
  first number, which is only right for `rotateXYZ`, the one order a
  fixture had held. It now takes each axis's degrees by axis. The fix is
  in `usd.py`, so text and binary layers both have it. A rotate op whose
  name is not one axis or all three once each (`rotateXY`, `rotateXXY`) is
  not guessed at: it counts as an op that could not be read. Tests: each
  of the six orders in a text layer against the turns worked out in the
  test and against the same turns as three one-axis ops
  (`test_room_scan.py`); `rotateZYX` in binary against Pixar's numbers,
  and a text layer with the same op against them too.
- **The same code as a text layer.** `usd.py` now has the prims
  (`_Prim`), the op-to-matrix sums (`_op_matrix_numbers`) and the building
  of the mesh (`_mesh_from_prims`) in one place for both, so a text layer
  and a binary layer of one stage give the same mesh. Two things came with
  that for text layers too: an op named `!invert!...` in the order is that
  op undone (how USD writes a pivot), and `!resetXformStack!` stops the
  prims above from moving a prim. Faces are cut into triangles by numpy
  instead of a loop, in the same order.
- **Where it is used.** `parse_usdz` tries RoomPlan JSON first as before,
  then text layers, then binary ones, each in the archive's order, and the
  first that gives a mesh is the scan; when a USDZ held more than one USD
  layer the report says only one was read. `read_scan_file` reads a bare
  `.usdc` (or a binary layer under any name: it goes by the first bytes).
  The mesh's format is `usdc`. Nothing else changed: the API, the dialog
  and the rest of the pipeline take it as they take any mesh.
- **A file is not trusted.** Every count and offset is checked against the
  bytes that are there before anything is allocated: a block cannot claim
  to unpack to more than 255 times its size (LZ4's limit) or 400 MB, a table
  to more than 20 million entries, an array to more than 60 million, and
  all the arrays read out of one file to more than 180 million together
  (prims can share one packed array, and each would unpack it again). The
  path tree is built from the entries present, not the count given. Field
  sets cannot be made to overlap and be read over and over. Whatever goes
  wrong is a `RoomScanError`: "This binary USD (USDC) file cannot be read:"
  the reason, then what to export instead (`CONVERT_MESSAGE`, which is now
  only that advice). A layer that is nothing but the eight bytes `PXR-USDC`
  is still refused that way.
- **The fixtures** (`backend/tests/fixtures/usdc/`) were written by Pixar's
  USD library (`make_usdc_fixtures.py`, run by hand outside the venv; it is
  not a dependency), each with a JSON of the world-space points, triangles,
  up axis and units that Pixar's library computes from it: the test room in
  metres Y-up at crate 0.8.0, 0.7.0 and 0.10.0; in centimetres Z-up; a
  bigger room with a ring of truss (612 triangles); and `roomplan_like.usdz`, shaped like RoomPlan's export: a prim
  for each wall placed by a 4x4, a four-sided floor placed by translate and
  scale, a table by translate, orient, scale and rotateXYZ, in nested
  groups, with normals, a primvar and custom data to step over.
  A second one, `variety.usdc`, holds what a plain export does not: points
  as doubles (`point3d[]`) under a translate and a double orient; points as
  halves (`point3h[]`) under a translate and `rotateZYX = (10, 20, 0)`;
  points held only as time samples at 1 and 2 (the JSON has the sample at
  1); an identity 4x4 on `/Room`, which the file holds in place of an
  offset; and an `over`, a `class` and an inactive prim with points at 500
  and -500 that are not part of the room. The reader matches Pixar's
  numbers on all of it (doubles and samples to 1e-6, halves to 1e-3), and
  none of the three prims is read.
- **Tests** (`backend/tests/unit/test_room_scan_usdc.py`, 180): every
  fixture's points to 1e-4 and its triangles exactly, in Pixar's order, with
  its up axis and units; the room from `room_y_metres.usdc` and
  `room_z_cm.usdc` is the room from the text layer of the same stage, shell
  for shell; the RoomPlan-shaped USDZ gives a room 12 x 9 x 4 m with the
  table as its raised area; LZ4 (a match that overlaps its own output, long
  counts, chunks, broken blocks) and the integer coding (both widths,
  wrapping, more than one block of work) against bytes laid out by hand;
  values no fixture holds, laid out by hand (the array header of crate 0.4
  and 0.6, packed floats both ways, 64-bit packed arrays, halves and
  doubles, a quaternion's order, time samples); and damaged files: cut
  short at every fifth length, a table of contents pointed anywhere, a
  version not read, too many sections, a section outside the file, each
  table claiming more than it holds, arrays that together hold too much,
  and 400 copies of each of three
  fixtures with bytes changed at random, each one read or refused in plain
  words, within 2 seconds (in practice a few thousandths). In
  `test_room_scan.py` the refusal tests now refuse a layer that is only
  its first bytes, and two are new (text before binary; an inverted op).
  `tests/integration/test_api_room_scan.py` posts the RoomPlan-shaped USDZ
  and a bare `.usdc` and gets the room back.
- **What the hand-laid tests are worth.** They hold the reader to my
  reading of the format (USD's `crateFile.cpp`), not to Pixar's library:
  where no fixture reaches, a wrong reading would pass them. What the
  fixtures do reach is listed above; the rest is in What is left.
- **What was run** (Nov 24): in `backend/`, with the project's venv,
  `pytest tests/unit/test_room_scan_usdc.py tests/unit/test_room_scan.py
  tests/integration/test_api_room_scan.py` 265 passed, and the whole suite,
  `pytest tests/ -q`: 2209 passed, 10 skipped, 5 xfailed (2029 passed
  before; the 180 more are this slice's). Before the tests were written, every
  truncation of a fixture and 3000 random damages of it were run by hand:
  no exception other than the refusal, the slowest 0.002 s once the path
  tree stopped trusting the file's count (1.8 s before). After the variety
  fixture and the rotate fix, the same three files: 276 passed (3 more in
  `test_room_scan_usdc.py`, 8 in `test_room_scan.py`). The whole suite,
  run before the last two of those were written: 2218 passed, 10 skipped,
  5 xfailed.
- **The dialog.** `ROOM_SCAN_ACCEPT` in `frontend/src/utils/roomScan.ts`
  now has `.usdc`, so the file picker offers a bare binary layer, and
  `RoomScanDialog.tsx` says "as USDZ, USDC or USDA (binary USD is read as
  well as text)" where it said a USDZ needed a text layer. `roomScan.test.ts`
  holds the list of endings and uses the refusal the server gives now.
  Those frontend tests and the build were not run in the session that
  wrote them (`npx vitest run` and `npm run build` were refused there);
  `npx tsc --noEmit` gave the same 13 errors as before, none in these
  files.
- **Otherwise backend only.** No new field, no migration, no new
  dependency; nothing here sends Art-Net or DMX, and there is no network
  call.

## What slice 23 built

The booth and the crowd in a scanned room, so that the 3D view of a scanned
venue looks like a club with people in it. Until now a scanned room was drawn
empty: the booth and the crowd the view makes up were left out of it, because
they would have stood through the stage and risers the scan found.

- **The numbers** (`frontend/src/components/rig/previs/scanFloor.ts`, no
  React and nothing drawn): `placeScanBooth` (where the booth is and how it
  is drawn there), `facingOpenFloor` (which way it faces), `openFloorAt`
  (whether somebody can stand at a point), `openFloorCells` (the open floor on
  a 0.25 m grid), `scanCrowdCapacity` and `placeScanCrowd` (who stands where),
  with `boxFloor`, `footprint`, `rectDistance` and `areaDistance`.
- **The booth.** On the first raised area whose kind is `booth`, `source:
  'scan'`. A room with none gets no booth made up, unless it has a stage:
  then it goes at the middle of the front edge of the first one, `source:
  'guess'`. A room with neither has no booth.
  - *Facing.* A booth faces the way one of the four sides of its raised area
    does: the one that looks most nearly at the middle of the open floor,
    never one with a wall within 0.75 m in front of it while another has
    none. With no open floor at all, away from the nearest wall. Of two the
    same, downstage. A guessed booth on a stage faces downstage whichever
    way most of the floor is, and goes by this rule only when a wall is
    within 0.75 m of the stage's downstage edge.
  - *At a heading* (`heading_deg`, slice 21). A raised area that is turned is
    read as it stands: its width along its heading and its depth square to
    it, about its middle, from the same helpers the plan and the drag use
    (`boxAxes`, `boxCorners`, `boxHeading` and `sideFacing` in
    `raisedArea.ts`). Its four sides then face along its own width and
    depth, not along the room. A guessed booth goes on the side that is
    downstage as the stage stands turned (the side `sideFacing` calls
    downstage: an end of the width once it is turned past 45 degrees). A
    booth the room has is drawn at its own heading: `ScanBooth.heading` is
    the raised area's, and `yaw` is the turn `buildRisers` gives its box
    when it faces along its depth. The metre kept clear in front is a box
    at the same heading (`ScanBooth.strip`; `clear` is then only the box
    round it). The crowd keeps 0.5 m from every raised area's turned
    footprint (`areaDistance`: inside its turned corners is 0, otherwise the
    distance to the nearest of its sides, by `insideOutline` and
    `nearestOnOutline`), and where the DJ can stand is checked the same way.
    `scanFloorKey` carries a heading that is not 0, so turning a raised
    area places the booth and the crowd again.
  - *No heading, or 0, is exactly what it was.* Those raised areas go
    through the sums they always did (`footprint` and `rectDistance`), the
    booth's `clear` is the same rectangle with `strip` null, the view's key
    is the same text and the crowd's seed the same number, so the same room
    has the same booth and the same people as before headings were read.
  - *A counter or a platform.* A booth 0.6 m high or more is the counter
    itself: the decks and mixer go on its top, on the DJ's side, and the DJ
    stands on the floor 0.25 m behind it. That is the height from which a
    scan calls a small raised area "Booth or counter", so every booth a scan
    found is a counter. A lower one (made so by hand), and a stage, is a
    platform: the view's own desk stands at its front edge with the DJ
    behind the desk.
  - *The DJ is drawn only where there is somewhere to stand*: in the room,
    0.1 m from a wall, on a surface at the right height with nothing else
    standing there, and not behind a counter over 1.3 m. A counter right
    against a wall has its decks and no DJ.
  - *It is marked.* A guessed booth has an amber frame on the stage round it
    and an amber diamond over it, the colour of a guessed fixture position
    (`GUESS_COLOR`). One on the room's own booth has no mark.
- **The crowd.** On the floor inside the outline (a box room's four walls
  otherwise), `WALL_CLEAR` 0.5 m from every wall and `RAISED_CLEAR` 0.5 m
  from every raised area, out of the `BOOTH_FRONT_CLEAR` 1 m strip in front
  of the booth, 0.9 m from a DJ standing on the floor, and clear of where the
  Floor camera stands. The template crowd's figures, spacing and density: at
  most 4 a square metre of open floor, and never more than the quality mode
  asks for (80, 180 or 320). Tightest in front of the booth, thinning out
  away from it, everybody facing it; with no booth they are spread evenly and
  face every way. No floor left gives nobody.
- **Seeded from the room**, to the centimetre: the corners of the floor, the
  raised areas and the booth. The same room is the same crowd on every
  render; an edit to the walls or to a raised area (slices 14 to 20) places
  the booth and the crowd again. Moving a fixture does not: the view writes
  the floor and the raised areas out as text and places again only when that
  text changes (`scanFloorKey` in `RigVisualizer.tsx`).
- **Drawing** (`DJBooth.tsx`, `Crowd.tsx`, `ClubRoom.tsx`): `DJBooth` takes
  `placed` (a `ScanBooth`) and builds the same desk, decks and DJ about the
  middle of the booth's front face, turned and moved there, with no riser
  and no speaker stacks of its own; the raised area under it is still the
  box `RoomShellView` draws. `PlacedCrowd` draws people whose places are
  given. `ClubRoom` takes `boothLight`, so the work light that was over the
  made-up booth is over the real one; the light count is unchanged.
- **A room with no scan stored is drawn as it was.** The template booth is
  built through the same code from the same numbers, and the template
  crowd's people are made by `crowdPerson`, which draws the same random
  numbers in the same order.
- **Tests** (`frontend/src/__tests__/scanFloor.test.ts`): an L-shaped
  outline (nobody in the notch, both arms filled, capacity without the
  notch), a room with a stage and a riser (nobody on or within 0.5 m of
  either, the guessed booth and its DJ, a riser on the stage where the DJ
  would stand), no floor left, the booth's strip and the DJ's room, a booth
  on a side wall and in the arm of an L, a low platform, the floor camera,
  the same crowd twice and another after an edit. For a raised area at a
  heading (the last `describe`): `areaDistance` against a distance worked
  out in the test from the angle alone; a heading of 0 giving the same
  booth, the same cells and the same crowd as none; a guessed booth on a
  stage turned 30 degrees (where it is, its facing, yaw, DJ and strip), on
  one turned 90 (where the same stage standing square has it, with the same
  open floor) and on one turned -60 (an end of its width is downstage); a
  wall in front of a turned stage's downstage side; a booth the room has
  turned 30 and 90 degrees (its heading, yaw, DJ and strip); the open floor
  off a turned stage and on the floor it turned away from; a crowd in an
  L-shaped room round a turned stage, riser and booth, nobody within 0.5 m
  of any turned footprint, in the turned strip or outside the walls; and
  another crowd once a raised area is turned.
- **What was run** (Nov 24, with the heading support): in `frontend/`,
  `npx vitest run` 55 files, 1163 passed (35 of them in
  `scanFloor.test.ts`: the 24 written first, unchanged, and 11 for a
  heading); `npx tsc --noEmit` the 13 errors it had before, none new and
  none in a file this slice touches; `npm run build` OK. When the slice was
  first written vitest and the build were refused and its tests were only
  type-checked. **The view has still not been looked at in a browser.**
- **Frontend only.** No backend change, no new field, no migration; nothing
  here sends Art-Net or DMX, and there is no network call.

## What slice 22 built

Heights set by dragging. Until now every height and base height was typed
into a row of Edit Room: the plan is seen from above and has no height.
Frontend only: the server already took everything a drag sends.

- **The numbers** (`frontend/src/components/rig/roomItemHeight.ts`, new, no
  React): `heightGauge` (what the strip shows for one item: the ceiling,
  how many metres the strip covers, and each handle with where it stands
  and the least and most it may go, by the server's own limits),
  `dragHeight` (what a drag of one handle has the item at: the value, what
  to draw, what to send, the words), `heightGripHint`, `heightGripLabel`,
  `HEIGHT_SNAP_M` (0.05) and `HEIGHT_SHIFT_SNAP_M` (0.25). A value is
  snapped, then held to its limits, then rounded to the millimetre.
- **The strip** (`RoomItemHeightStrip.tsx`, new): an elevation of the
  selected item, 136 pixels wide beside the plan. `gauge` is what to show
  (null for nothing selected) and `onChange(kind, index, changes)` is
  called once when a handle is let go, and never for a press within 5
  pixels or a drag brought back. The handle is kept where it was dropped
  until what `onChange` returns has settled, then the room given is drawn:
  a refusal goes back. Pointer events, so a mouse, a finger and a pen are
  one path; the move and the release are listened for on the window,
  because a drag up a narrow strip leaves it sideways at once. The press
  is prevented, so the page does not pan and the plan keeps the arrow keys.
- **The editor** (`RigBuilder.tsx`): the plan and the strip are in one row
  while items mode is on. The strip is given `heightGauge(selectedItem,
  room)` and `handleItemChange`, the function the plan's handles already
  call. So a height goes through `changeRoomItem` and its queue: one
  `editShellItem`, `carry_fixtures` from the item's box (`withCarry` already
  adds it to a `height` or a `base_height`), the rig read again when
  fixtures moved, the notice from `editResultText`, a 422 or 409 shown in
  the strip over the plan, and the room's Undo. None of that was changed.
  The strip's default words gained a sentence about the height strip.
- **No backend change, no new route and no migration.** `PATCH
  .../room-shell/{kind}/{index}` with `height` or `base_height` is slice
  15's and slice 18's, and the carry, the 422 and the undo step are slices
  17, 18 and 20's.
- **`StageView2D.tsx` and `roomItemDrag2d.ts` were not changed**: no grip
  was added to the plan, so the handle lists their tests assert stand.
- **Judgment calls.**
  - *A strip beside the plan, not handles on it.* A height has no
    direction on a plan seen from above; a handle there would have to
    pretend one. The strip is a second, small view with a real up.
  - *The strip is there for the whole of the mode*, selected item or not,
    so the plan does not change size between a press and the first move.
  - *Every raised area has a Base handle*, not only one that already
    floats: dragging it up from the floor is how a platform is floated.
  - *Top and Base are side by side*, each 44 by 30 pixels, so the two of a
    0.05 m deck do not lie on each other and a finger can take either.
  - *Top sends the deck above the base* (`height`), because that is the
    field, and the handle shows the top above the floor, because that is
    what a person measures. Snapping is of the value shown.
  - *Base carries the whole area*, top included, since `base_height` alone
    does that on the server; its most is the ceiling less the deck.
  - *Always snapped*: 0.05 m, or 0.25 m. The plan's snap mode and Alt are
    not read: a height typed to the millimetre is still the row's.
  - *A Step button as well as Shift*, because a finger has no Shift.
  - *The scale is fixed when the press begins*, and a room with no ceiling
    stored is shown to a metre over the item and can be dragged past the
    top of the strip; the value goes on and the strip is redrawn after.
- **Nothing here sends Art-Net or DMX or touches a patch, a mode or a tag,**
  and there is no new network call beyond the app's own API.

## What slice 21 built

A raised area at any heading. Until now a stage, riser or booth stood
square to the room and had only its quarter turn: a stage set across a
corner, or a booth angled to face it, could not be put in as it stands.

- **The heading** (`backend/app/services/room_scan/edit.py`): `heading_deg`
  is one of a raised area's size fields. `area_heading` reads it (0, square
  to the room, for one that stores none; folded over -90 and up to 90, to a
  tenth, by `clean_heading` as a line's is), `area_reach` says how far the
  area reaches either side of its middle as it stands, and `area_corners`
  gives its four corners turned. `edit_item` stores a turn of a tenth of a
  degree or more, marks it resized, and holds the whole of the area to the
  room by its reach at that heading, for the turn and for any later resize.
  `add_item` takes a heading and stores it only when it is not 0.
  `edit_words` says "turned".
- **What stands on it** (`carry.py`): `_across_and_back` measures a place
  along the area's own width and depth, so "over its footprint" is over it
  as it stands, for a fixture (`_stand_gap`) and for a raised area
  (`_stands_on_area`). `area_turn` is how far an edit turned it: 90 for
  sides that changed places, and the change of heading, taken as the
  smaller of the two turns that give it, added. `_swung` turns an offset.
  `_stood_moves` takes that turn in degrees (it took a yes or no): each
  fixture keeps its share along the area's own sides and is swung about the
  middle, its heading turned with it. `carried_areas` swings each raised
  area standing on it the same way, turns its own `heading_deg` by as much,
  and answers `turn`; `_footprint` adds `heading_deg` for one that has a
  heading before or after.
- **What is outside the walls** (`outline_edit.py`): `_item_points` goes by
  the corners where they stand.
- **The route** (`room_scan.py`): no new one and no new field. `PATCH` and
  `POST` already had `heading_deg`, for a line; only the words changed. No
  migration: a raised area stored before this slice has no heading and
  reads as 0.
- **The footprint** (`frontend/src/components/rig/previs/raisedArea.ts`,
  new, numbers only): `foldHeading`, `boxHeading`, `boxPoint`, `boxCorners`,
  `headingText` (", turned 30 degrees") and `sideFacing` (which way a side
  faces, in the room's words). `RoomShellBox` has `heading_deg`.
- **The 2D plan** (`roomPlan2d.ts`, `StageView2D.tsx`): `PlanRaised` has
  `heading` and `corners` for one that is turned, the plan is made as big
  as its corners reach, its tooltip says how far it is turned, and its
  rectangle is drawn turned about its middle.
- **The 3D view and the snap lines** (`previs/roomShell.ts`,
  `previs/fixtureDrag.ts`): `buildRisers` turns the box and its top, the
  same way round as the plan, and `snapLines` gives the four edges where
  they stand, each called by the way it faces ("Stage, upstage edge").
- **Edit Room** (`RoomShellEditDialog.tsx`, `utils/roomShellEdit.ts`): a
  **Heading** field on a raised area's row and on the Add form
  (`AREA_HEADING_LABEL`, `ShellItem.heading`, `headingShown`). `readDraft`
  sends a typed heading only when it differs, folded, from what is stored;
  `readNewItem` sends one only when it is not 0; `editResultText` tells a
  turn as it tells a resize, and a row's detail says ", turned 30 degrees".
- **The rotate handle** (`roomItemDrag2d.ts`): a box shape has `heading`;
  `itemHandles` stands the eight resize handles on the area as it is turned
  and adds `rotate`, on a stalk past the edge that is upstage when it
  stands square; `dragItem` turns it so that the handle points at the
  pointer, to 5 degrees with the snap on and a tenth without, and to 15
  with Shift (`ItemSnap.coarse`, `HEADING_SHIFT_SNAP_DEG`), which a truss
  line's rotate handle takes too; a resize handle pulls along the area's
  own sides; `gripCursor` (moved here from the plan) turns the arrow with
  the area. One `heading_deg` is sent when the handle is let go, through
  the code every other handle goes through, so a refusal puts it back.
- **Judgment calls.**
  - *Folded, like a line's.* A rectangle has no front, so a heading is
    kept over -90 and up to 90 and half a turn is no turn. What stands on
    it does have a front, and is swung by the smaller of the two turns.
  - *One square to the room stores nothing*, so every room stored before
    this slice, and every answer about one, reads exactly as it did.
  - *The quarter turn stays.* Sides swapped are still a quarter turn
    clockwise, and Turn still does that; a heading of 90 swings what stands
    on it the same way. Both in one request are added.
  - *A carried raised area turns its own heading by as much*, so a riser
    square to a stage stays square to the stage.
  - *The drag draws the turn unfolded* while the handle is held, so the
    handle stays under the pointer past 90 degrees; what is sent is folded.
- **Older tests changed on purpose.** `test_room_scan_adjust.py` and
  `test_api_room_shell_adjust.py` each had an expectation changed for a
  raised area that now takes a heading (over HTTP, one past a whole turn is
  refused as a line's is), and `roomItemDrag2d.test.ts` looks at the first
  eight of a raised area's handles: the ninth turns it.
- **Nothing here sends Art-Net or DMX or touches a patch, a mode or a tag,**
  and there is no new network call beyond the app's own API.

## What slice 20 built

Raised areas finished, so that a scanned room can be corrected fully: a
riser on a stage follows the stage, a platform can be added floating, and a
raised area is sized on the plan. Until now a stage that was moved left the
drum riser on it behind with its lights, a balcony had to be added on the
floor and then raised, and a raised area's sides were typed.

- **The stack** (`backend/app/services/room_scan/carry.py`): `stood_areas`
  (which other raised areas stand on one: the middle of the footprint
  inside its footprint, the base within 0.1 m of its top, and what stands
  on those), `carried_areas` (where each goes, and the item as it is to be
  stored), `carried_area_moves` (the fixtures standing on each),
  `refuse_areas_outside` (the 422), `apply_areas` (the room with them
  moved; the one given is not changed) and `areas_report` (the answer's
  list). `_stood_moves` takes the turn from its caller where the caller
  knows it. `carried_words` takes how many areas went.
- **The route** (`room_scan.py`): `PATCH .../room-shell/risers/{index}`
  with `carry_fixtures` true carries the stack and answers `items_moved`.
  Everything is worked out from the room as it was and checked before
  anything is written; the step of the room's undo holds the whole room
  and every carried fixture, so one undo puts it all back. Still 409
  during a locate walkthrough. No new route and no migration.
- **Adding on a base** (`edit.py`): `add_item` holds a new raised area's
  deck to what a deck can be and its top to the ceiling, in the words an
  edited base is refused in. Before, a base too high was refused as a
  height that was too great.
- **The Add form** (`RoomShellEditDialog.tsx`, `utils/roomShellEdit.ts`):
  a **Base height** field for a stage, a riser and a booth, starting at 0.
  `NewItemDraft` has `base_height`; `readNewItem` checks it with
  `baseHeightProblem` and sends it only when it is over 0, so what is sent
  for a platform on the floor is what it always was. The field is not shown,
  read or sent for a truss or a ring, and is kept from one raised kind to
  another.
- **The notice** (`carriedText`, `stackedText`, `Carried`): the dialog and
  the strip over the plan say how many raised areas went too. The answer's
  `items_moved` is typed (`CarriedArea`).
- **The handles** (`components/rig/roomItemDrag2d.ts`): `BoxGrip` (`nw`,
  `n`, `ne`, `e`, `se`, `s`, `sw`, `w`, by the compass of the plan as it is
  drawn), `isBoxGrip`, eight handles from `itemHandles`, and `dragItem`
  for each: twice how far the pointer is from the middle along each axis
  the grip pulls, to the grid's step, never under 0.3 m, and only what
  changed in what is sent. `gripHint` words each.
- **The plan** (`StageView2D.tsx`): the eight handles drawn on a selected
  raised area, smaller than a truss's, with a resize cursor for each. The
  press, the 5 pixel threshold, the one call on release, the drop kept
  until the answer and the item put back when it is refused are the code
  the other handles already went through.
- **The editor needed no change for the handles.** `changeRoomItem` already
  sends whatever a drag reports through `withCarry`, which adds
  `carry_fixtures` to a `width` or a `depth`; a refusal already goes to the
  strip and lets the plan go back.
- **Judgment calls.**
  - *A resize is about the middle*, because that is what the server does
    with `width` and `depth` and what the length handle does. The edge
    opposite the one dragged moves as far the other way.
  - *A resize alone carries no raised area.* The fixtures standing on the
    resized area still keep their share of it (slice 18); a riser on it
    keeps its place and its size, since a riser spread with the stage would
    have to be stretched too. Only a middle that the resize brought in is
    followed.
  - *The whole stack, not one level.* A box on a riser on a stage goes with
    the stage. Two thin areas that each stand on the other are each
    carried once.
  - *A carried area is held to its own row's limits*: the ceiling and a
    10 m base, as well as the box and 2 m. See the `PATCH` section.
  - *A base never goes under the floor.* A riser stored up to 0.1 m under
    the top it stands on comes down to the floor, not through it, when the
    stage is lowered that far.
  - *A carried area is marked as moved or resized by hand*, like one moved
    from its own row: it is no longer where the scan found it.
  - *The Add form sends no base of 0*, so the body of an ordinary add is
    unchanged and the older tests of it stand.
- **Older tests changed on purpose.** `roomItemDrag2d.test.ts` and
  `StageView2DItems.test.tsx` asserted that a raised area has no handle;
  they now expect the eight. No backend test changed.
- **Nothing here sends Art-Net or DMX or touches a patch, a mode or a tag,**
  and there is no new network call beyond the app's own API.

## What slice 19 built

The room's items, arranged on the 2D plan: until now a raised area, a truss
line or a ring was put somewhere by typing two numbers into its row. Frontend
only: the server already took everything a drag sends.

- **The helpers** (`components/rig/roomItemDrag2d.ts`, new, no React):
  `planItems` (what can be picked up, each with the list and the place the
  server knows it by, read from `shellItems` and not from the plan's own
  shapes, which leave out what cannot be drawn), `itemHandles` (where a
  line's length and rotate handles and a ring's radius handle stand),
  `dragItem` (what a drag of one grip has the item at: the shape to draw,
  what to send, the words over it), `nudgeItem` (an arrow key's change) and
  `gripHint`.
- **The plan** (`StageView2D.tsx`): with the new `itemsEdit` prop on, each
  item's footprint is drawn again **over the fixtures**, to be pressed, with
  the selected one's handles. A drag past the 5 pixel threshold is drawn as
  it goes and reported once, when it ends, through `onItemChange(kind,
  index, changes)`; a drag that ends where it began reports nothing. The
  arrow keys call `onItemNudge(kind, index, dx, dz)` once for each press,
  from a listener of the mode's own. `selectedItemKey` and `onItemSelect`
  hold which item is selected. Fixtures take no press, as in walls mode.
  With the prop off the plan is as it was.
- **The editor** (`RigBuilder.tsx`): items mode and its strip over the plan
  (what the last change did or why it was refused, the selected item's box,
  Undo, Back to Edit Room, Done arranging). Every change goes through one
  queue (`queueRoomChange`): one `editShellItem` each, sent only once the
  one before it was answered and, where that one moved fixtures, the rig was
  read again. A nudge is worked out when its turn comes, from the room as
  the change before it left it.
- **The dialog** (`RoomShellEditDialog.tsx`): the button **Arrange room
  items on the plan**, which hands over its unticked boxes
  (`onArrangeItems(leftAlone)`).
- **No backend change, no new route and no migration.** A move is `PATCH
  .../room-shell/{kind}/{index}` with `center_x` and `center_z`, a handle is
  the same route with `length`, `heading_deg` or `radius`, and each carries
  `carry_fixtures`. The carry, the 422 and the undo step are slices 15, 17
  and 18's, unchanged.
- **The 3D view needed no change.** It draws the room and the fixtures from
  the rig, which is given the answered room after each change and read
  again when fixtures were carried.
- **Judgment calls.**
  - *One request for each key press*, not one for a burst: a press is then
    one undo step, as it is for a nudged fixture, and what Undo takes back
    is never a guess. The cost is a request a press.
  - *Requests are queued, not dropped.* Walls mode ignores a drag made while
    one is out; here a second arrow key pressed before the first is answered
    would then be lost, so it waits its turn instead.
  - *A length changes about the middle*, because that is what the server
    does with `length`: the end that is dragged goes half as far as the
    line grows, and the other end moves as far the other way.
  - *The rotate handle stands past the end*, 0.6 m out, so it is not under
    the length handle of a short line or under a fixture hung at the end.
  - *The item being dragged is drawn twice*: its outline where the drag has
    it, and the item itself where it still is until the server answers.
    That keeps the plan's frame still under the pointer.
  - *An undo lets go of the selection and of the unticked boxes*, as the
    dialog does: it may bring back a deleted item, and the ones after it
    then change places.
- **Nothing here sends Art-Net or DMX or touches a patch, a mode or a tag,**
  and there is no new network call beyond the app's own API.

## What slice 18 built

Raised areas in Edit Room: the fixtures standing on one follow it, it can
be made another kind, and it can float on a base height. Until now a stage
that was moved or raised left its floor lights behind, a riser could not be
made a stage short of deleting it, and nothing could be drawn above the
floor but truss.

- **What stands on it** (`backend/app/services/room_scan/carry.py`):
  `stands_on` and `standing_fixtures` (over the footprint and 0.15 m round
  it, 0.05 m under the top to 0.6 m above it, never a fixture that hangs on
  a line or ring, the nearer top of two), `quarter_turned`, and
  `carried_moves` now answering for `risers` too: a move, a height or base
  height, a resize by share of the footprint, a quarter turn.
  `refuse_outside`, `apply_moves` and `put_back` are slice 17's, unchanged
  but for their words ("standing on", "stood").
- **The edit** (`edit.py`): `edit_item` takes `riser_kind` and
  `base_height`; `add_item` takes `base_height`; `base_of`, `deck_top` and
  `first_stage` are new, and `height_limits` goes by the base. A kind
  change renames an item still carrying its old kind's name, marks it
  "Kind set by hand." and is worded "made a stage" in the undo label; a
  base change is worded "raised" or "lowered".
- **The route** (`room_scan.py`): `PATCH .../room-shell/risers/{index}`
  takes `carry_fixtures` (default true), `riser_kind` and `base_height`,
  and every `PATCH` answers `riser_kind` and `first_stage`. `POST
  .../room-shell/risers` takes `base_height`. Still 409 during a locate
  walkthrough. No new route and no migration.
- **One undo step** (`edit_undo.py`): `push_step` keeps the edited item's
  list (`kind`) beside the carried fixtures, so the undo's message can say
  whether they hung or stood.
- **The suggestion** (`suggest.py`): floor lights put on a stage are lifted
  to its top, base included, and the reason says that height.
- **The helpers** (`utils/roomShellEdit.ts`): `carriesFixtures` is now true
  for a raised area; `stoodOn`, `carryLabel`, `carryBoxName`,
  `CARRY_STANDING_LABEL`; `RISER_KIND_CHOICES`, `riserKindShown`;
  `BASE_HEIGHT_LABEL`, `baseHeightShown`, `baseHeightProblem`,
  `floatingText`; a `ShellItem` carries `baseHeight` and `riserKind`;
  `readDraft` reads the two new fields only once they are touched;
  `withCarry` sends the flag with a raised area's change of place, size,
  height or base, and not with its name or kind.
- **The dialog** (`RoomShellEditDialog.tsx`): on each raised area's row the
  box, a **Kind** selector and a **Base height** field; the help text says
  what a base height is.
- **The plan** (`roomPlan2d.ts`): a floating raised area's tooltip says how
  far it floats. The 3D view already drew a raised area from its
  `base_height` up, and a test now holds it to that.
- **Judgment calls.**
  - *Standing is by distance, like hanging.* Nothing links a fixture to a
    platform. The window is 0.6 m above the top so a light on a low stand
    or a moving head on its base goes along, 0.05 m under it for one drawn
    a little into the deck, and 0.15 m round the edge for a base that
    overhangs the lip.
  - *A truss wins over a stage.* A fixture within reach of any line or ring
    is hung, not standing, so a truss low over a stage keeps its lights
    when the stage moves.
  - *A resize keeps shares, not metres.* A row spread across a stage made
    wider is spread across the wider stage, as a row along a truss made
    longer is.
  - *A quarter turn is clockwise seen from above*, and is read from the
    sizes alone: a raised area has no heading to store.
  - *A kind change keeps the item's place in its list*, so making an
    earlier raised area a stage makes it the first stage. `first_stage` is
    answered so a client can tell.
  - *A base change is a resize*, not a new mark, and the refusal for a top
    above the ceiling asks for a lower base or a lower height.
  - *The default is to carry*, as for truss: a request that says nothing
    takes the fixtures along.
- **Older tests changed on purpose.** The backend ones that asserted that a
  raised area carries nothing now send `carry_fixtures: false` or expect
  the carry and its words. The frontend ones now expect `carry_fixtures:
  true` in a raised area's save, and the helpers' tests expect a raised
  area to carry.
- **Nothing here sends Art-Net or DMX or touches a patch, a mode or a tag,**
  and there is no new network call beyond the app's own API.

## What slice 17 built

Fixtures follow their truss in Edit Room: until now a truss that was moved,
raised or turned left its lights hanging in the air where it had been.

- **The carry** (`backend/app/services/room_scan/carry.py`, new):
  `hangs_on` and `hung_fixtures` (which fixtures hang on a line or ring:
  0.3 m on the plan, 0.6 m in height, the nearer of two trusses),
  `carried_moves` (where each goes, from the item before and after the
  edit), `line_turn` (the smaller turn, read from the ends), `refuse_outside`
  (the 422), `apply_moves`, `put_back` (the undo) and the sentences. Pure
  apart from the two that set a fixture's position.
- **The route** (`room_scan.py`): `PATCH .../room-shell/{kind}/{index}`
  takes `carry_fixtures` (default true) and answers `carry_fixtures`,
  `fixtures_moved` and a `message`. Every position is worked out and checked
  before anything is written. Still 409 during a locate walkthrough.
- **One undo step** (`edit_undo.py`): `push_step` takes the moves and keeps
  them in the step beside the room (`fixtures`); `POST .../room-shell/undo`
  puts the room and those fixtures back and answers `fixtures_restored` and
  `fixtures_skipped`. No migration: the record is the same JSON column.
- **The heading.** The rig model has `rotation_y`, a yaw about the vertical
  that turns +Z towards +X; a line's heading turns +X towards +Z. So a line
  turned by `d` degrees takes `d` off each carried fixture's `rotation_y`
  (kept over -180 and up to 180). `rotation_x` and `rotation_z` are left.
- **The helpers** (`utils/roomShellEdit.ts`): `carriesFixtures`,
  `withCarry` (the flag goes only with a line's or ring's change of place,
  size, height or heading), `carriedCount`, `carriedText` and `CARRY_LABEL`;
  `editResultText` takes what became of the fixtures; the answers' new
  fields are typed (`CarriedFixture`).
- **The dialog** (`RoomShellEditDialog.tsx`): the box on each line's and
  ring's row, the count in the notice, and `onFixturesMoved`, called after
  `onChanged` when a save or an undo moved fixtures.
- **The editor** (`RigBuilder.tsx`): `handleRoomFixturesMoved` drops the
  editor's own undo steps and reads the rig again, as it does after a scan
  is applied; the walls-mode strip's Undo does the same. The 2D plan and the
  3D view draw from the rig, so neither needed a change.
- **Three older backend tests changed on purpose**: they asserted that a
  truss edit moves no fixture. Two now send `carry_fixtures: false`; the
  undo chain expects the carry and still ends with every fixture exactly
  where it began.
- **Nothing here sends Art-Net or DMX or touches a patch, a mode or a tag,**
  and there is no new network call beyond the app's own API.

## What slice 16 built

The room's walls, corrected by hand: the one part of a scanned room slices
14 and 15 left alone.

- **The edit** (`backend/app/services/room_scan/outline_edit.py`, new):
  `set_outline` (every corner, the height, or both), `move_corner`,
  `insert_corner`, `delete_corner`, and `room_corners`, which reads the
  walls of any scanned room, a box's four included. `check_walls` is what a
  room has to be; `crossing_walls` finds walls that cross, touch or double
  back. Pure, like `edit.py`: a shell in, a new shell out.
- **What is outside** (`outside_report`, `outside_words`): the raised areas,
  lines, rings and fixtures beyond a wall or above the ceiling. Nothing is
  moved; this is what a change to the walls answers with instead.
- **The routes** (`room_scan.py`): `GET` and `PATCH .../room-shell/outline`,
  and `PATCH`, `POST` and `DELETE` under `.../room-shell/outline/corners`.
  Each change is one step of the existing `room_shell_undo` record and is
  refused during a locate walkthrough, by the helpers the other edit routes
  use. `POST .../room-shell/undo` now answers `outside` too. No migration.
- **The helpers** (`utils/roomWallsEdit.ts`, new, no React): `wallCorners`
  (the corners as the server numbers them), `readCorner`, `readRoomHeight`,
  `wallsSizeText`, and the warning list's words (`outsideLines`,
  `outsideHeading`, `outsideOf`). `roomOutlinePath`,
  `roomOutlineCornersPath` and `roomOutlineCornerPath` in
  `utils/roomScan.ts`; `getOutline`, `setOutline`, `moveOutlineCorner`,
  `addOutlineCorner` and `deleteOutlineCorner` on `roomScanApi`.
- **The Walls section** (`RoomShellEditDialog.tsx`): the table of corners,
  Add after and Delete, the room height, the warning list, and the button
  that hands the corners to the plan (`onDragWalls`).
- **The plan** (`StageView2D.tsx`): with the new `wallsEdit` prop on, a
  numbered handle on each corner, a drag past the 5 pixel threshold drawn
  as it goes and reported once, when it ends, through `onWallCornerMove`;
  fixtures take no press meanwhile. With the prop off the plan is as it was.
- **The editor** (`RigBuilder.tsx`): walls mode, its strip over the plan
  (what the last drag did, what is outside, Undo, Back to Edit Room, Done
  with walls), one `moveOutlineCorner` for each drag, and the answered room
  put on the rig with no fixture, save or editor undo step touched.
- **The 3D view needed no change.** It reads `room.outline` and the room's
  box through `roomOutline` and `buildVenue`, as does the 2D plan through
  `roomPlan`, so both draw new walls as soon as the rig carries them.
- **Nothing here sends Art-Net or DMX, moves a fixture or touches a patch,**
  and there is no new network call beyond the app's own API.

## What slice 15 built

Edit Room, taken from rename, move and delete to correcting anything a scan
suggested without scanning again.

- **Size, height and heading** (`backend/app/services/room_scan/edit.py`):
  `edit_item` takes `width` and `depth` for a raised area, `length` and
  `heading_deg` for a line, `radius` for a ring and `height` for any of
  them, each with a least and a most, refused when not a finite number or
  out of range. `_fit` keeps the whole of a resized, turned or added item
  inside the room's box and the existing 2 m margin, and refuses one too big
  to be. `clean_heading`, `line_heading` and `height_limits` are there for
  callers and tests.
- **Hanging bands kept true** (`_uncount`, `_count`): a truss or ring that is
  raised, lowered or added leaves the band it was in and is counted in the
  one its new height is in, or starts one. Bands never hold an empty band
  or a count that is not the room's.
- **Add** (`add_item`): a stage, riser, booth, truss line or ring by hand,
  at the end of its list, marked `added_by_hand`.
- **Undo** (`backend/app/services/room_scan/edit_undo.py`, new;
  `rigs.room_shell_undo`, migration `008_rig_room_shell_undo`): the whole
  room as it stood before each edit, the last 20, one step taken back for
  each call. The rig carries the count and the latest step's words as
  read-only `room_shell_edits` (`models/rig.py`, `schemas/rig.py`). Emptied
  when a scan is applied and when the room is taken off.
- **The routes** (`room_scan.py`): the wider `PATCH`, `POST
  .../room-shell/{kind}`, `GET` and `POST .../room-shell/undo` (declared
  before the route that takes a list's name, or "undo" would be read as
  one). All of them and the existing `PATCH` and `DELETE` answer 409 while a
  locate walkthrough is running on the rig. See The API.
- **A 500 closed on the way.** A raw `Infinity` in the body of the existing
  `PATCH` made FastAPI's own refusal fail to answer. The numbers are now
  refused by `edit.py`, in a sentence.
- **The helpers** (`utils/roomShellEdit.ts`): each listed item's `sizes` and
  `marks`; `lineHeading`; the wider `draftOf` and `readDraft`, with
  `sizeProblem` and the least sizes (`SHELL_LIMITS`); `quarterTurned`; the
  Add form (`newItemDraft`, `readNewItem`, `NEW_ITEM_CHOICES`); the Undo
  button's words (`undoButtonText`, `shellUndoCount`). `roomShellListPath`
  and `roomShellUndoPath` in `utils/roomScan.ts`; `addShellItem` and
  `undoShellEdit` on `roomScanApi`.
- **The dialog and its wiring** (`RoomShellEditDialog.tsx`,
  `RigBuilder.tsx`): the size, height and heading fields, Turn, the Add
  form, the chips for who set what, and Undo. The editor hands the dialog
  the rig's `room_shell_edits` and puts each answered room and count back on
  the rig, with no fixture, save or editor undo step touched.
- **Nothing here sends Art-Net or DMX, moves a fixture or touches a patch,**
  and there is no new network call beyond the app's own API.

## What Edit Room built

- **The edit** (`backend/app/services/room_scan/edit.py`, new): `edit_item`,
  `delete_item`, `clean_name`, `item_centre` and `item_name`. Pure: a shell
  goes in and a new one comes out, which matters because the column is plain
  JSON and a change made in place is never written.
- **The routes** (`room_scan.py`): `PATCH` and `DELETE` on
  `/api/rigs/{rig_id}/room-shell/{kind}/{index}` (see The API).
- **The helpers** (`utils/roomShellEdit.ts`, new, no React): `shellItems`,
  `readDraft`, `draftOf`, and the dialog's wording (`editResultText`,
  `deleteQuestionText`, `shellEditErrorText`). `roomShellItemPath` in
  `utils/roomScan.ts`; `editShellItem` and `deleteShellItem` on `roomScanApi`.
- **The dialog and its wiring** (`RoomShellEditDialog.tsx`, new;
  `RigEditorToolbar.tsx`, `RigBuilder.tsx`): the Edit Room button, and the
  answered room put on the rig in the editor with no fixture, save or undo
  step touched.
- **No migration**, and nothing here sends Art-Net or DMX.

## What slice 11 built

- **The helpers** (`components/rig/planSelect2d.ts`, new, no React):
  `pastDragThreshold`, `boxBetween`, `fixturesInBox`, `boxSelection`,
  `nudgeShift`, `nudgeMoves` and `keysBelongElsewhere`.
- **The plan** (`StageView2D.tsx`): the 5 pixel threshold on a press; a
  selection box over empty floor, reported through the new
  `onSelectFixtures`; and, with the new `keyboard` prop on, Escape, R and
  the arrow keys. A nudge is sent through the drag's own three calls, so
  there is no second way of saving a move.
- **The editor** (`RigBuilder.tsx`, `RigEditorToolbar.tsx`): hands the plan
  the store's `selectFixtures`, turns the keyboard on while the 2D view is
  shown and no dialog is open, and says what the keys do in the Select row
  tooltip and the line under the plan. `rigEditorStore.ts` is unchanged.
- **One existing test changed**: `StageView2D.test.tsx` dragged a fixture
  3 pixels and expected it to move; it now drags it 7.
- **No backend change**, and nothing here sends Art-Net or DMX.

## What slice 10 built

- **Lay on truss** (`rowMove2d.ts`): `nearestTruss`, `spotsOn`,
  `addressOrder`, `spacingOn`, `layRowOnTruss` and `layNoticeText`, with no
  React in them. `spotsOn` is a port of `suggest.py`'s `_spots_on`.
- **The button and its save** (`RigEditorToolbar.tsx`, `RigBuilder.tsx`):
  `handleLayRow` uses the row move's own pieces (`withMoves`,
  `snapshotPositions`, `heightsBefore`, `noteUndoHeights`) and writes at
  once. `StageView2D.tsx` is unchanged.
- **No backend change.**

## What slice 9 built

- **Truss height and readout** (`StageView2D.tsx`, `rowMove2d.ts`): a 2D drag
  or palette drop that lands on scanned truss takes its hang height and says
  what it is on. `RigBuilder.tsx` saves the height with the position and
  hangs a dropped fixture at it.
- **Multi-selection and rows** (`StageView2D.tsx`, `rigEditorStore.ts`,
  `RigEditorToolbar.tsx`): Shift, Ctrl and Cmd build a selection; Select row
  and a double-click select a row (`rowOf`); a drag carries the selection by
  one shift held to the room (`holdRowShift`).
- **Save and undo** (`RigBuilder.tsx`): a row move is one batch-update and
  one undo step. An undo step now keeps a height, but only for a fixture
  whose height that drag changed by snapping onto truss (`heightsBefore`,
  `noteUndoHeights`, `snapshotPositions`). Every other height is left out,
  so undoing a move never takes back a height set in the properties panel,
  and a drag that met no truss is undone exactly as before.
- **No backend change.** `PUT .../fixtures/batch-update` already took
  `position_y` and already left tags alone.

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

All scans are built in code (`backend/tests/unit/room_scan_meshes.py`), but
for binary USD: those files are in `backend/tests/fixtures/usdc/`, written by
Pixar's USD library from the same rooms (slice 24).

- `backend/tests/unit/test_room_scan_keep_named.py` and
  `backend/tests/integration/test_api_room_scan_keep_named.py`: the list of
  what a scan applied again did, one thing at a time and by name; the
  warning for a truss read more than 1.0 m higher or lower, for one read
  to one side, and for a record of a deleted item that is dropped; and
  what says nothing (slice 35). Run. The frontend's
  `RoomScanDialogHandEditItems.test.tsx` has **not** been run (see "What
  slice 35 built" and "What is left").
- `backend/tests/unit/test_room_scan_keep_lost.py`,
  `backend/tests/unit/test_room_scan_carry_over.py` and
  `backend/tests/integration/test_api_room_scan_carry_over.py`: the three
  losses slice 36 says, `carry_over` for each with a new item behind it,
  each kind's entry put back and kept by the next scan, and the route over
  HTTP (success, Undo, stale 409, 422s). Run. The frontend's
  `RoomScanDialogCarryOver.test.tsx` has **not** been run (see "What slice
  36 built").
- `backend/tests/unit/test_room_scan_keep_overhead.py` and
  `backend/tests/integration/test_api_room_scan_keep_overhead.py`: a name
  and a hanging height set by hand kept on an overhead line and a ring, one
  added by hand kept or replaced, a deleted raised area left out and
  forgotten by the room's Undo, and what is flagged against the new ceiling
  and walls (slice 33). Run. The frontend's
  `RoomScanDialogHandEditsOverhead.test.tsx` has **not** been run (see
  "What slice 33 built" and "What is left").
- `backend/tests/unit/test_room_scan_keep_edits.py` and
  `backend/tests/integration/test_api_room_scan_keep_edits.py`: a name, a
  height and a base height set by hand kept when a scan is applied again,
  a raised area added by hand kept or replaced, and what the preview and
  the apply say of it (slice 32). Run. The frontend's
  `RoomScanDialogHandEdits.test.tsx` has **not** been run (see "What slice
  32 built" and "What is left").
- `backend/tests/unit/test_room_scan_keep_mark.py` and
  `backend/tests/integration/test_api_room_scan_keep_mark.py`: the DJ booth
  mark kept or dropped when a scan is applied again (slice 30), what a
  preview says of it beforehand, and a kind set by hand kept with it (slice
  31). Run. The frontend's `RoomScanDialogDjBoothDropped.test.tsx` (slice
  30) and `RoomScanDialogDjBoothPreview.test.tsx` (slice 31) have **not**
  been run (see "What slice 31 built" and "What is left").
- `backend/tests/unit/test_room_scan_dj_booth.py` and
  `backend/tests/integration/test_api_room_shell_dj_booth.py`: the DJ booth
  mark (slice 28). Run. The frontend's `boothPick.test.ts`,
  `boothCamera.test.ts`, `RoomShellDjBoothDialog.test.tsx` and
  `StageView2DDjBooth.test.tsx` were run afterwards and pass (vitest 59
  files, 1222 passed, Nov 24; see "What slice 28 built").
- `frontend/src/__tests__/RoomScanDialogTurn.test.tsx` and "the turn of a
  move" in `roomScan.test.ts`: the Turn column of the Room Scan dialog and
  its words (slice 29). Type-checked; **written and not run** (see "What
  slice 29 built").
- `backend/tests/unit/test_room_scan.py`: the parsers (OBJ, PLY in three
  encodings, USDA, USDZ, RoomPlan JSON), the same room recovered whatever the
  units, axes and heading, a point cloud with no normals, a scan leaking through
  a doorway, refusals and their wording, and which rows move where.
- `backend/tests/unit/test_room_scan_usdc.py`: binary USD against what Pixar's
  library computes, the same room as from the text layer, the two unpackers,
  hand-laid values, and damaged files (see "What slice 24 built").
- `backend/tests/unit/test_room_scan_gltf.py` and
  `backend/tests/integration/test_api_room_scan_gltf.py`: glTF (slice 25). A
  `.glb` and a `.gltf` of one scene are the same mesh; node transforms
  (translation, rotation and scale; a matrix; a node under a node; a mesh drawn
  twice; the default scene only; no scene at all); every index width, no
  indices, an interleaved buffer, strips and fans, points or lines alone as a
  point cloud, a bad index; the room recovered the same as from an OBJ; and each
  refusal with its wording, as a reader and as a 400 from the route. Listed in
  "What slice 25 built".
- `backend/tests/unit/test_room_scan_zip.py` and
  `backend/tests/integration/test_api_room_scan_zip.py`: a scan in a zip
  (slice 26). A `.gltf` finds its `.bin` by the name it gives; an `.obj` with
  its `.mtl` and textures; each format from a zip; which of several models is
  read; macOS's leftovers; and each way a zip is refused, as a reader and as
  a 400 from the route. Listed in "What slice 26 built".
- `backend/tests/unit/test_room_scan_suggest_heading.py` (slice 27): a floor
  row on a stage at 30, 90 and -60 degrees ends where the square rule puts
  it, swung about the stage's middle (the swing is worked out in the test,
  not by the code under test); it is parallel to the turned edges, a metre
  apart still and in from every edge; each fixture is turned; a row at the
  front ends at the turned front; the same scan again moves nothing, for a
  row and for one fixture; a row already moved is fitted and not swung; a
  heading of 0, 180, 360, a string, a boolean, 1000 or NaN gives the moves
  and the JSON a stage with no heading gives, and those are pinned; in a box
  room and in an L-shaped room, at every heading 5 degrees apart with the
  stage in five places and rows of 1, 4 and 7, nothing is left outside the
  walls or in the drop under the ceiling and a second pass moves nothing; a
  row swung into the notch of an L comes inside whole; and the undo turns
  fixtures back, leaves one turned since, and keeps the old record for a
  move that turned nothing.
- `backend/tests/unit/test_room_scan_turned_stage.py` (slice 27): a stage
  built at 30, -20, 10 and 44 degrees comes back at that heading with its
  own sides and corners; the same from a scan held another way round and
  from a point cloud; a quarter turn of the room turns it with the room; a
  stage square or a degree or three off, an L-shaped stage, a corner piece
  and a round riser get no heading; and the scan's own suggestion lays a
  row on the turned stage it found.
- `backend/tests/integration/test_api_room_scan_turned.py` (slice 27): the
  route with a scan of a stage at 30 degrees. The preview names the turn
  and writes nothing, apply moves and turns the row and leaves a tapped
  fixture alone, the same file again moves nothing, and the undo puts each
  fixture back facing the way it faced.
- `backend/tests/integration/test_api_room_scan.py`: preview writes nothing;
  apply stores the shell and it comes back on the rig and in the rig list; only
  template guesses move, a row at a time, and stay guesses; tapped, confirmed,
  measured and row-fitted positions do not move; a second scan moves nothing; a
  DJ booth is suggested where there is one; the overrides; a binary USDZ and a
  bare `.usdc` are read; a binary layer that cannot be read and other
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
- `frontend/src/__tests__/StageView2D.test.tsx` (**passing**: first in the
  344 run of Nov 22 2026): the room layer drawn for a
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
  truss's reach; a snapped position still held to the walls; no snap with no
  scanned room; the grid drawn wall to wall, stopped at a notch, and the
  deck's own with no room. (Its test that a palette drop does not snap was
  taken out with slice 9: a drop now does.)

- `frontend/src/__tests__/rowMove2d.test.ts` (**slice 9; passing, frontend
  vitest 478**): the readout's words for a truss line, a ring and a row; what counts
  as on a truss; which fixtures are a row by group, by scanned truss line,
  angled line or ring, and by height and depth, with and without a scanned
  room; a row's shift held to the deck, to a box room and to an L (stopped at
  the notch, let into the other arm, a member that starts outside); moves
  put on a rig; the editor's store building a selection and selecting a row;
  a row move undone in one step with its heights, and redone; the height
  from before the drag being the one kept; a drag that changed no height
  undone with no heights touched; a height set on a fixture the row did not
  carry surviving the undo. **Slice 10, passing, frontend vitest 495**:
  address order; the nearest truss to a row, a ring by its centre; places
  along a line (even, the row's sense kept, none to keep), along an angled
  line and round a ring; a row laid in address order at the truss's height,
  laid again moving nothing, laid round a ring, laid close together; none
  of it laid when a place is beyond the walls; what is said for each; the
  lay undone in one step with its heights.
- `frontend/src/__tests__/StageView2DRowMove.test.tsx` (**slice 9;
  passing, frontend vitest 478**): a drag taking a truss line's and a ring's height,
  none out of reach, with Alt or with snapping off, and the pick-up height
  given back off the truss; the readout's text and place, and its going
  away; a palette drop snapping onto a line and a ring at their height, not
  out of reach, with Alt or with snapping off, and the readout over the
  landing spot; Shift, Ctrl and Cmd; a press on one of several selected; a
  modifier taking one out; a double-click asking for the row; a row moved by
  one shift, snapped onto a truss, part on it and part off, held at the wall
  of an L's notch and of a box room, held to the deck with no room, not
  snapping to its own depth in the Truss mode, and left selected when let go
  over the background; one fixture with no scanned room reported exactly as
  before.

- `frontend/src/__tests__/planSelect2d.test.ts` (**slice 11; passing,
  frontend vitest 576**): the threshold under, at and over 5 pixels in each direction;
  a box's corners in any order, what it takes in dragged each of the four
  ways, a centre on its edge, an empty box; a plain and an additive
  selection; an arrow key's shift, with Shift, and for other keys; a nudge
  of one fixture and of several, held at the deck's edge, at a box room's
  wall and at the notch of an L, going nowhere against an edge, and giving
  no height; which elements keep their keys.
- `frontend/src/__tests__/StageView2DSelectKeys.test.tsx` (**slice 11;
  passing, frontend vitest 576**): a click and a wobble moving nothing, for one
  fixture and for a row; a drag from exactly 5 pixels; a slipped
  double-click leaving an off-grid guess off the grid; a palette drop
  unchanged; a box drawn and let go, in each direction, plain and with
  Shift, Ctrl and Cmd, over nothing, under 5 pixels, carried off the plan,
  not from a press on a fixture, not on a read-only plan, and in a scanned
  room; Escape clearing the selection and letting go of a box; R; each
  arrow key, the grid step, Shift, a whole selection, the clamp at the
  deck, a room's wall and an L's notch, one drag reported for each press
  and none for a held key; keys left alone in an input, a textarea, a
  select, a contenteditable element and a dialog, with a modifier, with
  the keyboard off, and on a read-only plan.
- `frontend/src/__tests__/RigBuilderSelectKeys.test.tsx` (**slice 11;
  passing, frontend vitest 576**): the editor itself, with its side panels left
  out and the API a stand-in. A click or a wobble adds no undo step and
  sends nothing; a drag is one undo step and one batch-update; a box
  selects, and adds with Shift; Escape; each arrow press is one undo step
  and one batch-update; R then Shift+arrow moves the row whole to the
  deck's edge and no further; one Undo puts it back; keys typed in the
  rig's name do nothing.

- `frontend/src/__tests__/planTouch2d.test.ts` (**slice 12; passing,
  frontend vitest 654**): which pointers are a finger or a pen; a press undecided
  under 500 ms, a long-press from 500 ms held still or with a wobble, a
  drag from 5 pixels however short the press and when the time is up, and
  a decision that stays made; a pad arrow's shift for each direction, at
  10x, and against the matching arrow key; when the focus cue is due (a
  field, a drop-down) and when it is not (the page, a button, a dialog).
- `frontend/src/__tests__/StageView2DTouch.test.tsx` (**slice 12;
  passing, frontend vitest 654**): a long-press adding a fixture at 500 ms and
  not at 499, taking a selected one out, moving nothing wherever the
  finger then goes, and holding with a wobble; a finger's drag, tap and
  row drag; a pen; a mouse pointer left to the mouse events; a second
  finger; a cancelled press; a read-only plan and one that has gone. A
  long-press on empty floor marked and its box added to the selection, a
  plain box without the wait, lifted with no box, a tap still clearing
  the selection, a cancelled box. The pad shown only when asked for with
  something selected, after the plan in its box, every button named and
  44 pixels, each arrow against its key, the 10x switch, the clamp at the
  deck and at a room's wall, nothing reported against an edge, Select row
  and Lay on truss. The cue for a field, a drop-down and a field focused
  before the plan was drawn; none for a button, a dialog or a plan
  without the keyboard; a click, a finger and a press on a fixture each
  taking the focus back.
- `frontend/src/__tests__/RigBuilderRowLay.test.tsx` (**slice 12;
  passing, frontend vitest 654**): the editor itself. A row dragged is one
  batch-update and one undo step however many moves it took; one Undo
  puts it back, one Redo carries it again, and a new move after an Undo
  leaves nothing to redo. Lay on truss offered only with scanned truss
  and two selected; a laid row saved in one batch-update and one step at
  the truss's height; one Undo putting it back with its heights and one
  Redo laying it again; pressed again, nothing saved; the same from the
  pad's button.
- `frontend/src/__tests__/RigBuilderTouch.test.tsx` (**slice 12;
  passing, frontend vitest 654**): the editor itself. A long-press adding to the
  selection and taking out of it, with no undo step and nothing sent
  wherever the finger goes, and the next nudge a step of its own; a box
  after a long-press on empty floor; a finger's drag as one step and one
  batch-update; a tap. Each tap of the pad one step and one batch-update,
  the same request the key sends, a row at 10x held at the deck's edge,
  and one Undo putting it back. The cue while the rig's name is typed,
  gone after a click on the plan, with the keys working again.

- **Edit Room** (written with it; run Nov 23 2026 with the full suite:  backend pytest 1682 passed, frontend vitest 783 passed, build OK):
  `backend/tests/unit/test_room_scan_edit.py`: a rename changing nothing
  else, the shell given left unchanged, blank and over-long names; a move of
  a raised area, one axis alone, a line keeping its length and heading, a
  move to where it is, the hold to the room and its margin, a centre that is
  not a number, an item with no position; a delete moving the rest up, the
  hanging bands after a deleted line or ring, and a row no longer hung at a
  deleted truss's height; each refusal.
  `backend/tests/integration/test_api_room_scan.py`, `TestRoomShellEdit`:
  the same through the routes, read back from the rig and from the database
  row; fixtures and the undo record untouched; the 404s (no room, no rig, no
  such place, a list that cannot be edited) and the 422s (a blank or 61
  character name, an empty body, a centre or an index that is not a number),
  but not the 409, a 200 character name or a shell that is not a scan; a
  scan read again replacing the edits; both routes behind the login.
  `frontend/src/__tests__/roomShellEdit.test.ts`,
  `RoomShellEditDialog.test.tsx` and `RigBuilderRoomEdit.test.tsx`: which
  items are listed and by which place, what a row sends, the wording; the
  dialog's save, delete question, delete and refusal; the button offered
  only with a scanned room, a renamed truss on the plan with no reload, a
  deleted truss gone from the plan and from Lay on truss, and a fixture move
  and its undo step left as they were.

- **Slice 15** (written with it, Nov 23 2026. **Backend: run and passing**,
  full suite 1794 passed, 10 skipped, 5 xfailed. **Frontend: type-checked
  only when written** — `tsc --noEmit` shows the same 13 errors in untouched files as
  before and none new, but `npx vitest run` and `npm run build` were refused
  by the session's permissions, so the three new test files and the changes
  to the three Edit Room ones were not run then; the whole frontend suite
  was run after slice 18 and passed, 943 tests):
  `backend/tests/unit/test_room_scan_adjust.py`: a width, depth, length,
  radius, height and heading each changing that and nothing else, the shell
  given left unchanged, a value it already has changing nothing; a line made
  longer along its own ends and turned about its middle, the heading as it
  is stored for each way of writing it; the whole of a resized, turned or
  added item held inside the room and one too big refused, with a plain move
  still holding only the middle; each limit, a value that is not a number, a
  size the item does not have, an item with no position; a truss's top going
  with its height; the bands after a truss is raised within its band, into
  another, to where nothing hangs, and out of a band it was alone in, with
  the counts adding up each time, and a row no longer hung at the height a
  ring left; each kind added, its default name, its marks, a legacy shell
  with no rings, the 50 limit and each refusal; the words for a step; the
  undo record pushed, popped, capped at 20, left unchanged, and read from a
  record that cannot be.
  `backend/tests/integration/test_api_room_shell_adjust.py`: the same
  through the routes, read back from the rig and from the database row, with
  fixtures and the scan's undo record untouched; each refusal writing
  nothing and leaving no step, a raw `Infinity` among them; five different
  edits undone one at a time back to the scanned room; the 20 step limit;
  the steps cleared by a scan applied again (and not by a preview) and by
  the room taken off; every edit, add and undo refused with 409 under a
  running locate walkthrough, before any other reason but an unknown rig or
  an unreadable body, with another rig and a finished walkthrough holding
  nothing; the new routes behind the login.
  `backend/tests/integration/test_zones_and_layout.py`: migration 008 adding
  the column and inventing no step.
  `frontend/src/__tests__/roomShellAdjust.test.ts`,
  `RoomShellAdjustDialog.test.tsx` and `RigBuilderRoomAdjust.test.tsx` (**not
  run**): the sizes a row holds and sends, `lineHeading`, the marks, each
  problem, a quarter turn, the wording of a resize, the Add form's defaults,
  bodies and problems, the Undo button's words; the dialog's size fields,
  Turn, Add (the kind's own fields, the row it makes, a refusal), Undo (one
  press one step, typed rows cleared, a refusal under a walkthrough); and in
  the editor, the undo count the rig came with, a raised stage and an added
  truss on the plan with no reload, the room's Undo leaving a fixture move
  and the editor's own undo step alone, and the count kept when the dialog
  is closed and opened again.
- **Slice 16 (the walls).**
  `backend/tests/unit/test_room_outline_edit.py` (run, 54 pass): a box
  room's four corners in the plan's order; an outline stored as `{x, z}`
  with the origin-centred box round it; a box still stored as a box; the
  same walls changing nothing; corners turned clockwise; each refusal's
  sentence (count, a number missing or infinite, reach, two corners
  together, a bow tie, a corner on another wall, a spike, too little floor,
  too narrow, the height); three corners in a line let through; one corner
  moved, added (half way, at a place, after the last) and deleted, the
  three-corner and 64-corner limits, a triangle turned inside out; and the
  outside report (on a wall is inside, the notch of an L, part against all
  of an item, a lowered ceiling, `already_outside`, a broken item left out).
  `backend/tests/integration/test_api_room_outline.py` (run, 17 pass): each
  route stored and read back from the rig and the database row, nothing
  else in the room and no fixture changed, the fixtures and the riser the
  new walls cut off listed, the height, a no-op leaving no step, a box kept
  a box, **a fixture placed by a wall 10 m from the origin not shifted**,
  five edits undone one by one back to the scanned room, the undo's own
  `outside`, the 404s and 409s, every 422 with a raw `Infinity` and `NaN`
  among them, the list routes not taking `outline` for a list, the locate
  walkthrough's 409 on all five, a scan read again replacing the walls and
  their undo, and the login.
  `frontend/src/__tests__/roomWallsEdit.test.ts`,
  `RoomShellWallsDialog.test.tsx`, `StageView2DWalls.test.tsx` and
  `RigBuilderWalls.test.tsx` (written unrun; run with the whole frontend
  suite after slice 18, which passed): the helpers; the
  Walls section's rows, a corner saved, added and deleted, the height, a
  refusal, the warning list on opening, after a change and after Undo, the
  hand-over button; the plan's handles, the 5 pixel threshold, one call for
  a drag, the grid and Alt, the corner held where it was dropped until the
  answer and put back when refused, fixtures taking no press; and in the
  editor one request for a drag, the answered walls drawn with no reload, a
  refusal, the list of what is outside, the strip's Undo, and fixtures
  carried again once walls mode is done.
- **Slice 17 (fixtures follow their truss).**
  `backend/tests/unit/test_room_scan_carry.py` (run, 22 pass): the reach on
  the plan and in height, past a line's end, a ring, missing numbers, two
  crossing trusses each keeping its own; a move, a height, a length, a
  turn, a ring's radius, move and height; **a light square to the truss
  still square to it after a turn**, checked against the rig's own rotation
  matrix; 80 degrees to -80 being 20 degrees on and swapped ends being no
  turn; the stored middle followed, not the one asked for; a rename and a
  no-op carrying nothing, and (since slice 18) a raised area taking what
  stands on it and never what hangs over it; only position and heading
  written; the refusal's sentence, the margin itself being inside, the
  floor and the ceiling; an undo putting back exactly and leaving one moved
  since or gone; a record that cannot be read; the sentences.
  `backend/tests/integration/test_api_room_shell_carry.py` (run, 11 pass):
  a move, a raise, a turn and a shorter line over HTTP with every other
  field of every fixture unchanged and the other lights untouched, the step
  stored with its fixtures, `carry_fixtures` false and null, a rename, a
  raised area told to go alone and one made another kind (since slice 18), a ring made bigger then moved and raised and undone twice,
  the 422 writing nothing and the truss alone allowed, one undo restoring
  truss and fixtures, a dragged fixture left by the undo, and the 409 under
  a walkthrough for the edit and the undo.
  `frontend/src/__tests__/RoomShellCarryDialog.test.tsx` and
  `RigBuilderRoomCarry.test.tsx` (written unrun; run with the whole frontend
  suite after slice 18, which passed): the box on a line and a ring, a
  raised area's being worded for what stands on it (since slice 18), what is sent ticked and
  unticked, the notice for several, one and none, no flag with a rename,
  the server's refusal shown, `onFixturesMoved` after a carry and after an
  undo that restored and not otherwise; and in the editor the rig read
  again, the plan redrawn, the editor's undo steps dropped, nothing read
  again when the truss went alone, and both Undo buttons.
- **Slice 25 (glTF import).** Backend, and one constant, one sentence and one
  test in the frontend. **Run (Nov 24):** backend pytest, whole suite,
  2105 passed, 10 skipped, 5 xfailed (2029 passed before this slice); `tests/unit/test_room_scan_gltf.py` 71 and
  `tests/integration/test_api_room_scan_gltf.py` 4 of them. **Not run:**
  `npx vitest run` and `npx tsc --noEmit` (no `node_modules` in the worktree,
  `npm ci` refused), so the new test in `roomScan.test.ts` has never been
  executed. What each test file covers is listed under Tests in "What slice
  25 built".
- **Slice 23 (the booth and the crowd in a scanned room).** Frontend only.
  **Run (Nov 24):** `npx vitest run` 1163 passed in 55 files, `npm run build`
  OK, `npx tsc --noEmit` only the 13 older errors.
  `frontend/src/__tests__/scanFloor.test.ts` (35 tests): no booth made up
  for a room with no booth and no stage; a guessed booth at the downstage
  middle of the first stage, kept there in a corner and turned only for a
  wall right in front; no DJ where a riser stands behind the desk; the
  room's own booth before the stage; a counter against a wall and one out
  from it, one on a side wall, one in the arm of an L, and a low platform;
  the open floor less its margins from the walls and the raised areas; an
  L-shaped room without its notch; the same crowd twice and another after
  an edit; never more people than asked for or than fit; the crowd clear of
  a stage, a riser and each other, denser near the booth and facing it; the
  booth's strip, the DJ's room and the Floor camera's; nobody where no
  floor is left. And for a raised area at a heading (slice 21): what is
  listed under Tests in "What slice 23 built" (a stage turned 30, 90 and
  -60 degrees, a booth turned 30 and 90, the crowd kept off every turned
  footprint, and a heading of 0 changing nothing).
- **Slice 22 (heights by dragging).** Frontend only. **Run afterwards (Nov 24,
  ~1:10 AM ET, by the overnight Grok run):** `npx vitest run` 1128 passed
  (1084 on its base), `npm run build` OK, `npx tsc --noEmit` only the 13 older
  errors, backend pytest 2029 passed, 10 skipped, 5 xfailed. When it was
  written it was not run and not type-checked: the worktree had no `node_modules`, and `npx
  vitest run`, `npm run build`, `npm ci`, `tsc` and running a script with
  `node` were each refused. The expected numbers were worked out by hand.
  The backend suite, which this slice does not touch, was run before and
  after it: pytest `tests/` 2029 passed, 10 skipped, 5 xfailed both times.
  `frontend/src/__tests__/roomItemHeight.test.ts`: the handles of a raised
  area on the floor and of a floating one, a deck held under a low ceiling,
  the one trim handle of a line and of a ring, a room with no ceiling, no
  item and one with no height; the 0.05 and 0.25 m steps, the millimetre,
  a handle let go where it stood, a truss held between 0.5 m and the
  ceiling, a ceiling off the step, the deck above its base from the top,
  the whole area from the base and down to the floor, a grip the item does
  not have, the flag `withCarry` adds; and the words.
  `RoomItemHeightStrip.test.tsx`: the empty strip; the handles of a truss,
  a ring and a raised area and where they stand; a drag drawn as it goes
  with the live value and one call when let go; down to the least; Shift
  and the Step button; nothing under 5 pixels or brought back; a drag that
  leaves the strip sideways; a finger, a second finger and a press the
  browser took; another mouse button; the top, the base and a platform
  brought down; the drop kept until the answer and no second drag
  meanwhile; put back when refused; and one item's drop not drawn on
  another.
  `RigBuilderItems.test.tsx` (a second `describe`): the strip there for the
  whole of the mode and gone after it; a truss raised with one
  `editShellItem`, `carry_fixtures` true, the rig read again, the notice
  and the undo label; Shift; the box unticked sending false; a deck from
  the top and a base from the base, one request each; nothing under 5
  pixels; a 422 and a 409 each put back with the server's words; and the
  strip's Undo.
- **Slice 21 (a raised area at a heading).** The backend tests were run
  after it: pytest `tests/` 2029 passed, 10 skipped, 5 xfailed (1990 before it). The frontend
  tests are **written and type-checked but not run** (its commit says so);
  see What is left.
  `backend/tests/unit/test_room_scan_heading.py`: one that stores none
  standing square, a heading stored folded and marked, half a turn being
  no turn and a tenth the least, what is not a heading refused, the undo
  words; its reach and its corners as it stands, a turn bringing the middle
  in, one too long for the room refused, a resize of a turned one going by
  its reach; an added one storing its heading and a square one saying
  nothing; a fixture over its footprint as it stands and at a corner, a
  riser standing on it; each fixture swung about the middle with its own
  heading turned, a turn to 90 as the quarter turn, a turn and the turn
  back to the millimetre, the smaller of the two turns, sides swapped and a
  heading changed in one request, a move and a height with a turn, a
  resize by share along the area's own sides; the stack swung about the
  stage's middle and turned with it, one already at a heading keeping how
  far off square it was; and a turned area past a wall listed where a
  square one is not.
  `backend/tests/integration/test_api_room_shell_heading.py`: over HTTP, a
  heading stored and the row standing on it going round its middle; a turn
  to 90; `carry_fixtures` false and the same heading changing nothing; a
  heading that is not one refused and writing nothing; the 409 under a
  walkthrough; a riser going round with the stage and taking its heading;
  and `POST` keeping a heading and saying nothing of a square one.
  `frontend/src/__tests__/raisedAreaHeading.test.ts`: the fold, the
  footprint and its corners, the sides' names; the plan's heading, corners,
  words and size; the 3D box turned the same way round; the snap lines'
  edges; the nine handles where they stand and their cursors; the rotate
  handle (folded, 5 degrees, a tenth, 15 with Shift, a truss line too);
  resizing a turned area along its own sides; and the helpers (`shellItems`,
  the row's draft, `readDraft`, `withCarry`, `editResultText`,
  `readNewItem`).
  `RoomShellRaisedDialog.test.tsx`, `StageView2DItems.test.tsx` and
  `RigBuilderItems.test.tsx` each gained cases: the Heading field on a row
  and on the Add form; the plan's turned rectangle and rotate handle, one
  call when it is let go and put back when refused; and in the editor one
  `editShellItem` with `heading_deg`.
- **Slice 20 (a stack of raised areas, the Add form's base, resize
  handles).** The backend tests were run after it: pytest `tests/` 1990
  passed, 10 skipped, 5 xfailed (1951 before it). The frontend tests are
  **written and type-checked but not run**: the session was refused `npx
  vitest --run`, `npm test` and `npm run build`. `npx tsc --noEmit` passes
  with the 13 errors it had before, none in a file this slice touched.
  `backend/tests/unit/test_room_scan_stack.py`: what stands on a raised
  area (the whole stack and never itself, the 0.1 m at the base, the middle
  inside the footprint and on its edge, a number missing, two that each
  stand on the other, each fixture on one area); a move shifting every
  area above and its fixtures, a height and a base height raising the
  bases, a base never under the floor, a quarter turn about the middle
  with a square platform's fixture turned, the sides of one that is not
  square swapped, a resize, a rename and a kind carrying nothing, a middle
  brought in being followed, the area underneath not carried by the one on
  top; the refusal past the margin and above the ceiling; the room given
  left unchanged; the answer's list and the sentences; and an added
  platform's base (left out, given, its limits, not a number, the ceiling
  in the edited base's words, the deck's own limits, none for a truss).
  `backend/tests/integration/test_api_room_shell_stack.py`: over HTTP, a
  moved stage taking the riser on it and the light on that, with
  `items_moved`, the message, the undo label, the stored room and nothing
  else changed; a higher deck and a base height; a quarter turn of a
  square riser and its light; `carry_fixtures` false and a resize alone
  leaving the riser; a riser on the floor beside the stage not carried,
  with the words and label as before the slice; the 422 for a riser above
  the ceiling, for one past the margin and for a light on the riser
  leaving the room, each writing nothing; one undo putting the stage, the
  riser and every light back; the 409 under a walkthrough; and `POST` with
  a base (on the floor with none, floating with one, the limits, infinity
  and NaN, the ceiling, none for a truss).
  `frontend/src/__tests__/RoomShellStackDialog.test.tsx`: the Add form's
  base height field for the three raised kinds and not for a truss or a
  ring; a floating platform sent with its base; none sent for 0 or an
  empty field; a wrong one saying why and sending nothing; the base kept
  between raised kinds and not holding up a truss; the server's ceiling
  refusal shown; the notice when a riser went with its stage, with and
  without fixtures; and the helpers (`newItemDraft`, `readNewItem`,
  `stackedText`, `carriedText`, `editResultText`).
  `roomItemDrag2d.test.ts`: the eight handles and where each stands,
  `isBoxGrip` and the hints; an edge and a corner about the middle, only
  what changed sent and never the middle; the grid's step and the
  millimetre; the least side; a handle let go where it stood; and no such
  grip on a line or ring.
  `StageView2DItems.test.tsx`: the eight handles on a selected raised area
  and none on one not selected; an edge drag drawn as it goes and one call
  with the width; a corner with both; the upstage edge with the front to
  back alone; nothing under 5 pixels or brought back; the drop kept until
  the answer and put back when refused; and the body still moving it.
  `RigBuilderItems.test.tsx`: an edge and a corner each one `editShellItem`
  with `carry_fixtures` true and no centre; the box unticked sending
  false; nothing under 5 pixels; a 422 and a 409 each put back with the
  server's words; and the strip saying that a riser went with its stage.
- **Slice 19 (items arranged on the plan).** Frontend only, and **written
  and type-checked but not run**: the session that wrote them was refused
  `npx vitest run` and `npm run build`, as the sessions of slices 15 to 17
  were. `npx tsc --noEmit` passes with the 13 errors it had before, none in
  a file this slice touched.
  `frontend/src/__tests__/roomItemDrag2d.test.ts`: what can be picked up
  and by which stored place, the footprints and the handles, a move to the
  grid and off it, a moved line keeping its shape, a drag that ends where
  it began, a length about the middle and its least, a heading folded as
  the server stores one and snapped to 5 degrees or a tenth, a radius and
  its least, a grip the shape does not have, and a nudge sending one axis.
  `StageView2DItems.test.tsx`: nothing to pick up with the mode off, on a
  read-only plan or with no room; the stored place in each test id; a
  press selecting and a wobble under 5 pixels sending nothing; one call
  for a whole drag, with the middle alone; Alt letting go of the grid; a
  drag brought back sending nothing; the item kept where it was dropped
  until the answer, then put back; a drag carried off the plan; handles on
  the selected item only; the length, rotate and radius handles; the arrow
  keys, Shift, a held key, nothing selected, the mode off and a field
  having the keys; Escape and empty floor; the click that ends a drag; no
  fixture picked up or boxed; and the layer being over the fixtures.
  `RigBuilderItems.test.tsx`: the hand-over from the dialog; a truss moved
  with one `editShellItem`, `carry_fixtures` true, the rig read again and
  the fixtures redrawn, the room's undo label and no editor undo step; a
  raised area moved to the grid with nothing read again; the 5 pixel
  threshold; the box unticked in the dialog and in the strip both sending
  `carry_fixtures` false; a 422 and a 409 each put back with the server's
  words; two quick arrow keys as two requests, the second from where the
  first left the truss; Shift and a held key; the length, rotate and
  radius handles each one request; the strip's Undo with fixtures put
  back; fixtures taking no press until Done arranging; and Back to Edit
  Room.
- **Slice 18 (raised areas).** Run after it: backend pytest 1951 passed,
  frontend vitest 943 passed, and the build.
  `backend/tests/unit/test_room_scan_raised.py`: what stands on a raised
  area (the footprint and its margin, the window at the top, a floating
  area's base and height together, a number missing, a light hung on a
  truss over the stage staying the truss's, the nearer top of two and the
  first listed when as near); a move, a height and a base height, a resize
  by share, a quarter turn with the heading, a middle brought in to fit
  being the one followed; a rename, a kind change and a no-op carrying
  nothing; only position and heading written, and the undo putting back
  exactly; the refusal past the margin and through the ceiling's margin; a
  riser made a stage keeping its place and taking the kind's name, a given
  name kept and a sent one winning, the same kind changing nothing, a wrong
  kind and a kind for a truss refused, `first_stage`, a suggestion going by
  the first stage of the shell it is given and lifting onto a floating
  stage's top; a base stored to the millimetre, a missing one read as the
  floor, the limits of 0 and 10 m, a top above the ceiling refused and a
  height going by the new base, no base for a truss, an added area on the
  floor unless given one; the sentences, and the step remembering which
  list.
  `backend/tests/integration/test_api_room_shell_raised.py`: over HTTP, a
  moved stage taking the row standing on it and nothing else, a higher
  deck and a base height, a resize, a quarter turn, `carry_fixtures`
  false, a light on a truss over the stage left with its truss; the 422
  writing nothing; a riser made a stage and a stage made a booth with
  `riser_kind`, `first_stage` and the undo labels answered, no fixture
  moved, and both undone back to the scanned room; the same kind being no
  change and a wrong or empty one refused; a base height refused outside
  its limits, a platform added floating, a base of 0 being no change; one
  undo putting the stage and what stood on it back, a fixture moved since
  left where it was put; and the 409 under a walkthrough.
  `frontend/src/__tests__/RoomShellRaisedDialog.test.tsx`: the box on each
  raised area, worded and ticked; the kind and base shown, and neither on
  a truss; a stage moved with its fixtures, the count in the notice and
  the rig read again; the box unticked; a riser made a stage with no word
  about fixtures; the kind it already is being no change; a base height
  taking what stands on it up; a kind, a base and a height in one save; a
  wrong base height saying why and sending nothing; the server's refusal
  shown; an undo that put fixtures back having the rig read again; the
  helpers (the words, the flag, the row's base and kind, `readDraft`,
  `editResultText`, the delete question, the "Kind set by hand" mark); the
  2D plan's tooltip for a floating area; and the 3D box drawn from its base
  up.

For the walkthrough video:

- `backend/tests/unit/test_room_video.py`: the missing-tool messages and how
  COLMAP is found; which frames are dropped as blurred, repeated or black, and
  how too many are thinned; **frame sampling with real ffmpeg and real OpenCV**
  on clips made by ffmpeg (skipped where they are not installed): a portrait
  clip whose middle barely changes, a clip filmed upright with its rotation in
  the metadata, a dark clip, a clip that never moves with and without grain,
  and a file that is not a video; the room recovered from **sparse, noisy
  clouds with strays** (600 to 5,000 points), which is what a video gives; an
  outside tool run, stopped and timed out for real (with the Python
  interpreter as the tool); COLMAP's text files read back into camera positions;
  a model tipped about every axis stood up to within 0.15 degrees, where the
  phone's own down was more than 3 degrees out; the room recovered at its real
  size from a ceiling height and from a wall length, and through the scan
  reader with its stage intact; the assumed scale, and its warning; the whole
  run in order against a stand-in for COLMAP (CPU retry, the larger of two
  models, each failure's wording, dense falling back to sparse); and the job
  runner (off the calling thread, one at a time, stop, crash, cleanup,
  shutdown).
- `backend/tests/integration/test_api_room_video.py`: the tools answer; a video
  sent with no COLMAP is answered, not failed; starting does not wait; the
  result previews and applies through the ordinary route and lands on the rig;
  the assumed-scale warning reaches the preview; a second measurement needs no
  second reconstruction; stop frees the slot; a job belongs to its rig; the
  size limit, declared and undeclared; the login.
- `frontend/src/__tests__/roomVideo.test.ts`: paths, which files are refused
  before sending, the measurement and its parameters, and the status wording.
  **Written but not run** (`npx vitest run` was refused again in the session
  that put it on master; `npx tsc --noEmit` ran with only its 13 older errors).

**What these do not show:** that a real COLMAP accepts the commands in step 2,
that its text output is laid out as the stand-in writes it (it follows COLMAP's
documented format), or that a real room's sparse cloud is dense enough for the
reader to find walls in. The stand-in proves the steps are called in order and
their files read. Nothing more.

## What is left

- **Slice 32's frontend test has not been run, and nor has the build with
  it.** `npx vitest run` and `npx vite build` were refused in the session
  that wrote it, as for slices 29 to 31; `npx tsc --noEmit -p .` ran with
  its 13 older errors and no new one, and the backend suite ran. Before
  relying on it, in `frontend/`: `npx vitest run` (it adds one file,
  `RoomScanDialogHandEdits.test.tsx`, 8 tests) and `npx vite build`. The
  likeliest thing for a first run to find is the `alert` role it tells the
  warning by. **Not seen in a browser**: the line under the preview note.
- **Slice 33's frontend test has not been run, and nor has the build with
  it.** `npx vitest run` and `npx vite build` were refused in the session
  that wrote it, as for slices 29 to 32; `npx tsc --noEmit -p .` ran with
  its 13 older errors and no new one, and the backend suite ran. Before
  relying on it, in `frontend/`: `npx vitest run` (it adds one file,
  `RoomScanDialogHandEditsOverhead.test.tsx`, 7 tests, and the 8 of
  `RoomScanDialogHandEdits.test.tsx` must still pass with the helper
  changed) and `npx vite build`. **Not seen in a browser.**
- **Slice 34's frontend tests have not been run, and nor has the build
  with it.** `npx vitest run` and `npx vite build` were refused in the
  session that wrote it, as for slices 29 to 33; `npx tsc --noEmit -p .`
  ran with its 13 older errors and no new one, and the backend suite ran.
  Before relying on it, in `frontend/`: `npx vitest run` (two new tests,
  and three older ones hold the new delete question) and `npx vite build`.
  **Not seen in a browser.**
- **Slice 35's frontend test has not been run, nor the type-check, nor
  the build.** `npx vitest run` and `npx vite build` were refused in the
  session that wrote it, as for slices 29 to 34, and this time the
  worktree had no `frontend/node_modules`, so `npx tsc --noEmit -p .`
  could not run either: **the dialog change is checked by no tool.**
  Before relying on it, in `frontend/`: `npx tsc --noEmit -p .` (13 older
  errors; none should be in `roomScan.ts`, `RoomScanDialog.tsx` or the new
  test), `npx vitest run` (one new file,
  `RoomScanDialogHandEditItems.test.tsx`, 13 tests; the tests of the
  two older hand-edits files, 8 each, must still pass with
  `handEditsLine` changed) and `npx vite build`. **Not seen in a browser.**
- **Slice 36's frontend test has not been run, nor the build.** `npx
  vitest run` was refused in the session that wrote it; `npx tsc --noEmit
  -p .` ran with its 13 older errors and no new one, and the backend suite
  ran. Before relying on it, in `frontend/`: `npx vitest run` (one new file,
  `RoomScanDialogCarryOver.test.tsx`, 5 tests) and `npx vite build`.
  **Not seen in a browser.**
- **What slice 37 leaves** (keep all, the stored list):
  - **The second entry of the two-entry HTTP test is made by hand** (a
    raised area renamed): the test room loses one truss only. Two real
    losses are tested through `carry_all()` in the unit tests.
  - **A fixture two entries would each move refuses Keep all** rather than
    being moved once by the sum: keep those one at a time.
  - **An entry is dropped on any change to its item's name, height or base
    height**, even one back to the same value later; the room's Undo is the
    way back.
  - **The reopened list has no "Kept ..." state** once the rig is read
    again: a kept entry simply leaves the list.
  - **The stored list is not shown in the 3D view** or the Edit Room
    dialog: only in the Room Scan dialog.
- **What slice 36 leaves** (carry-over):
  - *Closed by slice 37:* a carry-over is one item at a time: "Keep all"
    sends every entry in one request, as one Undo step, all or none.
  - *Closed by slice 37:* the buttons are in the answer only. The open
    entries are kept with the stored room (`room_shell.pending_carry_over`,
    GET `.../room-scan/carry-over`), and the dialog opened again shows them.
  - **A raised area's footprint is not carried**, on purpose, as slice 32
    keeps none.
  - **"No longer read" has no button**: there is no item to put it on.
  - **Carrying over "another has it" replaces the winner's edits** on that
    item: Near's name goes onto the area Nearer had, and Nearer's is gone.
    The operator chose it; Undo takes it back.
  - *Closed by slice 37:* the button finds its warning by place. Each
    warning with an entry has an `id`, and the entry the same as
    `warning_id`: the dialog matches by that, so a warning it passes over
    shifts nothing.
  - **The carry-over route is not tested with fixtures hung on the truss**
    or during a locate walkthrough: both rest on the PATCH's tests of the
    shared rules.
- **What slice 35 leaves** (the list by name, and what is lost):
  - *Closed by slice 36:* a raised area's name or height lost to a reading
    to one side is named, with the new area, and can be carried over.
  - *Closed by slice 36:* a truss the scan no longer reads at all is said:
    "The scan no longer reads Front truss; its name and trim go with it."
  - *Closed by slice 36:* of two stored items that pick the same new one,
    the one that does not have it is named with the one that does, and
    can be carried over onto it (slice 32, point 3).
  - **A record dropped because the scan read the thing at another height
    or to one side is said as "the scan did not see"**, and the thing is
    back in the room at once, not "on a later scan". The warning for a
    record does not say what the scan read there instead.
  - **A new truss that crosses the place of a named one the scan no
    longer reads** is taken for that one read beside it (they share a
    little of the plan, and no stored truss is the new one), and the
    warning gives the distance between their middles.
  - *Closed by slice 36:* warnings can be acted on. "Keep Front truss on
    this one" puts the name and trim onto the truss the warning speaks of
    (POST `.../room-scan/carry-over`), marked as set by hand, as one Undo
    step.
  - *Closed by slice 37:* the list is not kept once the dialog is closed.
    What can still be put back is kept with the stored room.
- **What slice 34 leaves** (deleted lines and rings, hanging heights):
  - *Said since slice 35:* **a truss re-trimmed by more than 1.0 m between
    two scans is another truss** (`HANG_MATCH_M`): its name and trim are
    not kept, and a record of it deleted is dropped, so it comes back.
    Both are now named in `hand_edits.warnings` and shown in the dialog.
    The scan still has to read it within 1.0 m of where the last scan did
    for anything to be kept.
  - **Two trusses on one footprint less than 1.0 m apart in height** are
    still told apart only by overlap and order, as before this slice.
  - **A trim set by hand before this slice is matched without a height**
    until a scan applied again keeps it once (it then has `scan_height`).
    In a stack, such a truss can still take the other one's place at that
    one reading. A line **added by hand** is never compared by height:
    one added under a scanned truss on the same footprint still matches
    that truss on the plan. Where the scan's own stored truss matches it
    as well, that one has it and the added one is replaced and reported
    (as slice 33); where none does, the added one gives the scan's truss
    its name and height, whatever height the scan read it at.
  - **`scan_height` is not shown or editable**, and Edit Room's Undo of a
    trim takes it away with the trim (the whole room is put back).
  - **A deleted line's record takes the scan's line before anything else
    is matched**, as a raised area's does (see the slice 33 point below),
    and it cannot be seen or removed on its own.
  - *Closed by slice 35:* the dialog names. Under the line of counts each
    thing is listed with what it is ("line", "ring", "raised area") and
    what happened to it.
- **What slice 33 leaves** (lines, rings, deleted areas and checks):
  - *Closed by slice 34:* a deleted line or ring no longer comes back. A
    scanned one leaves a record, as a raised area does, and the next scan
    leaves it out.
  - *Closed by slice 34:* hanging heights are compared when a line or a
    ring is matched (within 1.0 m of where the scan read it), so two
    trusses one above the other on the plan keep their own names and
    trims.
  - *Said since slice 35:* **a truss read more than 0.2 m to one side is
    another truss** (the strip is 0.6 m wide, `LINE_STRIP_M`), and so is
    one read at much less or much more than its length: its name and trim
    are not kept. Where the two readings still share some of the plan (up
    to 0.6 m to one side) a warning names it and says how far off the scan
    read it; read clear of where it was, nothing is said.
  - **A line added by hand within about 0.4 m of a scanned truss and
    running beside it is replaced** (they share more than a fifth of the
    two strips, `CROSSING`); one that crosses a truss is kept. Two short
    lines that cross (both under about 2 m) can share more than a fifth
    and be replaced. A ring added by hand inside a scanned ring is replaced
    when its radius is over about 0.45 of the scanned one's: a ring's
    footprint is its whole disc.
  - **A record that matches nothing is dropped.** If one scan misses the
    deleted thing, or reads it less than half over where it stood, the
    record goes, and a later scan that reads it again brings it back.
    *Said since slice 35:* a warning names each record dropped.
    Reading the room a quarter turn round (**Turn the room**) drops every
    record, as it drops every other match.
  - **A record cannot be seen or removed on its own.** Nothing in Edit
    Room lists `deleted_areas`. The ways to forget one are the room's Undo
    (while the delete is still among its steps: a scan applied again
    empties them) and taking the room off the rig.
  - **A record takes the scan's raised area before anything else is
    matched.** An edit cannot be kept on an area that is left out, and the
    DJ booth mark cannot land on it. It takes it even where a raised area
    still in the room overlaps that new area more: where the scan read two
    risers on one spot, one was deleted, and the next scan reads only one
    there, that one is left out (and reported), and the riser that was
    kept is gone with it.
  - **Warnings are said, not acted on.** A kept trim above the new ceiling
    stays where it is and still counts in `hanging_bands`, so a suggestion
    can hang rows at it. Only what was kept is checked: something the scan
    itself reads outside its own walls is not listed here
    (`GET .../room-shell/outline` lists everything outside).
  - *Closed by slice 35:* the dialog names. Each entry of
    `hand_edits.warnings` is on screen as a warning ("Check Podium: it is
    outside the walls of the room as this scan reads it."), and the list
    under the line of counts says "line" or "ring". The line of counts
    itself still says "overhead items".
  - **Edit Room shows no chip for a line's name or trim set by hand**, as
    for a raised area's name.
- **Keeping hand edits goes only so far** (slice 32):
  - *Closed by slice 33:* a line and a ring now keep a name and a hanging
    height, and one added by hand is kept. A line's length, heading and
    place set by hand are still the scan's again, as a raised area's
    footprint is.
  - **A footprint set by hand is not kept**, on purpose: width, depth,
    heading and place are read again. An operator who widened a stage the
    scan reads too narrow has to widen it again. An area added by hand and
    kept as it is, is the exception: all of it is the person's.
  - **A kind set by hand is kept only on the marked DJ booth** (slice 31).
    On any other raised area it lets the area match whatever kind is read
    there, so its name and heights are kept, but the kind is the scan's
    again.
  - *Closed by slice 33:* a deleted raised area no longer comes back. The
    room remembers it (`deleted_areas`) and the next scan leaves it out.
  - **A room edited before this slice keeps nothing**: its basis says
    "Resized by hand." at most, which does not say a height was set, and a
    rename left no mark. Rename or set the height once more and it is kept
    from then on.
  - **A raised area moved with the one it stands on is not "set by hand"**
    (`carry.py`): its base height changed because its carrier's did, and
    its basis says "Resized by hand." only. It is not kept.
  - **An area added by hand that shares any floor with a new raised area
    is replaced whole**, even a sliver of overlap, and its name and height
    go with it unless it matches (half the two footprints together). The
    answer names it, so it can be added again.
  - **A raised area added by hand on top of a scanned one is always
    replaced** (a drum riser put on the scan's stage): it shares floor
    with the stage, and heights are not compared. Add it again after the
    scan, or scan with it in place.
  - *Closed by slice 33:* a kept height above the new ceiling, and
    something added by hand that the new walls leave outside, are still
    kept, and are now listed in `hand_edits.warnings` and said in its
    `message`.
  - **The moves follow the room with the edits**: a kept height on the
    first stage changes where the floor lights are suggested. Held by the
    slice 31 test for a kept kind, not by one of its own.
  - **Two stored areas that pick one new area**: the greater overlap has
    it and the other keeps nothing. The DJ booth mark is asked on its own,
    so in that corner the mark can sit on a raised area named after the
    other.
  - **Edit Room shows no chip for a name set by hand**, and after a scan
    is applied again a kept height shows as "Resized by hand".
  - **After Apply the dialog's line counts areas**; the names are in the
    list under it since slice 35. Which fields were kept (name, height)
    is still only in the answer's `hand_edits.message`.
- **Slice 31's frontend tests have not been run, and nor has the build
  with it.** `npx vitest run` and `npx vite build` were refused in the
  session that wrote it, as for slices 29 and 30; `npx tsc --noEmit -p .`
  ran with its 13 older errors and no new one, and the backend suite ran.
  Before relying on it, in `frontend/`: `npx vitest run` (it adds one file,
  `RoomScanDialogDjBoothPreview.test.tsx`, 8 tests) and `npx vite build`.
  The likeliest thing for a first run to find is in that file: it tells
  the warning from the plain line by the `alert` role and a class name of
  the MUI Alert. **Not seen in a browser**: the line under the preview
  note.
- **The preview's mark goes only so far** (slice 31): see the slice 30
  list below, which it closes two points of and adds to.
- **Slice 30's frontend tests have not been run, and nor has the build
  with it.** `npx vitest run` and `npx vite build` were refused in the
  session that wrote it; `npx tsc --noEmit -p .` ran with its 13 older
  errors and no new one, and the backend suite ran. Before relying on it,
  in `frontend/`: `npx vitest run` (it adds one file,
  `RoomScanDialogDjBoothDropped.test.tsx`, 6 tests) and `npx vite build`.
  **Not seen in a browser**: the warning under the stored message.
- **Keeping the DJ booth mark goes only so far** (slices 30 and 31):
  - *Closed by slice 31:* a kind changed by hand no longer loses the mark
    at the next scan. It is kept, mark and kind, where the stored `basis`
    says the kind was set by hand. **What is still dropped:** a marked
    raised area whose kind differs from the reading's and whose `basis`
    does not say "Kind set by hand." (a room written by another client, or
    by hand into the column). Nothing records it as a person's, so it is
    matched on its kind as before.
  - **A kept kind can change the fixture moves.** The moves are suggested
    for the room that would be stored, and the suggestion reads the first
    `stage`. A marked booth the scan reads as its first stage is stored as
    a booth, so it is no longer that stage. One test over HTTP makes the
    test room's stage a booth and holds the preview's moves to be the ones
    apply makes; where the floor lights then go is not asserted.
  - *Closed by slice 32:* a name typed by hand is kept, on the marked
    raised area and on every other, and the mark's sentence uses it ("kept
    on DJ"). A raised area nobody named is still called what its kept kind
    is called ("Booth or counter") where the scan called it what it read
    ("Riser").
  - **A booth moved or resized by hand past half its footprint is
    dropped**: the new reading has it where the scan sees it. So is every
    mark when the room is read a quarter turn round (**Turn the room**):
    nothing stands where it did.
  - *Closed in part by slice 32:* a name, a height and a base height set
    by hand are kept, and so is a raised area added by hand that the scan
    has nothing in the place of. **Still the scan's again:** a width, a
    depth, a heading and a place set by hand (by design: the scan measures
    the footprint). A deleted raised area and an overhead line's or ring's
    name and hanging height were closed by slice 33. See the slice 32 and
    slice 33 lists above.
  - *Closed by slice 31:* the preview now says what will become of the
    mark (`dj_booth_mark`, and one line in the dialog). **It is said of the
    room as stored when the preview was read**: a room edited between the
    preview and Apply is matched again at Apply, as it then stands, and the
    answer says what was done.
  - **After Apply a kept mark is said in the answer and not in the
    dialog** (`dj_booth_message`); after Apply the dialog speaks only of a
    dropped one. Before Apply it says both.
  - **The room's Undo does not go back across a scan applied again**, for
    the mark as for everything else (it never did).
  - **Heights are not compared.** Two raised areas of one kind stacked on
    the same footprint are told apart only by their place in the list.

- **Slice 29's tests have not been run, and nor has the build with it.**
  `npx vitest run` and `npm run build` were refused in the session that
  wrote it; `npx tsc --noEmit -p .` ran, with its 13 older errors and no
  new one. Before relying on it, in `frontend/`: `npx vitest run` (1222
  passed in 59 files before the slice; it adds 13 tests and one file,
  `RoomScanDialogTurn.test.tsx`, and 6 of the 13 are in `roomScan.test.ts`)
  and `npm run build`. The likeliest thing for a first run to find is in
  `RoomScanDialogTurn.test.tsx`: it is the first test to draw the Room Scan
  dialog at all, and it chooses a file through the hidden file input and
  reads the table by its roles. **Not seen in a browser**: how the Turn
  column sits in the table at the dialog's width, where Why is already the
  wide one.
- **The Turn column goes only so far** (slice 29):
  - **It is the number the server gives**, clockwise seen from above. It
    does not say what the fixture's `rotation_y` was or will be, which runs
    the other way round.
  - **Nothing is drawn turned before Apply.** The dialog has no picture of
    the suggestion; the turn is seen in the 3D view once it is applied.
  - **After Apply the count is of the moves listed**, not of what the
    server says it turned: the answer has no such number.
  - **The undo's words do not say a fixture was turned back** (slice 27).
- **Slice 28 has been run but not seen in a browser.** Its tests, the build
  and the type-check pass (Nov 24: vitest 59 files, 1222 passed; `npm run
  build` OK; `npx tsc --noEmit` only the 13 older errors; backend 2562
  passed, 10 skipped, 5 xfailed). The session that wrote it had none of
  the frontend's: it had no `frontend/node_modules` and was refused
  `npm ci`, `npx vitest run` and `node`. Not seen: the DJ and Floor cameras
  on a real room, the DJ camera from behind a side wall or an outline's
  wall, the tag's size over a small booth, and the box in the already wide
  row of Edit Room.
- **The DJ booth mark goes only so far** (slice 28):
  - **Reading the scan again no longer drops it** where the new reading
    has the same raised area standing in the same place (slice 30); it is
    dropped, and the answer and the dialog say so, where it has not. A kind
    set by hand on the marked raised area is kept with it (slice 31), and a
    name and a height set by hand on any raised area (slice 32). A marked
    booth added by hand keeps its mark where it is itself kept. A width, a
    depth, a heading or a place set by hand is still dropped: the scan
    measures those.
  - **A change of kind made through the API without `is_dj_booth` takes the
    mark off.** Edit Room sends it; another client has to.
  - **A marked stage is drawn as a stage** (a desk at its downstage edge,
    half its width) and a marked riser as a booth. There is no saying "a
    counter" or "a desk" apart from the kind and the 0.6 m height.
  - **No box in the Add form or in items mode on the plan**: tick the row
    in Edit Room. The plan's tag is not a button.
  - **The plan's tag does not move off another label**: it is a line above
    its raised area's label wherever that label was nudged to, and the
    label layout does not know it is there.
  - **The Floor camera stands on one line**: straight out from the middle
    of the booth's front. It does not look for the widest part of the
    floor, it does not go round a pillar or a notch (it stops at the first
    wall), and a booth facing a wall under 1.85 m away leaves it where the
    old preset had it, turned to the booth. Its height is the preset's
    2.3 m above the floor even when the booth is on a balcony.
  - **The DJ camera is not kept out of things**: a raised area, a truss leg
    or another arm of the room behind the booth can be where it stands. A
    counter with no DJ drawn has it placed from the gear.
  - **Only those two cameras.** Iso, Front, Audience and Top still frame the
    room's box and the made-up booth's end of it.
  - **A scanned room's crowd changed once** with this slice where the booth
    is not upstage centre: the Floor camera, which the crowd keeps clear
    of, stands somewhere else.

- **Slice 22 has been run but not seen in a browser.** Its tests, the build
  and the type-check pass (see its entry in "What the tests cover"). The
  session that wrote it had none of them: The session had no `frontend/node_modules` and was
  refused `npx vitest run`, `npm run build`, `npm ci`, `tsc` and `node` on
  a script. Before relying on it, in `frontend/`: `npx tsc --noEmit` (13
  older errors are expected, none in `roomItemHeight.ts`,
  `RoomItemHeightStrip.tsx` or `RigBuilder.tsx`), `npx vitest run` and
  `npm run build`. Its test files are `roomItemHeight.test.ts`,
  `RoomItemHeightStrip.test.tsx` and the second `describe` of
  `RigBuilderItems.test.tsx`. Expect a first run to find something: a
  type error is as likely as a failed expectation. Not seen at all: how
  the strip sits beside the plan on a narrow screen (it takes 136 pixels
  and 8 of gap from the plan's width while items mode is on), whether the
  plan and the strip line up when the plan is taller than the strip, the
  handles under a finger, and **the plan's size outside items mode**: the
  plan is now inside a row of its own in every mode, which should leave it
  as wide and as tall as it was and has not been looked at.
- **Heights by dragging go only so far** (slice 22):
  - **Only in items mode on the 2D plan**, for the one selected item. The
    3D view has no height handle, and a row of Edit Room is still where a
    height is typed to the millimetre.
  - **Shift has no touch equivalent but the Step button**, which stays
    pressed until it is pressed again; it is not kept from one visit to
    the mode to the next.
  - **The strip shows one item and nothing else**: not the other raised
    areas or trusses at their heights, not the fixtures on it, and not the
    stage it stands on. A riser's base is not snapped to the top of the
    stage under it: drag it there by the number, or type it.
  - **Nothing follows while it is dragged.** The fixtures and the risers
    standing on it go when the server answers, as for every other handle.
  - **The limits are worked out from the room on screen.** The strip stops
    a handle where the server would refuse the item itself; it does not
    know what a carry would refuse (a fixture taken through the ceiling's
    margin or a riser above the ceiling), which comes back as a 422 and
    puts the handle back.
  - **Top and Base cannot be dragged together**, and there is no dragging
    the base while the top stays: the base carries the whole area. Lower
    the top afterwards.
  - **A room with no ceiling stored** is shown to a metre over the item;
    a handle dragged past the top of the strip goes on rising by the
    number while it is drawn at the top, until it is let go.
  - **Escape does not cancel a drag** in the strip; bring the handle back,
    or use Undo. The arrow keys do not change a height. **The plan's keys
    do not know a handle of the strip is held**: Escape pressed during a
    drag lets go of the item on the plan and the height is still sent when
    the handle is let go, and an arrow key nudges the item under the drag.
  - **A refusal is said in the strip over the plan**, not beside the
    handle.
  - **The readout is the height above the floor** for all three handles.
    A raised area's row shows its Height as the deck above its base, so a
    floating platform's Top reads differently in the two places (3.00 in
    the strip, 0.3 in the row).

- **The frontend tests of slices 19, 20 and 21 have not been run, and nor
  has the build.** `npx vitest --run`, `npm test` and `npm run build` were
  refused in the sessions that wrote them; `npx tsc --noEmit` ran for
  slices 19 and 20, with its 13 older errors and no new one, and slice
  21's commit says its tests were type-checked too. Run
  both in `frontend/` before relying on any of them. Slice 21 wrote
  `raisedAreaHeading.test.ts` and added to `RoomShellRaisedDialog.test.tsx`,
  `StageView2DItems.test.tsx`, `RigBuilderItems.test.tsx` and
  `roomItemDrag2d.test.ts`. Slice 19's test files are
  `roomItemDrag2d.test.ts`, `StageView2DItems.test.tsx` and
  `RigBuilderItems.test.tsx`; slice 20 added to all three, changed two
  older assertions in them on purpose (a raised area now has handles), and
  wrote `RoomShellStackDialog.test.tsx` and added a key to one expectation
  in `roomShellAdjust.test.ts`. Expect a first run to find something: none
  of the frontend tests of the three slices has ever been executed. Slice 20's backend tests were run (1990 passed).
  **Nothing of these slices has been seen in a browser**: how wide a truss
  is to press, whether the handles are easy to hit at the plan's usual
  size, nine handles round a small riser, how the strip reads with
  its box in it, and a turned raised area in the plan and in the 3D view
  (that both turn it the same way round is tested on the numbers only).
- **A raised area at a heading goes only so far** (slice 21):
  - **A scan finds one only where it is plain** (slice 27): turned 5
    degrees or more, and a rectangle. A heading set by hand is still
    replaced when the scan is read again, by the scan's own or by none.
  - **A scan's suggestion reads the first stage's heading** (slice 27),
    and no other raised area's: see the next item.
  - **The 2D plan's labels go by the square box.** The 3D drag snaps to
    the turned edges (`snapLines`); the 2D drag snaps to no raised area's
    edge, turned or not, and the label layout does not know the area is
    turned.
  - **A heading has no front.** 30 and 210 are the same raised area, and
    what stands on it is swung the shorter way, never more than a quarter
    turn at a time. To face a stage the other way, turn its fixtures.
  - **A turn does not respace anything**: fixtures and risers keep their
    place on the deck, and trusses over it do not follow.
- **A suggestion for a turned stage goes only so far** (slice 27):
  - **No turned stage from a real phone has been read.** Every one was
    built in the tests, with clean edges. A real scan's stage has gear on
    it, a ragged edge and steps beside it, and the three gates (5 degrees,
    0.9, 0.8) were chosen on built rooms. Expect the first real one to be
    read square when it is turned, which is the old behaviour, more often
    than turned when it is square. Keep the scan either way.
  - **An ungrouped row moved while the stage stood square is not kept whole once the stage is turned by hand without its box ticked.** Ungrouped fixtures a scan has moved are a row by their depth on the turned stage (within 0.05 m of the next); ones still lying along the room are read a fixture at a time. Give the row a group.
  - **A row an earlier scan moved is not swung by a later one.** A rig
    scanned when the stage stood square (or by a version before this one)
    has the scan's hint on its rows, and a hinted row is read as already
    turned. It is then fitted to the turned stage as though it lay along
    it, which it does not. Undo the room scan moves first, then read the
    scan again. The same holds the other way: a row laid on a turned stage
    is not swung back by a scan that finds the stage square.
  - **A different heading the second time does not re-turn.** A laid row
    is un-swung by the new heading, fitted and put back, so a scan that
    reads 31 degrees after 30 shifts it at most to keep it on the deck and
    never turns it the extra degree.
  - **A heading has no front here either.** The front is taken as the edge
    that faces most nearly downstage: the scan stores a heading within 45
    degrees of square, and one set by hand is within 90. A stage that
    really faces a side wall or upstage has its rows laid facing the wrong
    edge; turn the room in quarter turns, or the fixtures by hand.
  - **Only floor rows, and only the first stage.** Rows on a riser or a
    booth are not suggested onto it, turned or square, as before. Overhead
    rows do not follow a turned stage: a truss over it is found as its own
    line at its own heading, and a row goes along that.
  - **Only the plan is turned.** `rotation_y` loses the heading; tilt
    (`rotation_x`) and roll are left, and a moving head's pan and tilt
    limits or home are not looked at.
  - **A row in the hold of both the stage and a wall settles in one or two
    passes, not to the best place.** Where the stage's edge and the wall
    cannot both be kept, the walls win and the row may stand off the deck.
  - **Which wall is upstage is still decided by the box round the stage**
    along the room's axes, and a turned stage is not snapped to a wall it
    nearly touches. A stage across a corner at 45 degrees is as near two
    walls as each other: the first of the two in the old order wins.
  - **The undo record grew two keys** (`rotation_y_before`,
    `rotation_y_after`) for turned fixtures only. The undo's answer still
    lists positions and does not say a fixture was turned back.
- **A stack of raised areas follows only so far** (slice 20):
  - **"Standing on it" is by place, not by a link.** The middle of the
    footprint inside the other's, and the base within 0.1 m of its top. A
    riser whose middle overhangs the stage's edge stays behind, and so does
    one added on the floor (base 0) inside a stage's footprint: give it the
    stage's top as its base first. A platform that happens to float at a
    stage's top over it is carried though nothing joins them.
  - **A resize alone carries no raised area**, while the fixtures standing
    on the resized area keep their share of it. A stage made narrower can
    leave a riser overhanging it, or its lights closed up round a riser
    that did not move.
  - **Deleting a raised area leaves what stands on it in the air**, areas
    and fixtures both.
  - **A change of the lower area's kind, or its name, carries nothing**, as
    for fixtures.
  - **A carried area cannot be left behind on its own.** The box is one
    for the fixtures and the stack together (`carry_fixtures`): there is no
    carrying the lights and leaving the riser.
  - **A carried area already above the ceiling, or past the margin, blocks
    every carry**, as a fixture already outside does: the refusal looks at
    where it would end up, not at whether it got worse.
  - **A stack is not shown before it goes.** While a stage is dragged on
    the plan, only the stage's outline follows the pointer; the riser on it
    is drawn where it was until the server answers.
  - **What was typed in a carried area's row and not saved is let go**
    when it is carried, its name included: the row held its old place, and
    saving it would have sent the area back. Type it again.
  - **The undo's answer does not list the areas put back**, only the
    fixtures: the room it answers with has them where they were.
  - **Trusses do not follow a raised area.** A truss on legs standing on a
    stage is moved by hand.
- **Arranging items on the plan goes only so far** (slices 19 and 20):
  - **A raised area's handles resize it about its middle** (slice 20).
    There is no dragging one edge while the other stays put: resize it,
    then move it. Its quarter turn is still the Turn button on its row;
    its rotate handle sets its heading (slice 21).
  - **A corner dragged until the two sides have changed places is a
    quarter turn to the server**, which reads a turn from the sizes alone:
    a 6 by 3 stage dragged to exactly 3 by 6 has its fixtures and the
    risers on it swung, not kept at their share. One grid step off, it is
    a resize.
  - **Nine handles cover a small riser** (eight to resize it and one to
    turn it). Each of the eight is 0.24 m across; on a
    raised area under about 0.6 m a side there is little of it left to
    press between them. Let go of it (Escape) and press it again to move
    it, or type its place in its row.
  - **A side goes to the grid's step, so an edge does not land on a grid
    line** unless the middle is on one.
  - **A length changes about the middle.** There is no dragging one end
    while the other stays put; move the line afterwards.
  - **A height is not set on the plan itself**, which has none: it is set
    in the height strip beside it (slice 22), or in a row.
  - **A drag does not snap to anything but the grid**: not to a wall, to
    another item's edge, or to the fixtures. A length and a radius go to
    the grid's step, so an end does not land on a grid line unless the
    middle is on one.
  - **A heading goes to 5 degrees**, or to a tenth with the snap off or Alt
    held, or to 15 with Shift (slice 21), for a line and for a raised area.
    Nothing snaps it to square with a wall that is not square to the room,
    and Shift has no touch equivalent.
  - **One request for each key press.** A held key does not repeat, and ten
    quick presses are ten requests and ten undo steps (the room keeps 20).
  - **No nudge pad.** The arrow keys have no buttons on a touch screen in
    this mode; an item is dragged with a finger, and not nudged.
  - **A refused change is not explained on the item**, only in the strip.
  - **The item is drawn twice during a drag**: its outline where the drag
    has it and the item where it still is. Its label and its fixtures stay
    where they are until the server answers.
  - **Going back to Edit Room starts its boxes ticked again**, as opening
    the dialog always does: a box unticked in the strip is not carried
    back.
  - **Only one item at a time.** There is no selecting two. A raised area
    does take the risers standing on it (slice 20).
  - **Overlapping items**: the one drawn last takes the press (rings over
    lines over raised areas, later in a list over earlier). A ring is
    pressed on its truss, not inside it.
- **Checks ran after slice 18**: backend pytest 1951 passed, frontend
  vitest 943 passed, and the build passed. That frontend run takes in the
  test files of slices 15, 16 and 17, which were written in sessions that
  could not run vitest. **Nothing of slices 15 to 18 has been
  seen in a browser**: a raised area's row is now wider still (a kind
  selector, a base height field and the box), and the plan and the 3D view
  redraw under the open dialog.
- **Fixtures follow a raised area only so far** (slice 18):
  - **"Standing on it" is by distance, not by a link.** A light on a stand
    more than 0.6 m above the deck stays behind, and so does one clamped
    under a floating platform. One beside the area, within 0.15 m of its
    edge, goes along when its own height is in that window (a light on a
    stand next to a low riser); one on the floor there, more than 0.05 m
    under the top, does not. Untick the box, or use Undo, when the reach
    guesses wrong.
  - **A fixture within reach of any truss is never carried by a raised
    area**, even a floor light that happens to stand within 0.3 m and
    0.6 m of a low truss.
  - **A raised area also carries the raised areas standing on it** since
    slice 20, with the lights on them; the limits of that are above.
  - **A quarter turn is always clockwise, and is read from the sizes.**
    Two turns leave the area as it was and its fixtures swapped end for
    end, facing the other way. Width and depth typed the other way round
    are a turn, whatever else is saved with them; a width or depth that
    is not the exact swap is a resize, not a turn; a square area has no
    turn.
  - **A resize spreads the fixtures out or closes them up**, by share of
    the footprint. To keep a row's spacing on a bigger stage, untick the
    box.
  - **A deleted raised area leaves its fixtures in the air**, at the height
    its top was.
  - **A change of kind moves nothing and re-suggests nothing.** The only
    suggestion is made when a scan is read, from that scan's own room, in
    which every raised area is the scan's guess and stands on the floor. A
    kind set by hand is replaced when the scan is read again unless it is
    on the marked DJ booth (slice 31); a base height set by hand is kept
    since slice 32, and the suggestion is made for the room with it, but
    no test over HTTP holds where the floor lights then go: a
    suggestion going by a stage set by hand, and its lift to a floating
    stage's top, are tested on the function alone.
  - **A base height is the whole of a level.** A balcony is a box with a
    top: no rail, no stairs, no sloped or stepped deck, and a scan still
    finds none of them. Whether a 3D drag or a 2D snap lands a fixture on
    a floating deck has not been checked.
  - **The limits of slice 17 below hold here too**: the room's box and
    not its walls, a fixture already outside blocking every carry, the
    editor's own Undo steps dropped, only `rotation_y` turned, and a
    carried fixture left alone by "Undo room scan moves".
- **Fixtures follow a truss only so far** (slice 17):
  - **Only from Edit Room's rows and its items mode on the plan** (slice
    19). A deleted truss leaves its fixtures where they hung, and a moved
    wall carries nothing.
  - **"Hung on it" is by distance, not by a link.** Nothing records which
    truss a fixture belongs to: one within 0.3 m and 0.6 m of it goes, a
    floor light that happens to stand that close under a low truss goes
    too, and one hung on a drop further below the truss does not. Untick
    the box, or use Undo, when the reach guesses wrong.
  - **A turn is never more than a quarter turn.** A line has no front, so
    turning one to 180 degrees is no turn and its fixtures stay put; to
    swap a row end for end, lay it again.
  - **A carried fixture is no longer where the scan put it**, so "Undo room
    scan moves" leaves it alone afterwards. Its tags are not changed: a
    guess stays a guess though it has been moved by hand, in a way.
  - **The undo leaves a fixture moved since**, by more than 5 mm; one
    nudged and nudged back is put back. A fixture whose heading alone was
    changed since is put back, heading included.
  - **The room's box, not its walls, is the limit**, as for the truss
    itself: in an L-shaped room a truss and its fixtures can be carried
    into the notch, where the Walls section then lists them as outside.
  - **A fixture already outside the limit blocks every carry on its
    truss**, even a change of height or a move back towards the room: the
    refusal looks at where each fixture would end up, not at whether it got
    worse. Untick the box, change the truss, and place that fixture by hand.
  - **The limit is the scanned room's box**, not the larger of the room and
    the stage that a dragged fixture is held to
    (`fixture_position.position_limits`). On a rig whose stage is drawn
    wider than its scanned room the two differ.
  - **The editor's own Undo steps are dropped** when fixtures were carried,
    like after a scan is applied: a drag made before the truss was moved
    cannot be undone afterwards.
  - **Only `rotation_y` turns.** A fixture with a tilt or roll stored keeps
    them, which is right for a hanging light and may not be for one mounted
    on its side.
- **Slices 15 and 16 have not been seen in a browser.** Their frontend
  tests and the build were not run when they were written; they passed in
  the run after slice 18, above. Nothing of either slice has been seen in
  a browser:
  the dialog is now wide and long (seven columns, a table of corners and a
  form), and how it sits on a small screen is unknown; nor have the corner
  handles, how they sit over a fixture at a corner, or the strip over the
  plan. The backend suite was run after slice 16: 1865 passed, 10 skipped,
  5 xfailed (1794 before it).

- **Checks ran on 2026-11-22, 7:44 PM ET, after slice 8 (outline-held guesses, 2D truss snap, room grid, palette click):** frontend vitest 424 passed (22 files) and the build passed; backend pytest tests/ 1632 passed, 10 skipped, 5 xfailed, including tests/integration/test_api_room_scan.py.
- **Slices 9 to 12 have had their tests run, and they pass**: frontend
  vitest 654 after slice 12, and the build. No backend file changed in any
  of them, so the backend run above stands. None of them has been seen in
  a browser: the readout, the selection box's look, whether a box drag
  selects text elsewhere on the page, the keys with the focus left on a
  toolbar button, and the nudge pad under a finger.
- **The editor's wiring for a row drag, Lay on truss and Redo is tested**
  by `RigBuilderRowLay.test.tsx`, as a drag, a nudge and a row nudge are by
  `RigBuilderSelectKeys.test.tsx`: each is one batch-update and one undo
  step. The Select row button, a height changed by a drag's snap and then
  undone, and the properties panel put away for several selected are still
  type-checked only.
- **A held arrow key moves one step.** Auto-repeat is ignored so that one
  press is one undo step and one request. There is no finer step than the
  grid's: for less, drag with the snap mode set to Free, or type the
  position in the properties panel.
- **A nudge does not snap.** It never puts a fixture on the grid or on a
  truss and never changes a height, so an off-grid guess nudged stays
  off-grid by the same amount. Quick presses each send their own
  batch-update, a few milliseconds apart.
- **A fixture outside the walls is not held by a nudge** until a nudge has
  brought it inside, as in a row drag; a single fixture *dragged* from
  outside comes to the wall at once. The two differ.
- **A selection box goes by marker centres and by the box alone.** It does
  not take in a fixture whose icon it only touches, cannot be dragged
  beyond the plan's edge (it ends there with what it held), and has no way
  to take fixtures *out* of a selection; Shift-click does that.
- **The keys need the focus off a field.** After typing the rig's name or
  choosing a snap mode, the focus stays there and the plan ignores keys
  until the plan is clicked. Since slice 12 a line on the plan says so, and
  the nudge pad gives a finger the arrows, Select row and Lay on truss.
- **The 2D room layer has not been seen in a browser**: label sizes and
  nudges in a crowded room, a turned label, the tooltips, where UPSTAGE,
  AUDIENCE and the scale bar land round a real room, a drag and a palette
  drop out in the room with the view grown, a drag snapping to a truss line
  and a ring, the grid across an L-shaped floor, and where a palette click
  lands. Nor has slice 9: the readout's size and whether it prints over a
  fixture's name or the truss's own label, a row dragged along a wall and
  into the notch of an L, a double-click selecting a row, and Ctrl-click on
  a Mac, where the browser may open its menu instead.
- **A drag carries a row, never turns or respaces it.** It snaps onto a truss
  with the fixture under the pointer only, so a row that does not lie along
  the truss has one fixture on it, and a row longer than the truss overhangs
  its ends; those fixtures keep their old height while the rest take the
  truss's, which the readout's count ("3 of 4 on ...") is there to show.
  Lay on truss is what respaces a row.
- **Lay on truss chooses the truss itself**: the nearest to the middle of
  the selection, however far that is. To lay a row on another truss, carry
  it near that one first. Nothing on the plan shows the laid places before
  the press; the tooltip names the truss and Undo takes it back.
- **Lay on truss fills the whole truss.** Spacing is the truss's length
  over the count: there is no keeping a row's own spacing, no setting one,
  and no laying along part of a truss or part of a ring. A line straight
  across the room is filled the same way, where a scan's suggestion would
  slide the row under it as one piece.
- **Lay on truss goes by the selection alone.** A group's unselected
  fixtures keep no place in the count (a scan's suggestion gives them one),
  so laying half a group puts it over the other half's places. Select the
  whole row first.
- **A truss partly outside the walls takes no row** that would have a place
  beyond them, though most of it is inside. Lay fewer fixtures, or carry
  the row there by hand.
- **A row is held by its nearest walls, one fixture at a time.** That is
  exact against the straight walls of a box and of an L. Where two members
  are pushed opposite ways (a row wider than the room is across, or wedged
  across a narrow arm) the row stays where it was and does not slide. A
  member that starts outside the walls is not held until it is inside, so
  such a row can also be carried further out.
- **Rows are found by simple rules.** Height and depth are rounded to 0.1 m,
  so two fixtures 2 cm apart either side of a rounding step are not one
  row. A fixture hanging near two scanned trusses belongs to the first the
  scan listed. A grouped fixture's row is its group even when the group is
  spread over the room. Fix a wrong row with Shift-click.
- **Modifier keys have no touch equivalent**, so on a tablet a row is
  selected with the button or a double-tap, if the browser sends one, and
  a box cannot add to a selection. The plan listens for mouse events: a
  finger may not draw a box at all.
- **Shift-press on a selected fixture no longer drags it.** It takes the
  fixture out of the selection and carries nothing; it used to deselect it
  and drag it all the same.
- **The readout names scanned truss only.** A snap to the grid or to the
  plan's own purple truss lines says nothing, and the truss snapped to is
  not highlighted.
- **A row moved in 2D is "moved since the scan".** Like any 2D move, it
  takes those fixtures out of what "Undo room scan moves" will put back.
- **The 2D snap takes hold as soon as a press is a drag.** Since slice 11
  that is 5 screen pixels, as in the 3D view, so a wobble no longer moves a
  fixture or a row. Past it, a fixture next to a truss goes onto it and an
  off-grid guess goes to the grid, as before. Five pixels is on the screen:
  in a large room drawn small it is more of the floor. Alt has no touch
  equivalent.
- **An undone height can be an old one.** An undo step keeps the height a
  fixture had before the drag snapped it onto truss. If that height is then
  changed in the properties panel, undoing the drag puts the older one back.
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
- **One fixture at a time in the 3D view.** No multi-select and no dragging a
  whole row there (the 2D view has both), and no rotating a fixture.
- **One undo, all the way back.** The record gathers the moves of every scan
  applied since the last undo, so an undo puts a fixture back where it stood
  before the first of them; one scan out of several cannot be undone on its
  own. The record is spent by an undo whether or not anything was skipped, and
  an undo cannot itself be undone. A 3D drag has no undo either: drag it back.
  (The 2D editor's own Undo is separate and steps back one drag at a time,
  a row move included.)
- **Dropping a fixture may move the camera.** Every drop lays the venue out
  again; if the room grows for a fixture put beyond a wall, the camera preset
  may be re-applied. Not checked on screen.
- **Snap targets are the scan's own lines.** The view's drawn truss rows for a
  rig with no scanned room are not snap targets, and there is no grid snap.
- **A real scan.** Polycam, Scaniverse and RoomPlan exports from a real venue
  have not been read. Expect the thresholds in `extract.py` to need tuning.
- **Binary USDZ** (`.usdc`) is read (slice 24), but only so far:
  - **No file from a real phone has been through it.** Every file it has
    read was written by Pixar's USD library from a room made in code. The
    first RoomPlan, Polycam or Scaniverse USDZ is a test of the reader. If
    it is refused or the room is wrong, export OBJ, and keep the USDZ: it
    is the fixture this needs.
  - **One layer.** A USDZ whose root layer brings its geometry in from
    another layer (references, payloads, sublayers) is not put together:
    the first layer that holds mesh points is read on its own, without the
    transforms the layer above gave it, and the report says the USDZ held
    more than one. Variants are not read either.
  - **No instances.** A mesh drawn many times from one prototype is read
    once, where the prototype is, or not at all.
  - **No animation.** A value with only time samples is read at its first
    sample (checked against a Pixar-written file, `variety.usdc`).
  - **No GeomSubsets, materials, normals or texture coordinates.** Only
    points and faces are read, so a scan's floor cannot be told from its
    walls by what the app called them.
  - **RoomPlan's categories are lost.** Read from binary USD, a RoomPlan
    room is a mesh like any other: walls and objects are not named, as
    they are from RoomPlan's JSON.
  - **The dialog's change is unrun.** The file picker offers `.usdc` and
    the wording says binary USD is read, but the frontend tests and build
    were not run where that was written: run `npx vitest run` and
    `npm run build` in `frontend/`. A bare `.usd` is not in the picker's
    list, though the server reads a binary layer under that name.
  - **Not run against a Pixar-written file**: crate versions 0.4 to 0.6,
    arrays of floats packed as whole numbers or as a lookup table, packed
    64-bit arrays, LZ4 in more than one chunk, half quaternions, and a
    matrix held in place of its offset that is not the identity (a plain
    scale). Their tests are bytes laid out by hand from the format's
    description. Of the three-axis rotates, binary files with `rotateXYZ`
    and `rotateZYX` are checked against Pixar's numbers; the other four
    orders are checked in text layers against sums done in the test, and
    go through the same code. Pixar's two hold a turn about one axis and
    about two (Y then X); a turn about all three at once rests on the
    sums in the test. Tested by nothing: `!resetXformStack!`, and
    reading points from prims that are not typed `Mesh` when no `Mesh`
    has any. Now checked against Pixar (`variety.usdc`): points as halves
    and doubles, a double orient, an identity matrix held in place,
    time samples, and leaving out `over`, `class` and inactive prims.
    Crate versions before 0.4.0 and any 1.x are refused. A 0.x later
    than 0.12 is read, with a note in the report.
  - **Slow on a very large packed file.** LZ4 is undone in Python. Points
    are not packed, so a phone scan's bulk reads at once, but its face
    indexes are. Measured on made-up data, not a real scan: 3 million
    indexes out of the integer coding in 0.1 s, and LZ4 at its worst (a
    million short runs in 6 MB) in 0.6 s. A real file falls between; a
    file built to be slow could take most of a minute at the 200 MB upload
    limit. The most read is 60 million entries in one array (20
    million triangles).
- **glTF** (slice 25) is read, with these left:
  - **No real export has been read.** Every `.glb` and `.gltf` the reader has
    seen was written by the tests. Whether Polycam's and Scaniverse's default
    GLB exports use Draco has not been checked against the apps: if they do,
    the upload is refused with the message naming the fix, and the operator
    has to find the app's switch or export OBJ.
  - **Draco, meshopt and quantised positions** are refused, not unpacked. A
    Draco decoder in pure Python would be a slice of its own.
  - **A `.gltf` with a separate `.bin`** is read from a zip of the two
    (slice 26). Sent on its own it is still refused, and the message says to
    send the zip. Choosing the `.gltf` and the `.bin` as two files in the
    dialog is not built: the upload takes one file.
  - **Sparse accessors** are refused. **Points and lines** are read only
    when the file has no triangles, and without their normals (a PLY point
    cloud's normals are read).
  - **Only the default scene** is read, and no skin, morph target, animation
    or GPU instancing extension (`EXT_mesh_gpu_instancing`) is applied.
  - **The dialog** accepts `.glb` and `.gltf` in its file picker and words
    them in its help text; that change has not been run or seen in a browser
    (see "What slice 25 built").
- **A scan in a zip** (slice 26) is read, with these left:
  - **No real zip has been read.** Every one was built by the tests with
    Python's `zipfile`. What Polycam and Scaniverse put in theirs (the
    folder layout, how a `uri` is spelled, whether they add a model in a
    second format) has not been checked against the apps. Keep the first
    real zip that is refused or read wrongly: it is the fixture this needs.
  - **The frontend change is unrun** (see "What slice 26 built"): run
    `npx vitest run`, `npx tsc --noEmit` and `npx vite build` in
    `frontend/`.
  - **One model.** A scan split over several models (tiles of a large
    photogrammetry export, one `.obj` a room) is not put together: one is
    read and the rest are named as left alone.
  - **The size limit counts the textures.** A zip whose files add up to more
    than 200 MB unpacked is refused even when the model alone is small,
    because the limit is on what the zip says it holds. An OBJ is text and
    packs small, so a zip well under 200 MB can hold an OBJ that is over.
    Export at a lower detail, or zip the model without its textures.
  - **A USDZ inside a zip** is unpacked by the USDZ reader under its own,
    older limit (400 MB unpacked), not the zip's.
  - **A USDZ renamed `.zip`** is read by the zip's rules, not the USDZ
    reader's: binary layers before text ones, and RoomPlan JSON last, where
    the USDZ reader takes RoomPlan JSON first.
  - **Any `.json` holding the word `"walls"` is taken for a model**, RoomPlan's
    or not. It is tried last, so it costs nothing beside a real model; when
    it is the only one in the zip, the refusal is the RoomPlan reader's and
    not "the zip holds no scan".
  - **A `uri` with a query or a fragment** (`scene.bin?v=2`) is looked up
    as a file of that whole name, and not found.
  - **Two files with one name** in a zip: the first is the one read.
  - **Zips in several parts, and compressions other than store and
    deflate** that this Python was not built with (deflate64 never is) are
    refused, in words.
  - **The dialog takes one file.** A `.gltf` and its `.bin` cannot be
    chosen together; they have to be zipped.
- **Ceilings and levels.** Sloped or domed ceilings, balconies and mezzanines
  are still read as a flat ceiling over one floor. A balcony can be put in
  by hand as a raised area with a base height (slice 18).
- **Editing the walls goes only so far** (slice 16):
  - **Nothing follows a wall.** A fixture, raised area, truss or ring the
    new walls leave outside is listed and left where it is. There is no
    "bring them inside" button: move each by hand, or undo the wall.
  - **The list is a warning, not a lock.** Walls can be saved with things
    outside them, and nothing stops a show running that way. A fixture a
    scan left up to 2 m beyond a wall on purpose is listed like any other.
  - **The middle of the floor does not move**, so a room drawn out to one
    side is no longer centred on the origin, and its stored `width` and
    `depth` are wider than its walls. The dialog shows the walls' own
    size. The 2D plan's tooltip and the scan summary still show the box.
  - **A wall is at least 0.1 m, not 0.5 m**, and at most 200 m. A scan
    merges runs under 0.4 m and can then shorten a wall further when it
    fits the corners (`find_outline`), so it can store a wall under 0.5 m;
    a least length of 0.5 m would refuse every later edit to such a room
    for a wall nobody touched. Raise `WALL_MIN_M` if that is not wanted.
  - **A corner goes only as far as the plan's edge in one drag.** The plan
    shows a metre round the room; drag again once it has redrawn, or type
    the place in the dialog.
  - **Corners are numbered, not named**, and a corner added or deleted
    renumbers the ones after it. Walls turned inside out by a move are
    numbered clockwise again from the same first corner.
  - **A drag moves one corner.** There is no dragging a whole wall, no
    adding a corner by clicking a wall on the plan (use Add after in the
    dialog, then drag it), no typing while in walls mode, and a corner
    snaps to the grid only: not to another corner, to square, or to a
    scanned truss. Escape does not cancel a drag; Undo takes it back.
  - **Walls mode is the 2D plan's.** The 3D view draws the new walls and
    has no handles.
  - **One outline, no holes, straight walls, one height**, as before: a
    pillar, a curved wall and a sloped ceiling cannot be drawn by hand
    either.
  - **Hanging heights are not recounted against new walls.** A truss the
    walls now cut through is listed as outside and still counted in its
    band, so a scan's suggestion can still hang a row along it.
  - **What is outside is worked out by the server alone**, when the dialog
    opens and after each change to the room. A fixture dragged outside the
    walls in the 3D view while the dialog is open is not listed until then.
- **Editing the room goes only so far.** A raised area, line or ring can be
  renamed, moved, resized, raised or lowered and deleted, a line can be
  turned, and any of them can be added (Edit Room, slice 15); a raised area
  can be made another kind and floated on a base height (slice 18). What is
  left:
  - **A raised area can stand at any heading** since slice 21; the limits
    of that are above.
  - **Only the first `stage` in the list** is what a scan's suggestion puts
    floor lights along, and a raised area cannot be moved up or down its
    list: a kind change keeps its place.
  - **A ring cannot be made an arc.**
  - **Items are dragged on the plan only so far** (slice 19): any of them
    can be moved there, a line's length and heading, a ring's radius and a
    raised area's sides (slice 20) and heading (slice 21) have handles, and
    the arrow keys nudge.
    A height and a base height are dragged in the strip beside the plan
    (slice 22). See the limits of slices 19, 20 and 22 above.
  - **Everything is held to the room's box and 2 m round it, not to the
    floor outline**, so in an L-shaped room an item can be put in the notch.
  - **A plain move holds the middle only; a resize holds the whole item.**
    So an item can be moved until half of it is past the margin, and the
    next change to its size brings it back in.
  - **A band's height is not recalculated** when the lowest truss in it is
    raised to another band: it still starts where the scan found it, though
    what is left in it hangs a little higher (within the band's own
    thickness). A new band started by hand is as deep as the truss.
  - **Undo goes back, not forward**: there is no redo, an undo cannot be
    undone, only the last 20 edits are kept, and reading the scan again or
    removing the room clears them all. It is the room's own undo, in the
    dialog: the editor's Undo button and Ctrl-Z do not reach it.
  - **Every room edit is refused while a locate walkthrough runs**, even a
    rename. That is stricter than the scan routes, on purpose.
  - **Fixtures follow a line or ring** that is moved, raised, turned or
    resized (slice 17), **and a raised area** (slice 18), **and a raised
    area follows the one it stands on** (slice 20); the limits of each are
    above. Nothing follows a wall.
- **Crowd and booth in a scanned room** are fitted to it (slice 23). What that
  leaves:
  - **It has not been seen in a browser.** Its tests, the type-check and the
    build pass (see its entry in "What the tests cover"), and nobody has
    looked at the view: a booth on a real scan, a booth on a turned raised
    area sitting square on the box drawn under it, the amber mark, or the
    crowd round a turned stage.
  - **Which booth, unless one is marked.** With nobody having ticked "DJ
    booth" on a row of Edit Room (slice 28), the first raised area of kind
    `booth` still gets the desk, and a scan calls a bar counter a booth too:
    where the bar comes first the decks are on the bar until the right one
    is marked. The plan's tag shows which one it is.
  - **A counter against a wall has no DJ**, and neither has a platform under
    0.95 m deep or a counter over 1.3 m high: there is nowhere to draw one
    standing. A scan that took the DJ's standing room into the box gives this.
  - **The desk does not fit itself to what is on the stage.** A guessed booth
    is at the middle of the stage's front edge even where a riser stands
    there; only the DJ is left out then. A desk is never narrower than 1.3 m,
    so it overhangs a platform narrower than that.
  - **One of four ways.** A booth faces the way a side of its raised area
    does: along X or Z on one square to the room, along its own width or
    depth on one at a heading. It does not turn to a wall that runs at an
    angle, or to the floor, any further than its raised area is turned. That
    turn is one set by hand, or one a scan measured (slice 27).
  - **No dance floor is drawn** in a scanned room: the crowd stands on the
    plain floor. No speaker stacks either.
  - **Raised areas are all obstacles**, whatever their base: nobody stands
    under a balcony added as a floating platform, or on a stage.
  - **Edit Room does not say a booth is a guess.** The 2D plan's tag does
    ("DJ?", slice 28) and so does the 3D view's amber mark; in Edit Room the
    box is simply unticked on every row until somebody ticks one.
  - **A big edit moves everybody**: the crowd is seeded from the room, so
    any change to the floor or a raised area is a new crowd, not the old one
    stepping aside.
- **A real video through a real COLMAP.** Never run. Expect to adjust the
  COLMAP commands in `video.py` (option names differ between COLMAP versions;
  as few as possible are passed), and the frame thresholds. On Windows COLMAP
  is taken to ship as `COLMAP.bat` beside `bin/colmap.exe`; that layout was not
  checked against a download.
- **Dense clouds**: the COLMAP stereo and OpenMVS commands are the least
  certain part and have no test beyond "a failure falls back to sparse".
- **Up from a video with no rotation recorded.** If the phone was held
  sideways and the video does not say so (some editing and messaging apps strip
  it), "image down" is not down, the up search starts 90 degrees out and the
  room comes out on its side. The preview's Up axis setting does **not** fix
  this in general: the error is not a swap of Y and Z. Send the video straight
  from the phone, or film again.
- **How sparse is too sparse.** Synthetic clouds of 600 to 5,000 points, 3 cm
  of noise, 3% strays and as little as a tenth of the points on the floor and
  ceiling read correctly. A real room with a bare floor may give fewer than
  that there; then the floor is taken from the lowest points, with a warning.
- **Refusals made before the upload is read** (400, 404, and 413 from
  `Content-Length`) may reach a browser as a dropped connection rather than
  their message if it is part-way through a large upload. The dialog checks
  the name and size itself first; `unavailable` and 409 read the upload and
  drop it before answering.
- **Progress inside a step.** The bar moves a stage at a time; COLMAP's mapper,
  the slow one, shows as one long stage.
- **Jobs do not survive a restart**, and closing the dialog stops the job
  (the button says so; a click outside or Escape does not close it while a
  video is being worked on).
- **Measurements** are the ceiling height or the longest wall only; there is no
  picking two points in the cloud.
