# Built-in 3D preview

The 3D view (`frontend/src/components/rig/RigVisualizer.tsx`, the Visualizer
page and `/rigs/:id/visualizer`) draws the rig in its room and shows the light
the engine is outputting. It is read-only: it never sends a DMX value.

## What is built

**The picture is drawn from the output, and from nothing else.**
The socket's `lighting.dmx_frames` are the frames the engine hands to the DMX
callback, with the grand master and the blackout already applied, plus an
`output` block (`master`, `blackout`, `on_wire`). `GET /api/dmx/output-frames`
returns the same. `previs/outputFeed.ts` keeps the latest frames in a plain
object that the render loop reads; it is not React state, so a frame arriving
re-renders nothing. The header says in one line what the picture is drawn from:
*On the wire*, *Preview only* (demo rig held off the wire, or a fixture check
has the output), *Blackout*, *Output lost* (no frame for two seconds) or *No
output yet*.

**Profile and DMX values to beam state** (`previs/beamState.ts`).
One pure function reads a fixture's own channels out of its universe's frame:
dimmer, RGB/CMY/extra emitters, colour wheel slot where the profile names its
ranges, shutter and strobe, zoom, and pan/tilt in degrees from centre (16-bit
where the profile has fine channels). Pan and tilt invert are applied here,
from the fixture's `pan_invert` / `tilt_invert` tags (the older `is_inverted`
flag flips pan). A closed
shutter, a zero dimmer and a blackout are all dark. With no frame the fixture
is dark and its head at centre.

**Fixtures with their rotations.**
`rotation_y` turns the whole fixture about the room's vertical. `rotation_x`
and `rotation_z` (hung on its side, leaning) turn the yoke, head and beam
together inside that yaw. `hangBeam` in `previs/beamThrow.ts` applies the same
turns to the beam's direction, so where the beam is drawn to land agrees with
the model. A rotation the rig gives outright wins over the view's own guess
that a floor-standing fixed fixture faces up.

**The room shell** (`previs/roomShell.ts`, `previs/RoomShellView.tsx`).
Where a rig carries `room_shell` (today the LIV approximate demo preset), the
view draws its dome, round dance floor, balcony, rear stage riser and LED
walls, in place of the generic flat ceiling and square dance floor. All of it
is built in code from the shell's numbers. A rig with no shell gets the generic
club room as before.

**Markers for unconfirmed positions** (`previs/GuessMarkers.tsx`).
A fixture tagged `position_unconfirmed` (laid out on a template, not yet tapped
in place: see `FLASH_AND_TAP.md`) gets an amber ring, a marker above it and a
dashed line to the floor. The header counts them. One merged geometry, one
draw call.

**Move fixtures** (`previs/FixtureDragLayer.tsx`, `previs/fixtureDrag.ts`).
For a rig stored in the database, the *Move fixtures* button in the header
puts a grab handle on every fixture. Press one to select it, drag it along the
floor plan at its height, Shift-drag for height, or nudge the selected one
with the arrow and Page Up/Down keys. With a scanned room a drag snaps to the
nearest scanned truss line or raised-area edge (*Snap* button; Alt lets go for
one drag). Releasing saves through
`PUT /api/rigs/{id}/fixtures/{fixture_id}/position`, which confirms the
position, so the amber marker goes. The header also carries *Undo room scan
moves* when a scan's moves can still be undone. Full behaviour in
`ROOM_SCAN.md`. All the geometry is pure functions in `fixtureDrag.ts`; the
layer only turns pointer events into rays. While a fixture is held nothing in
React changes (the marker moves through refs); the rig is given the new
position on release. The orbit controls are the scene's default controls
(`makeDefault`) so the layer can hold the camera still during a drag. Stored
positions only: nothing here sends DMX.

**Cost.** Fixtures are memoised and given nothing that changes per frame;
colour, intensity, beam visibility and head angles are written straight to
three.js objects in the frame loop. The beam debug table is behind a *Debug*
button and no fixture writes a row for it while it is closed.

## Tests

`frontend/src/__tests__/previsPreview.test.ts` covers the room shell geometry,
`hangBeam` against three.js's own rotation, and the output feed. The beam state
mapping and the backend's output frames have their own tests
(`beamState.test.ts`, `backend/tests/unit/test_preview_output_frames.py`).
`fixtureDrag.test.ts` covers the drag, snap, limit and nudge geometry of Move
fixtures; `RoomScanUndoButton.test.tsx` the undo button.

## What is left

- **Move fixtures has not been dragged in a browser.** Its geometry is tested
  and the page builds; the pointer handling in the canvas has only been read,
  not used. Dragging is one fixture at a time, has no undo of its own, and on
  a touch screen has no height drag (Shift) or one-drag snap release (Alt).
  A save lays the venue out again, which re-renders every fixture once per
  drop or key nudge.
- **Not seen in a browser this round.** The code type-checks, the unit tests
  pass and the bundle builds; nobody has yet looked at the LIV dome, a leaning
  fixture or the amber markers on screen. The in-app browser pane stops WebGL
  when hidden, so check in a real or headless browser against a running
  backend, and feed it audio before judging the beams.
- **Per-axis invert has no writer.** The rig stores one `is_inverted` flag,
  which the view reads as pan invert. The `pan_invert` and `tilt_invert` tags
  are honoured when present, but nothing in the backend or the rig editor sets
  them yet, and the engine itself inverts nothing. Tilt invert therefore needs
  the tag added by hand until the patch has a proper field for it.
- **A rig switch shows the old rig's frames for one message.** The feed is not
  cleared when the rig changes (`clearOutputFeed` exists and is not yet
  called); the next message, about 30 ms later, replaces them.
- **Scenery does not stop a beam.** Beams land on the floor, the four walls
  and the flat ceiling height. They pass through the dome, the balcony, the
  risers and the LED walls.
- **A database rig has a room shell only after a room scan.** A demo preset
  carries its own; a patched rig gets one by applying a phone scan
  (`ROOM_SCAN.md`). Without one it is drawn in the generic club room.
- **LED walls are idle panels.** Nothing drives their content.
- **Colour wheels need named ranges.** A wheel channel with no `value_ranges`
  in the profile is drawn open white; gobos, prisms, frost and iris are not
  drawn at all.
- **Pan/tilt zero is a convention.** Centre of travel is drawn straight down
  the fixture's own axis. A fixture whose home differs needs an offset the rig
  does not yet hold.
- **The store still receives every frame.** The page keeps calling
  `setUniverse` and `setFixtureStates` for other readers; the 3D view no longer
  reads either, and they could be dropped from this page.
- **A stale picture is labelled, not dimmed.** After two seconds without a
  frame the header says *Output lost* but the last frame stays drawn.
