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

## Code

- `frontend/src/utils/venueSetupChecklist.ts`: the status logic, pure and tested
  in `frontend/src/__tests__/venueSetupChecklist.test.ts`.
  `nextVenueStep` picks the Next step and `venueSetupProgress` writes the
  progress line.
- `frontend/src/components/setup/VenueSetupChecklist.tsx`: the panel, tested in
  `frontend/src/__tests__/VenueSetupChecklist.test.tsx` (the nine statuses for
  an empty and a nearly ready rig, the step buttons, Not available yet, Skip
  across a remount, Next, and the Rig builder's Venue Setup button).
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
