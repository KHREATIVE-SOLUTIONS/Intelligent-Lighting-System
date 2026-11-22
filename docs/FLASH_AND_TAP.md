# Flash-and-tap locate mode (design note)

Status: **not built.** This note is the plan for the pass after patch sheet
import. Nothing described under "What to build" exists yet.

## The problem it solves

`POST /api/import/patch-sheet` turns a bare patch list into a rig with a 3D
layout generated on a stage template. Every one of those positions is a guess:
the fixture carries the tags `position_source:template` and
`position_unconfirmed`, and the preview reports `position_confirmed: false`.

Flash-and-tap is how a guess becomes a fact. The system lights one fixture, the
operator taps where it really is on the plan, and the flag comes off.

## What already exists

`backend/app/api/endpoints/rig_identify.py` (the flash-to-identify walkthrough,
`frontend/src/components/rig/IdentifyWalkthrough.tsx`) already does the hard
and the dangerous parts, and locate mode should be built on it, not beside it:

- Lights one fixture at a time, held steady and never strobed, at no more than
  the venue's audience intensity cap.
- Takes the running show off the wire while it runs and puts the parked levels
  back afterwards.
- Releases itself: a 90 s cap per fixture, a browser heartbeat, a watchdog, one
  session at a time.
- Records a tap as `position_x` / `position_z`, keeps the height, and marks a
  fixture that never lit `identify:no-response`.

## The gaps between that and locate mode

1. **A tap does not confirm.** `record_position` writes the position but leaves
   `position_unconfirmed` and `position_source:template` on the fixture, and
   "keep and advance" confirms nothing either.
2. **It walks every active fixture in address order.** A rig of 84 is 84 taps,
   including fixtures whose positions are already measured.
3. **Switched-off fixtures are skipped silently.** An import switches off a
   fixture whose type matched no profile or that shares channels with another.
   Those cannot be flashed (a placeholder profile drives nothing), so they need
   to be listed as "not located", not left out of the count.
4. **A tap is X and Z only.** Height stays whatever the template gave the row.

## What to build

**Confirming.** In `record_position`, and in a new "it is where the plan shows
it" answer, drop `position_unconfirmed` and set the source tag to
`position_source:tap` (tapped) or `position_source:confirmed` (accepted as
drawn). Keep the tag helpers in `venue_import/apply.py` as the one place that
spells these names.

**Only what needs it.** `POST /rigs/{id}/identify/start?only=unconfirmed` walks
just the fixtures tagged `position_unconfirmed`. The summary reports how many
are still unconfirmed, and separately how many could not be flashed and why.

**Row by row, ends first.** The layout generator already made each row a group
(`group_name`) in address order. Walk a row's first fixture, then its last, and
then offer to re-space the fixtures between those two taps along the straight
line joining them (`POST /rigs/{id}/identify/{session}/fit-row`). For the demo
festival sheet that is 14 taps for 84 fixtures. Fitted fixtures get
`position_source:row_fit` and **stay unconfirmed** until the check below.

**Row check.** After a fit, light the row one fixture at a time, left to right,
at a walking pace. One answer, "that ran left to right along the truss",
confirms the whole row; "no" drops back to tapping each one. This is a steady
step from fixture to fixture, never a chase fast enough to read as a flash.

**Height.** One trim height per row, edited once on the row, not per fixture.

**Mirrored sheets.** If the first row's two taps come out right to left, offer
to mirror the whole remaining layout (the `mirror` option of the import) before
the operator taps their way through it the hard way.

## Safety rules, unchanged from the walkthrough

- Only ever started by a person standing in the room. No test, script or
  automation starts a locate session against real output.
- Steady light only, capped at the audience intensity cap, one fixture at a
  time, show output suspended for the duration and restored on every exit path.
- Tests drive it against the in-memory DMX controller, as
  `tests/integration/test_identify_walkthrough.py` does.

## Tests to write with it

- A tap removes `position_unconfirmed`; skipping does not.
- `only=unconfirmed` leaves measured fixtures out of the walk.
- A row fit between two taps is evenly spaced and stays unconfirmed; a passed
  row check confirms all of it.
- Switched-off fixtures are reported as not located, with the reason.
- Every exit path (finish, end, heartbeat loss) leaves the fixture dark and the
  show's levels restored.

## Not in scope

Finding fixtures with a camera, and anything that needs a network service.
