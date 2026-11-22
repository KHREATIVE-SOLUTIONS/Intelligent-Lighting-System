# Flash-and-tap locate mode

Status: **built, and tested against the in-memory DMX controller only.** It has
not been run against real fixtures. The frontend changes were not typechecked
in the session that wrote them (no `node_modules` in the worktree); run
`npx tsc --noEmit` in `frontend/` before relying on them.

## The problem it solves

`POST /api/import/patch-sheet` turns a bare patch list into a rig with a 3D
layout generated on a stage template. Every one of those positions is a guess:
the fixture carries the tags `position_source:template` and
`position_unconfirmed`, and the preview reports `position_confirmed: false`.

Flash-and-tap is how a guess becomes a fact. The system lights one fixture, the
operator taps where it really is on the plan, and the flag comes off.

## Where it lives

It is the flash-to-identify walkthrough, not a second system beside it:

- `backend/app/api/endpoints/rig_identify.py`: the session, the rows, the fit
  and the row check.
- `backend/app/services/venue_import/apply.py`: the one place that spells the
  tag names (`with_position_source`, `with_position_confirmed`,
  `is_unconfirmed`, `position_source`).
- `frontend/src/components/rig/IdentifyWalkthrough.tsx`: the dialog. The rig
  builder's "Identify Lights" button offers "Check the N guessed" when the rig
  has active fixtures tagged `position_unconfirmed`.
- `backend/tests/integration/test_flash_and_tap.py`: the tests.

Everything the walkthrough already did still holds: one fixture lit at a time,
held steady and never strobed, at no more than the venue's audience intensity
cap; the show taken off the wire while it runs and its parked levels put back;
a 90 s cap per fixture, a browser heartbeat, a watchdog, one session at a time.

## What a tap now means

| Answer | Endpoint | Tags afterwards |
| --- | --- | --- |
| Tapped on the plan | `/position` | `position_source:tap`, flag off |
| "It is where the plan shows it" | `/confirm` | `position_source:confirmed`, flag off (a measured position keeps its own source) |
| "I can't see it" | `/skip` | unchanged, plus `identify:no-response` |
| Leave it, move on | `/advance` | unchanged |

The dialog's third button is now `/confirm`. `/advance` is still on the API and
still confirms nothing; the dialog no longer calls it. The plan draws the
current light's stored position as a ring, so "where the plan shows it" has
something to point at.

## Locate mode: `start?only=unconfirmed`

`POST /rigs/{id}/identify/start?only=unconfirmed` walks only active fixtures
tagged `position_unconfirmed`. Without `only`, the walkthrough is the one it
always was: every active fixture, in address order, no rows.

**Not located.** A switched-off fixture drives nothing, so it is never lit. The
state lists those under `not_located` with the reason (`unmatched_type`: no
profile matched; `address_clash`: shares channels; otherwise switched off in
the patch), counted apart from `still_unconfirmed`, which is the lights in the
walk that are still guesses. A rig with nothing left to walk is refused with a
400 before the show's output is touched.

**Rows, ends first.** A row is one `group_name` on consecutive addresses. The
address test is there because a sheet that names its own group can spread it
over two trusses, and a fixture missing from the middle of a run (switched off,
or already measured) would leave a hole the fit spaces straight across; either
case starts a new row. Each row is walked first fixture, last fixture, then the
rest.

**Fit.** Once both ends are located (tapped or agreed as drawn), nothing is lit
and the state's `row.stage` is `fit_offer`. `POST .../fit-row` spaces the
fixtures between the ends evenly along the line joining them, X and Z only,
tags them `position_source:row_fit` and **leaves them unconfirmed**.
`{"accept": false}` drops back to tapping each one. For the demo festival sheet
(7 rows, 84 fixtures) that is 14 taps.

A fit is only offered when the generated positions were a straight line on the
plan. A ring, a tower stack, a row with an end that was skipped, and a row with
a fixture that cannot be lit all go to one tap per fixture, and
`row.fit_blocked_reason` says which.

**Row check.** After a fit the row is lit one fixture at a time, from the
plan's left to its right, 1.5 s each (`ROW_CHECK_STEP_S`), once, and then goes
dark. Each fixture is blacked out before the next comes on. `POST .../flash`
runs it again. `POST .../row-check {"passed": true}` confirms every fitted
fixture in the row; `false` leaves them guesses and drops back to tapping each.
The check sits in the session's one hold slot, so `/end`, finishing, the
watchdog and the fixture-test stop endpoints all release it.

**Height.** `POST .../row-height {"height": 7.25}` sets one trim height on
every fixture of the row being located. It moves nothing on the plan and
confirms nothing. It only reaches the current row, so set it before answering
the row's last question.

**Mirrored sheets.** The first time a row's two real taps run the opposite way
across the stage to how the row was drawn, the state carries
`mirror_offer: {"fixtures": N}`. `POST .../mirror` negates X on the template
guesses in the rows not yet answered, and on switched-off template guesses.
Tapped, confirmed, fitted and measured positions are not moved.

This is not the same operation as the import's `mirror` option. That option
only swaps which side "SL" and "SR" positions land on; this reflects every
remaining guess about the centre line, which also reverses each row's address
order. That is what two taps running the wrong way actually show.

## Safety rules, unchanged from the walkthrough

- Only ever started by a person standing in the room. No test, script or
  automation starts a locate session against real output.
- Steady light only, capped at the audience intensity cap, one fixture at a
  time, show output suspended for the duration and restored on every exit path.
- Tests drive it against the in-memory DMX controller.

## Known limits

- A row longer than 60 fixtures takes longer to walk than the 90 s single-light
  cap. The walk still ends by itself and the heartbeat still guards it.
- A tower stack is one tap per fixture: its fixtures share a spot on the plan,
  so there is no line to fit them to.
- Row height cannot be set after the last row's final answer, because the
  session is complete by then. Edit it in the rig builder.
- A fixture with no position at all (`unplaced`, at 0,0,0) is not a guess and
  is not in the locate walk. The full walkthrough places it with a tap.

## Not in scope

Finding fixtures with a camera, and anything that needs a network service.
