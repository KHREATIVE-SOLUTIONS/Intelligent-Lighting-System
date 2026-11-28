# New venue setup checklist

One place to go from an empty box to a rig you can demo to the owner and hand
to the house console. It reads what the box already knows and opens the
screens that already exist. It writes nothing itself and never sends DMX.

## Where it is

- **Rig builder** toolbar: **Venue Setup**. This is the full checklist for the open rig.
- **Rigs** page: **Venue setup**, next to New Rig. With no rig open it offers
  step 1 (LIV demo, new rig, import) and the audio input. The rig's own steps
  say they are waiting on step 1.

## The steps

| # | Step | Status comes from | Button opens |
|---|------|-------------------|--------------|
| 1 | Venue and rig | rig open, active fixture count; "demo running" from the engine | demo view (`/visualizer`, navigation only), rig wizard, import dialog (MVR / GDTF / MA2 XML / CSV) |
| 2 | Patch | every active fixture has an address 1-512; patch clashes from `GET /rigs/{id}/conflicts` | Auto-Patch; import a patch sheet (MA2 XML / CSV import) |
| 3 | Layout | scanned room on the rig; stage plot uploaded / calibrated | Room Scan, Edit Room (scanned rigs), stage plot calibrate |
| 4 | Locate | fixtures tagged `position_unconfirmed` | Identify Lights (flash and tap) |
| 5 | Readiness checks | fail / warn counts of the readiness report | Readiness dialog (with its one-press fixes) |
| 6 | Focus presets | moving heads and focus targets from the focus table | Focus presets panel |
| 7 | Audio input | the status bar's audio reading, BPM from the engine | audio device chooser |
| 8 | Output target | the status bar's DMX reading | **Not available yet**: no screen sets the Art-Net target |
| 9 | Export to console | readiness failures (nothing records that an export was taken, so this step is never "done") | console export (MA2 / MVR) with the handoff pack |

A step can be **Done**, **Needs attention**, **Not started**, **Skipped** or
**Not available yet**. A button whose screen does not exist on this build is
shown as a "not available yet" chip, never as a dead button.

Under the title two lines say where the venue stands:

- **Progress**: `"Main room": 6 of 9 done, 1 needs attention, 1 skipped.` The
  attention and skipped parts are left out when there are none.
- **Next**: `Next: 4. Locate`, the first step in order that is neither done nor
  skipped and has a button to press. A step that is not available yet (or
  needs attention but has nothing on this build to open) is passed over, so
  Next never points at a dead end. When nothing is left to open the line says so.

The Next step's row carries a **Next** chip and a bar down its left side, its
buttons are filled rather than outlined. Next follows the statuses as they
arrive (readiness and focus are fetched after the panel opens), and skipping
the Next step moves it on to the following one.

**Skip** marks a step as not wanted at this venue (no moving heads, say). Skips
are kept per rig in the browser's localStorage under `venueSetup.skipped.<rigId>`.
A done step is never hidden behind a skip.

Readiness and focus are read only while the panel is open, and again after
its own focus, export or audio dialog is closed (or **Check again**).

## Get demo-ready

**Get demo-ready** (bottom left of the panel) takes an operator from nothing to
a demo in one click, on the LIV Miami demo rig or the rig the panel is open on.

1. Pressing it reads the box and writes nothing: the readiness report (when a
   saved rig is open) and the audio capture status and devices.
2. It shows the plan in three lists: what it will do, in order, each with one
   line on what it does; what it left as it is and why (already running,
   already captured, no saved rig); and what **stays with you**.
3. Nothing runs until **Do these N**. Each action then gets a line: Done,
   Skipped (it had nothing to change) or Failed with the box's error text. A
   failure does not stop the actions after it. When the run ends the
   checklist reads its statuses again.

What it may do, and only this (`DEMO_ACTION_KINDS`):

| Action | When | Call |
| --- | --- | --- |
| Load the LIV Miami demo | no rig with fixtures is open, no demo is running, and output is verifiably not sending | `demoApi.applyPreset('liv_miami_approx')` |
| Run the readiness checks | a saved rig is open | `readinessApi.get` (reads only) |
| Make groups | a check that is not OK offers it | `readinessApi.autoGroups` |
| Start the audio input | nothing is captured and no feed reaches the box | `audioApi.startCapture` |
| Refresh the focus presets | a saved rig is open | `focusPresetsApi.get` (reads only) |

- **Output stays the operator's.** It never changes the output target, never
  starts output, never flashes a fixture and never sends Art-Net or DMX. Locate
  (flash and tap), Output target and Export to console are always in the
  manual list. Loading the demo swaps the engine's fixtures, so it is planned
  only when output is not set up, not connected, or held until a rig is
  patched (`outputVerifiablyIdle`; no reading yet counts as maybe sending);
  otherwise loading the demo is a manual step
  too. The box also refuses (409) to load a demo over a patched live rig; the
  run shows that as Failed. It never activates a saved rig.
- **Only Make groups is applied.** It adds groups and nothing else; its undo
  record is kept on the rig as for any fix (see Open). Re-address and
  Set modes change the patch, which must then be matched on each fixture, and
  Locate flashes fixtures: each is listed as manual with its reason
  (`AUTO_READINESS_FIXES`).
- **Audio:** the device the box remembers, else the one this browser last
  started, else this computer's loopback, after the same filtering as the
  audio chooser. It never picks a line input nobody chose; with nothing to
  pick, audio is a manual step.
- **On the LIV demo** there is no saved rig, so readiness and focus are listed
  under "left as it is", not run.

## Code

- `frontend/src/utils/venueSetupChecklist.ts`: the status logic, pure and tested
  in `frontend/src/__tests__/venueSetupChecklist.test.ts`.
  `nextVenueStep` picks the Next step and `venueSetupProgress` writes the
  progress line.
- `frontend/src/components/setup/VenueSetupChecklist.tsx`: the panel, tested in
  `frontend/src/__tests__/VenueSetupChecklist.test.tsx` (the nine statuses for
  an empty and a nearly ready rig, the step buttons, Not available yet, Skip
  across a remount, Next, and the Rig builder's Venue Setup button).
- `frontend/src/utils/demoReady.ts`: Get demo-ready's planner (`planDemoReady`)
  and runner (`runDemoReadyPlan`), pure and tested in
  `frontend/src/__tests__/demoReady.test.ts`; the button in
  `frontend/src/__tests__/VenueSetupChecklist.demoReady.test.tsx` (plan before
  confirm, the run, a failure that does not stop the rest, the refresh, and
  the demo left manual while output may be sending).
- Not to be confused with `utils/setupChecklist.ts`, the four-line pre-show
  check on the dashboard.

## Try it

1. Start the backend and frontend as usual. Use other ports than 8000/5173 if
   those are taken.
2. Open **Rigs** and press **Venue setup**. Step 1 offers the LIV demo, a new
   rig or an import.
3. Open a rig in the builder and press **Venue Setup**. Work down the list;
   each step's status updates when its dialog closes.

## Open

- No screen sets the output target (Art-Net IP / universe), so step 8 shows
  status only.
- Patch sheet import is the console (MA2 XML / CSV) import, which makes a new
  rig. Nothing lays fixtures out from a patch sheet automatically.
- After a run the checklist reads readiness and focus again at once; the
  Venue, Audio and Output rows come from the status bar's poller and catch up
  on its next poll.
- The plan is not re-checked on confirm: the output state is the one read when
  the plan was shown. The box's 409 over a patched live rig is the guard after that.
- Get demo-ready cannot tell which demo preset is running, only that one is;
  if another demo is on the engine it leaves it there.
- The readiness panel offers Undo only beside a fix it ran itself, so a Make
  groups run by Get demo-ready has no Undo button. The undo record is on the
  rig (`POST /api/rigs/{id}/readiness/fix/undo` takes it back) until the next
  fix replaces it; otherwise groups are edited by hand.
