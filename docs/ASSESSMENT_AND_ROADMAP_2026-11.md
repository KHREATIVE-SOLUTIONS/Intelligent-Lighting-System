# App Assessment and MVP Roadmap — November 2026

Written 2026-11-17. Supersedes `ASSESSMENT_AND_ROADMAP_2026-07.md` for planning; that
document is kept as the record of where the project was in July.

**Goal this roadmap serves:** an MVP that can be simulated convincingly against a venue
rig, then demonstrated live in a venue without putting the room, the fixtures or the
audience at risk, as soon as possible.

---

## 1. Verdict

The product now exists. A fresh install, a rig patched from a template, and music in
produce valid Art-Net on the patched universe at a steady 40 frames per second, with
nothing outside the patch. In July none of that was true.

It is not yet ready for lights-on in a venue. The reasons fall into four groups, and
only the first is large:

1. **Safety and fail-safe gaps** — the strobe limit can be bypassed, silence blacks out
   the room, and a crash freezes whatever frame was last sent.
2. **Operator-path gaps** — a DJ line feed cannot be selected on Windows, a rig built in
   the UI does not go live, and the documented launcher does not start the operator UI.
3. **Hardware truth** — nothing has been run on a real node or fixture, and the
   renderer hard-codes the shutter channel instead of reading the fixture profile.
4. **Show look** — the output is dim, pale and small-moving on the material tested.

Before any of that: **the code on this machine is not the current app** (section 2).

The roadmap in section 7 is five gates, each with a pass/fail test. The first live demo
is the fifth gate.

---

## 2. Read this first: three diverged copies

| Copy | Commit | State |
|---|---|---|
| GitHub `master` (both remotes) | `da3569a`, 2026-10-23 | The current app. 40 commits ahead of local. No open pull requests. |
| Local `master` (this checkout) | `565c189`, 2026-08-11 | 40 behind, 1 ahead, plus uncommitted edits to `visualizer/server.py`, `visualizer/index.html`, `.claude/launch.json`. Holds the only Python environment. |
| Two local worktree branches | `claude/relaxed-nash-d6a28f`, `claude/wizardly-mendeleev-ff9e50` | 2 commits each, built on local `master`. |

Local and GitHub conflict in four files: `start.py`, `visualizer/server.py`,
`scripts/audio_capture.py`, `.gitignore`.

Local `master` lacks most of what makes a venue demo defensible: the latched blackout,
the grand master, the health bar, the pre-show checklist, the fixture picker, the hold
that keeps the demo rig off the network, and audio-loss recovery. Its one extra commit
deletes the only 3D view that draws the database rig. **Do not demo from it.**

Everything below describes GitHub `master` at `da3569a`. The table above is the state
the audit found.

**Resolved the same day (2026-11-17), on your decision to use GitHub as the base:**

- Local `master` now equals GitHub `master` (`da3569a`).
- The old local commit and the uncommitted visualizer edits are preserved on
  `archive/local-visualizer-2026-11` (`70174d6`). Nothing was discarded.
- The carry-over fixes, this document and the harness sit on branch `g0-one-tree`,
  **not yet committed**. Until they are, a `git clean` would lose the document and
  the harness.

G0 in section 7 lists what is done and what is still open.

---

## 3. What was tested, and what was not

**Run:**

- Backend test suite on `da3569a`: 1033 passed, 8 skipped, 5 expected failures.
  Continuous integration is green on the same commit.
- A wire-level simulation, built for this audit (`scripts/venue_sim/`). It starts the
  real backend against a throwaway database, walks first-run setup, patches the
  seeded "Small Club" template (10 LED pars, 2 LED bars, 4 moving heads, 100 channels,
  one universe), plays synthetic music into the audio WebSocket at real-time pace, and
  captures every Art-Net packet on loopback. The capture is decoded against the patch
  read straight from the database, not against the engine's own channel maps.
- Four parallel code audits (venue safety, show logic, operator UI and visualizer,
  launch and output), each required to cite file and line. Every row of sections 5a
  and 5b was then re-checked by me, in the code or on the wire, except the parts
  tagged [audit]. Two audit predictions did not reproduce and are listed in 5b.

**Evidence tags used below:**

- **[wire]** measured from captured Art-Net packets.
- **[code]** I read the cited line.
- **[audit]** an audit agent read or ran it; I did not re-verify.
- **[inferred]** reasoning from the above, not observed.

**Not covered — treat as unknown:**

- **No hardware.** No node, no fixture, no real cable. Level figures are linear DMX
  values, not what a room looks like.
- **Synthetic music only.** The repository contains no recorded audio.
- **Audio went in over the WebSocket**, not through server-side device capture, which is
  the venue path. Silence handling and latency may differ there.
- **One rig**, with no channels typed `other`, no strobe-typed channel and one universe.
  "Control channels are never written" was therefore not exercised on the wire.
- **The soak was 9 minutes**, a smoke test. The soak command now runs for one hour by
  default and eight at most (`scripts/venue_sim/README.md`); no run longer than a few
  minutes has been completed yet.

---

## 4. What works (measured)

| Behaviour | Result |
|---|---|
| Fresh install, nothing patched | 0 packets in 5 s. The demo rig runs internally and is held off the network. [wire] |
| Unauthenticated access | Rigs, blackout, raw DMX and strobe routes all 401; audio WebSocket refused; `/health` gives liveness only. [wire] |
| First-run setup | Console setup code, then password, then token: works. [wire] |
| Template to live rig | 10 seeded templates; apply plus activate puts the rig on stage with no restart. [wire] |
| Art-Net validity | Correct header, version 14, 512-slot frames, sequence 1–255; 0 malformed in ~8,000 packets. [wire] |
| Frame rate | 40.0 fps. Gaps alternate ~16 and ~31 ms (the Windows timer tick); one 112 ms gap in the first four-minute pass. [wire] Re-measured 2026-11-20 with packets stamped in a separate process: longest gap 34 ms. The 112 ms was probably the harness pausing, not the backend. [inferred] |
| Universe ownership | Only the patched universe is sent; 0 non-zero channels outside the patch. [wire] |
| Blackout | Dark on the next frame, 100% dark for 6 s under loud music, heads keep tracking, frames keep flowing, light back 16–46 ms after restore. [wire] |
| Grand master | 0.3 scales output to 0.29×; movement unaffected. [wire] |
| Audio feed lost | Holds an ambient look at ~22% within ~10 s; recovers when music returns. [wire] |
| Tempo | 127.8 BPM reported for a 128 BPM track. [wire] Hip-hop, half-time and drum-and-bass tempos correct. [audit] |
| Graceful stop | Exits in 0.7 s and leaves the last look on the node, as configured. [wire] |
| Reboot | Rig comes back by itself; first Art-Net frame 4.1 s after process start. [wire] |
| Smoke soak, 9 minutes | Memory flat at ~350 MB, 40.0 fps every minute, 0 send errors. Details in section 10. [wire] |

### Scorecard against the July findings

| July finding | Now |
|---|---|
| The rig you build never drives the lights | Fixed. [wire] |
| Async database bug broke nine routers | Fixed; the template, activate and patch routes were exercised. [wire] |
| No DMX leaves the box | Fixed. [wire] |
| No authentication | Fixed, on by default. [wire] |
| Transmitter shares the event loop | Own thread. [wire: steady 40 fps under load] |
| Audio loss kills the show | Feed loss holds an ambient look. Silence still blacks out (section 5). |
| Intelligence switched off by an early return | The early return is still there. Inside it, the section detector, beat lock, drop anticipation and track-change detection are now live. Beam looks, key lighting, LFO and the pro movement engine are still unreachable. [audit] |
| Strobes disabled | On at boot, "conservative", 3 Hz, behind a governor. |
| `value_ranges` unpopulated | 34 of 1,353 bundled channels carry them, and the renderer does not read them. [code, data] |
| Three UIs, four launchers | Still: React UI, standalone visualizer, `operator.html` (dead under default auth), and 8+ launch paths. [audit] |
| No packaging, no autostart | Still none. [audit] |
| AGPL dependency | Gone from `requirements.txt`; still installed in the local environment. [audit] |

---

## 5. What blocks a safe live demo

Ordered by how you would meet it, not by size.

### 5a. Met by an operator following the runbook

| # | Gap | Evidence |
|---|---|---|
| A1 | **No runnable copy of the current app.** The only environment belongs to a checkout 40 commits behind. | [wire: git] |
| A2 | **Windows refuses line inputs.** Any device that is not a loopback capture is rejected with a 400, so a DJ feed into a USB interface cannot be chosen. Only music played on the laptop itself works. | [code] `audio.py:379-380` |
| A3 | **A rig built in the UI does not go live.** Every creation path marks the rig active; the UI shows Activate only for inactive rigs; only the activate route installs a rig on the running engine. The rig appears after a backend restart. | [code] `RigList.tsx:197`, `rigs.py:231-257` |
| A4 | **The documented launcher starts no operator UI.** `start.py` serves the visualizer as static files, with no data feed, and opens that. The backend does not serve the built React app. | [code] `start.py:88-91,463`; `main.py:15` imports `StaticFiles` and never mounts it |
| A5 | **Silence is a black room.** Music stops: dark within 5 s and still dark at 40 s. A quiet 96 BPM track averaged 0.9% output, fully dark 62% of the time. A 15 s intro sat at 1%. After a reboot with no audio: dark. | [wire] |
| A6 | **A crash or kill freezes the last frame.** No packets follow a kill; the node keeps a frame that may be a full-white flash. Nothing restarts the process: the repository has no service, scheduled task or supervisor. Under `start.py` on Windows, Ctrl+C terminates the backend without a clean shutdown. | [wire]; [code] `start.py:81,183` |
| A7 | **The output target is set only by editing `.env` and restarting.** The UI has no screen for it, the socket is never bound to an interface, and there is no node discovery (no ArtPoll anywhere in `backend/app`), so the status reads healthy with no node listening. Universe fields are 0-based with no hint. | [code]; universe base [audit] |
| A8 | **The 3D preview cannot validate a patch.** Both visualizers draw the engine's internal fixture state, not the bytes a fixture would receive. Wrong address, wrong mode, CMY versus RGB, closed shutter and blackout are all invisible. The standalone page also loads three.js from a CDN and is keyed to a demo rig's fixture IDs. | [audit]; [code] `visualizer/index.html:178,552` |

### 5b. Reachable by anyone holding an operator token

None of B1 to B5 has a button in the React UI. Each is one API call.

| # | Gap | Evidence |
|---|---|---|
| B1 | **Manual mode has no strobe limit.** With the `no_strobe` profile set and autopilot off, the LFO strobe preset produced an 8 Hz full-rig flicker, 9 luminance peaks in the worst second. | [wire] |
| B2 | **The safety profile fails open.** An unrecognised profile name (tested: `off`) selects "performance" and raises the cap to 18 Hz. I confirmed the setting, not an 18 Hz output. | [wire: API reply]; [code] `effects_engine.py:3840-3846` |
| B3 | **A read puts a universe on the wire.** `GET /api/dmx/universe/5` produced 40 fps of zeros on universe 5 from then on. The visualizer server polls this route when it has a token. | [wire]; [code] `dmx_controller.py:493-497` |
| B4 | **A demo preset can overwrite a live rig.** Applying `pro_beam_room` over the real rig put 256 foreign channels on universe 0 and 200 on universe 1. | [wire] |
| B5 | **Blackout is not the last stage before the wire.** With blackout latched, a raw channel write lit a fixture to full for a moment. During a flash-to-identify walkthrough the engine's output is detached, and blackout lives in the engine, so the Blackout button cannot darken the identified fixture. | [wire]; [code] `rig_identify.py:205-219` |

**Predicted by the audits, not reproduced on the wire:**

- A running test pattern did not reach the wire while the engine was driving the rig
  (0 stray channels).
- The Autopilot toggle, which *is* a button, did not unleash strobing. In manual mode
  the drop got no accent at all on two plays, one of them with the drop detected
  (peak 27%). Manual mode is dull, not dangerous, on what was tested. The audit read
  ungoverned strobe code on that path; treat it as unproven either way until G2.

### 5c. Only a bench test can settle

| # | Gap | Evidence |
|---|---|---|
| C1 | **Shutter and strobe channels are hard-coded.** The renderer writes 255 to a shutter channel and 0 to a strobe channel. In the bundled library, 0 means "Closed" on the strobe-typed channel of four fixtures (ADJ Mega TriPar Profile Plus, ADJ Ultra HEX Bar 12, Elation SixPar 200, Martin RUSH PAR 2), which would sit dark. 59 of 73 shutter or strobe channels have no value ranges at all. | [code] `fixture_groups.py:267-272`; [data]; effect [inferred] |
| C2 | **The 3 Hz cap covers accents only.** Full-white flashes stayed at 3 or fewer per second, as governed. The beat pulse underneath added more: across seven drops, 4–6 luminance swings of 20% or more in the worst second. | [wire], a DMX-level proxy |
| C3 | **No home, invert or aim.** Heads move about mechanical centre; the per-fixture invert flag is not read. Pan stepped up to 50° in one frame as the drop landed. | [audit]; [wire: 16 single-frame jumps over 3% of range in 54 s] |
| C4 | **Colour-wheel, gobo, prism and white channels are never driven.** A colour-wheel-only spot stays open white. | [wire]; [audit] |
| C5 | **Nothing has run on a node or a fixture.** | — |

### 5d. What the audience would see

| # | Finding | Evidence |
|---|---|---|
| D1 | **Dim.** Steady dance music rendered at 10–14% average output; no fixture passed ~40%. Brightness tracks raw input level: 0.9% to 21.7% across −18 to +9 dB of gain. | [wire]; [audit] |
| D2 | **The drop is not reliable in sequence.** Caught in 8 of 12 single plays, about one beat late each time, and in 2 of 4 during the soak. Missed in all 3 plays where the track followed 14 s of loud music on a fresh boot, once under `no_strobe`, and on the first two drops of the soak. The test suite plays each track on a fresh engine, so it cannot see this. | [wire] |
| D3 | **The drop fades early.** On 3 of the 4 caught drops traced to the end of the track, the rig fell from ~37% to ~11% about ten seconds in, with the music still at full energy. | [wire] |
| D4 | **One pale colour.** Changing palette changed the output by 0.5%; saturation on the wire about 0.30. | [audit] |
| D5 | **Small movement.** Pan uses 7–13% of range, tilt 10–21%, from six sine patterns. | [wire]; [audit] |
| D6 | **Pars all do the same thing.** On a pars-only rig every fixture is identical; the chase needs moving heads. | [audit] |
| D7 | **Light lands ~75 ms after the kick**, consistently (156 of 160 beats on a DJ mix). White flashes run on a free 2.6 Hz grid, not on the beat. Bar 1 is arbitrary. | [wire]; [audit] |
| D8 | **Speech and loud bands mislead it.** Speech locked a false tempo; a loud live band without a steady kick drew a false drop. | [audit], synthetic |

About 17,000 of the 28,700 lines under effects, audio, lighting and ML do not affect
the DMX frame. [audit]

---

## 6. Corrections to earlier statements

- My interim note that the drop "did not land under `no_strobe`" was a misreading. A
  control run lost the drop with no profile call at all. The cause is history-dependent
  and not yet established (D2).
- The July document's Phase 5 item "fold previs into the React app" was reversed on
  local `master` and kept on GitHub. GitHub's choice is the better base (section 7, G0).

---

## 7. Roadmap: five gates

Each gate has a test that passes or fails. Sizes are relative, not dates.

### G0 — One tree, one environment (small)

- Take GitHub `master` as the base.
- Park local commit `565c189` and the uncommitted visualizer edits on a named branch.
  Carry over only: the `.gitignore` union, the `8014 → 8000` default, token-safe
  printing in `audio_capture.py`, and the `validate_show_pipeline.py` fix from
  `claude/wizardly-mendeleev-ff9e50`.
- Build a clean environment from `requirements.txt` (no BeatNet, no ultralytics) and
  install frontend dependencies.

**Pass:** one checkout equal to GitHub `master`; 1033 backend tests and the frontend
tests pass there; one documented command starts backend and UI.

**Status, 2026-11-17 — mostly done:**

| Item | State |
|---|---|
| One checkout on GitHub `master` | Done. Old work parked on `archive/local-visualizer-2026-11`. |
| Carry-overs | Applied on `g0-one-tree`, uncommitted: `.gitignore` union; `visualizer/server.py` default port 8000; `scripts/audio_capture.py` no longer prints the token; `scripts/validate_show_pipeline.py` uses port 8000, sends `ILS_TOKEN`, and reports a refusal as a refusal. |
| Backend tests in this checkout | 1035 passed, 6 skipped, 5 expected failures. Two more ran than in the audit worktree because the dev database and bundled library are present here. The dev database was byte-identical afterwards. |
| Frontend | Dependencies installed from the lockfile; 42 of 42 tests pass. `tsc` reports 18 errors, none new; CI treats them as non-blocking. |
| Backend and UI start together | Verified with the two entries in `.claude/launch.json` (`lighting-backend` on 8000, `lighting-ui` on 5173): the UI reached the backend and showed the login screen. `scripts\run_dev.bat` also exists but was not run, and it reinstalls dependencies every time. A single launcher is G4. |

Still open:

- Commit `g0-one-tree`, including this document and `scripts/venue_sim/`.
- The Python environment is the old one and still carries BeatNet and ultralytics.
  Fine for development; do not ship it or build an image from it.
- Three stale worktrees and their branches (`adoring-liskov`, `relaxed-nash-d6a28f`,
  `wizardly-mendeleev-ff9e50`). Their useful parts are already carried over.
- The 18 TypeScript errors.
- `scripts/validate_show_pipeline.py` fails its own move-in-black check on unmodified
  GitHub `master` ("during transition dimmer=0.900, expected near black"). It tests a
  path the live renderer does not use; fix or retire the check under Track L4.

### G1 — Wire-truth simulation (medium)

This is "simulate a venue". It turns today's one-off measurements into a standing test.

1. Move `scripts/venue_sim/` into the test suite as a wire tier.
2. Add a deliberately awkward rig: two universes, a fixture with `other` channels, a
   strobe channel where 0 is "Closed", a colour-wheel-only spot, a CMY fixture, coarse-only
   pan and tilt, a fixture patched above channel 500.
3. Test sequences, not single tracks: several tracks back to back, as a DJ plays them.
   Add three to five real recordings you have the right to use.
4. Feed audio through server-side capture as well as the WebSocket.
5. Drive the 3D preview from decoded Art-Net bytes through the patch and profile, so it
   shows what a fixture receives, including blackout and grand master.
6. Soak for eight hours.

**Pass:** the wire tier asserts every row of section 4; the preview goes dark on
blackout; eight hours with flat memory, steady 40 fps and no gap over 100 ms.

### G2 — Fail-safe and venue-safe (large; the bulk of the work)

1. **One output stage, after every layer and before the wire**, holding: a flash
   limiter on total rig luminance, blackout, and the grand master. Persist the blackout
   latch across restarts. Closes B1, B5 and C2 in one place.
2. **Fail closed.** An unknown safety profile selects the strictest (B2).
3. **A venue mode** that disables the manual, LFO, legacy-strobe, demo and raw-DMX
   routes, and makes `GET` read-only (B3, B4).
4. **Never black the room by accident.** An idle look after N seconds of silence, a
   house-lights button, a defined look at boot and on stop, and a supervisor that
   restarts the backend (A5, A6).
5. **A rig goes live when it is created or edited**, with a visible "live" marker (A3).
6. **Accept line inputs on Windows**, allow only one audio feed, add an input trim and
   meter (A2).
7. **Report honestly.** Engine exception streaks and DMX state feed the health verdict.

**Pass:** wire tests show no path exceeding the flash limit in any mode; blackout holds
against every writer; silence, feed loss, kill and reboot each end in a defined look.

### G3 — Bench hardware (small, but needs equipment)

Equipment: one Art-Net node, one moving head with a shutter channel, one LED par, and
the USB audio interface fed from a mixer.

- Node receives on the intended universe; unicast target set from the UI.
- Flash-to-identify finds each fixture; shutter opens; colours are right.
- Pan and tilt directions and home are correct; add per-fixture invert and home.
- Blackout is physically dark. Pull the cable: the status says so (needs node discovery).
- Kill the process: note what the node holds.
- Film at 240 fps: count flashes per second and measure light against kick.

Work this will force: shutter and strobe values from `value_ranges` (C1), node
discovery and a target screen (A7), a universe-numbering hint.

**Pass:** every line above ticked on real equipment.

### G4 — Demo day (medium)

- One launcher: the backend serves the built UI, starts at boot, restarts on failure,
  needs no internet.
- Pre-show checklist extended: node seen, each fixture answered, strobe policy chosen,
  house look and blackout tried.
- A two-hour rehearsal on the bench with a recorded set.
- Agreed with the venue beforehand: strobe signage, their console released on your
  universes, an isolated network or a unicast target, and their console as the fallback.

**Pass:** cold boot to lights following music in under a minute with no keyboard; pull
the audio, pull the network, kill the process — each recovers or holds a safe look.

### Track L — Look (medium each; run beside G2)

The minimum for a demo that impresses is L1 to L3.

| # | Change | Fixes |
|---|---|---|
| L1 | Normalise rendered level against the loudness reference the analyser already computes, with a floor per section | D1, A5 |
| L2 | Give the dimmer an attack and release envelope, and a chase that includes static fixtures | D6 |
| L3 | Stop the colour collapsing to the mood colour; re-gate the white wash | D4 |
| L4 | Slew pan and tilt at changes; widen movement | D5, C3 |
| L5 | Make the drop reliable in sequence, give it a deliberate hold, put flashes on the beat, add a latency trim | D2, D3, D7 |
| L6 | A drop that reads without flashing, for the `no_strobe` posture | — |

L1 has a known constraint: raw energy was chosen so a noise floor stays dark. The five
expected-failure tests in `tests/musical` are the targets for L1, L2 and L5.

### Order

Original order: `G0` → `G1` and `G2` together → `L1`–`L3` → `G3` → `G4`.

**Changed on 2026-11-17 at your direction: show intelligence comes first.** The order is
now `G0` → Track I (below) → `G1`, `G2` → `G3` → `G4`. Track I replaces Track L.

G2 and G3 still gate lights-on in a venue. Nothing in Track I makes the system safer;
it makes it worth watching.

Order the bench equipment early; it is the only item with a lead time. G2's output stage
belongs in the transmit path, not the renderer, so it does not collide with Track I.

---

## 7A. Track I — show intelligence (first priority)

Goal, in your words: perfect beam movement, effect usage, and colour chosen to the mood
and energy of the song, with the show responding properly to song structure.

Every step is judged on the look bench (`scripts/look_bench/`), which plays tracks back
to back through the real engine and renders the whole show as one picture with numbers.
It was checked against the wire measurements before being trusted. The reference rig is
the new `club_night` preset: 12 movers on two trusses, 4 moving washes, 8 LED bars,
4 strobes and 6 pars, mirrored about the centre line.

| Step | What | Bench number, before → target | State |
|---|---|---|---|
| I0 | Look bench and a reference club rig | Reproduces the wire | Done |
| I1 | Movement a designer would program: symmetric tilts, tilt ripples, mirrored circles, figure-eights, fan sweeps, fly-outs. Whole-bar cycles. A glide, not a jump, between looks. | Mirror symmetry −0.3…+0.4 → **+1.0**. Biggest lit step 51–53° → **4°**. Pan travel 46–68° → **57–84°**. | First pass done |
| I1b | Looks built from a starting position plus a motion, aimed at points in the room so they are uniform on any rig (design below) | A look sheet per look per rig: mirror error 0, every beam inside the room, nothing faster than a head can turn. **All 44 generated movements pass on all seven demo rigs.** | First pass done |
| I1c | The look library chooses the look: 67 designed looks tagged by section, mood, energy and audio character, picked by weighted random, never one of the last four (detail below) | A run of four tracks: **22 looks in 21 changes, 18 of them different, none following itself.** Levels, colour, flashes, sections and drops identical to before. | Stage 1 done: the look's movement, speed and size. Its dimmer, chase, strobe and colour parts are not performed yet. |
| I2 | Fixture roles: washes as the bed, bars and pars with their own patterns, strobes kept for the drop | Family correlation 0.99 → **0.85–0.97**. Strobes glowing all night → **dark outside the drop**. Hue variety 0.11–0.36 → **0.26–0.82**. Spread inside the bars 0 → **0.03**. | First pass done |
| I3 | Colour to mood and energy: stop the collapse to one pale colour, contrast between sections, re-gate the white wash | Saturation 0.19–0.33 → 0.6 or more. A palette change must change the picture. | |
| I4 | Level and dynamics: follow programme loudness with a floor per section; attack and release; a build that ramps | Verse level ~1% → visible. Steady groove 0.13 → higher. The five expected-failure tests. | |
| I5 | Structure: the drop caught every time in a sequence, held deliberately, flashes on the beat, look changes on the phrase line, a real bar one | Drop caught 8 of 12 → every time. | |
| I6 | Beam effects: gobo, prism, zoom, colour wheel | Needs fixture value ranges first (C1) | Later |

**What I1 changed.** Each moving head now knows where it sits on its truss, so pan is
mirrored about the centre line and tilt is shared. Movements take 4, 8 or 16 beats
instead of about two, cover more distance, and finish on a bar line. (Since I1c a
library look runs at its own speed, and 54 of the 67 use a factor such as 0.75 or 1.3,
so those no longer cycle in whole bars. They still start on the phrase line.) The engine never
asks a head for more than 240°/s of pan or 180°/s of tilt, so a change of look is a
glide. Sections, levels, flashes and drop detection are numerically unchanged.

**What I2 changed.** Beams keep the movement and the chase. Moving washes and pars are
a steady bed in a second colour, turned round the colour wheel from the beams' colour:
close by in quiet sections, opposite at the biggest. LED bars run their own pattern, a
pulse from the centre of each row outward, with booth and wall rows answering each
other. Strobes are dark outside the drop. Inside the drop every fixture does exactly
what it did before, so the drop is unchanged frame for frame.

Two things the tests and the bench caught while doing it:

- The first version made the wash bed slightly brighter through a build than the chase
  it replaced, which shrank the step into the drop and failed an existing contract
  test. The bed now sits lower, under the beams.
- The bench's brightness-swing counter was counting a held level as two or three
  peaks. Fixed. With roles on and off compared under the same counter, the worst
  second is identical (3 swings of 20% or more on a drop). Earlier bench figures of
  7–9 were that over-count. The wire measurement of 4–6 in real time stands as the
  safety number; the bench count is for comparing one run with another.

**The 3D view can now show the club rig.** In demo mode the view has a "Demo rig"
chooser, and it draws whichever demo rig the engine is running. The backend refuses to
apply a demo rig while a patched rig is live, which closes safety hole B4.

### I1b — looks from a position plus a motion (first pass built)

**Built.** `backend/app/services/effects/live_looks.py` replaces the angle-based
patterns. Four positions (all centre, columns, fan, cross), five motions (hold, tilt,
sweep, circle, and a fly-out that crosses from one position to another), three phase
modes (unison, ripple from the centre outward, truss against truss). Every sensible
combination is generated: 44 movements. An aim function turns each head's target point
into pan and tilt from where it hangs, including which way its body is turned.

**Judged.** `scripts/look_bench/look_sheet.py` draws every movement from above and from
the front for any rig. All 44 pass on all seven demo rigs, from 4 heads to 52: mirror
error zero, every beam inside the room, lean under 68 degrees, and nothing faster than a
head can turn. On the bench, levels, colour, flashes, sections and drops are identical
to before; only movement changed.

**What the sheet caught on the way.** The first fly-out moved the target point across
the floor, which dragged it past the foot of each head and asked for 340 to 620 degrees
of pan a second. It now crosses in pan and tilt, the way a console crossfades two
position palettes, over two cycles.

**A gap found and closed.** The engine did not know which way a fixture's body is
turned (`rotation_y`), although rigs built from templates set it and the 3D view draws
it. Aiming would have been right on demo rigs and wrong on patched ones. It is passed
through now.

**Not built yet.** More positions (out over the crowd, to the booth, split left and
right). A side-to-side sweep with every beam moving together rather than mirrored.
Per-fixture invert for a head hung the other way up, which still needs the bench.

### I1c — the look library, brought back (stage 1 built)

**What it is.** `backend/app/services/effects/look_library.py` holds 67 designed looks
with names like `predrop_freeze`, `drop_fast_chase` and `moonlight_drift`. Each is
tagged with the sections it suits, its moods, an energy range and the kinds of audio it
fits, and carries a movement, a speed and size, a dimmer effect, a chase style, a strobe
mode and a colour treatment. Its selector keeps only the looks that fit the section and
energy, drops the last four it used, weights the rest by mood and audio character, and
picks by weighted random. That is what stopped a night repeating itself. It was written
for an earlier engine and nothing on the live path imported it.

**What is connected now.** `backend/app/services/effects/live_library.py` is the join.
On every new section and every new phrase the engine asks the library's own selector
for a look and performs its movement at the look's speed and size. Each of the
library's fifteen movements has a place in the generated vocabulary (its `fly_out` is
centre opening to a fan, its `ballyhoo` is crossed circles truss against truss, and so
on). A club style makes the looks that move its way two and a half times likelier and
rules nothing out, so a style never shrinks the choice. The look running is reported to
the UI's data stream as `look` and `look_movement`; nothing draws it yet.

**What the selector is told about the music, and what it is not.**

| Input | Source | Honest? |
|---|---|---|
| Section | The engine's own detector | Yes |
| Energy | The section's place on the library's scale, moved by how loud the moment is against the track's own level | Yes. Raw energy follows playback level and would have offered breakdown looks in a quiet drop. |
| Mood | Valence and arousal | Rough. Mood is only a bonus weight, so a wrong mood cannot pick a wrong look. |
| Audio character | Heavy bass, sparse, full, percussive, an impact | Only these five. The library also knows vocal-heavy, synth-lead, drum-breakdown, riser and snare-roll; nothing in the engine can detect those reliably, so they are never claimed. |
| Musical fingerprint | Not supplied | The modules that produced it were measured in August and could not tell apart the things they described. |

**Not performed yet, on purpose.** A look's dimmer effect, chase style, bump, base
level, strobe mode, blinder, colour treatment and fixture-group isolation. Those change
brightness and flashing, which is where the safety limits and the drop contract live.
So today a look's name promises more than it delivers: `drop_strobe_eighth` moves like
itself and does not strobe on eighth notes. A test pins this: two different nights are
frame for frame as bright as each other. The library's `predrop` looks are also held
back, because a wrongly predicted drop must stay invisible.

**Measured.** Four tracks back to back on the club rig: 22 looks run in 21 changes, 18
of them different, none following itself. Levels, colour, flashes, sections and drops
identical to the run before.

**Two things that are not as good as they were, stated plainly.**

- *The heads tilt less, and on some music pan less.* Median travel on the four bench
  tracks, in degrees:

  | | Pan | Tilt |
  |---|---|---|
  | I1 movement (what is on GitHub) | 84, 70, 76, 57 | 65, 48, 70, 48 |
  | I1b with nine looks in rotation | 160, 129, 135, 144 | 41, 46, 43, 45 |
  | I1c with the library choosing | 68, 97, 128, 131 | 25, 24, 46, 35 |

  Two causes. A look stretches its throw toward a point in the room instead of swinging
  through a set angle, which is fewer degrees of tilt. And the library is uneven: many
  of its looks keep pan still and move in tilt (`symmetric_fan`, `cascade`,
  `tilt_wave`), many run at less than full size, and its `snap_look` is mapped to a
  held cross. Which of our movements each of the library's fifteen maps to is a choice,
  in `MOVEMENT_TO_LOOK`, and so is how deep a tilt goes (`TILT_DEPTH`). Both can be
  made bolder, and should be judged by eye in the 3D view.
- *A few looks are too fast for a head at high tempo.* Every look at its own speed and
  size is within what a head can do up to 174 BPM (238 degrees a second of pan against
  a limit of 240). At 190 BPM the quickest sweep asks for 260, and under the fastest
  club style up to 373. The slew limit holds the head back, so the fixture is safe and
  the look flattens. An expected-failure test records it.

**Proved the tests can fail.** Fifteen deliberate breakages, each caught by a named
test: the selector forgetting its history, the running look handed back, a movement
mapped to nothing, the engine ignoring the look's movement, speed or section, a look's
size leaking into brightness, the seed ignored, the club style doing nothing or ruling
looks out, and others.

**Found on the way.** Two earlier tests set the section by writing it into the engine,
which the detector overwrote on the next frame, so they passed without ever leaving the
verse. They now hold the section the way the operator's Drop button does, and still
pass. And an offline run is only repeatable on the virtual clock, because the beat
clock places each audio block inside its frame by the wall clock.

**Next stages, each on its own with the bench watching.**

0. Fit a look's speed to the tempo when it is taken, so nothing outruns a head at any
   BPM or club style, and review the movement mapping for travel.
1. Dimmer effect and chase style per look. The engine's dimmer layer already runs every
   frame and is ignored; the look would choose its effect. Must keep "silence is dark"
   and the level contracts.
2. Strobe mode per look, through the accent governor only, never around it.
3. Colour treatment per look (saturation and contrast), which belongs with I3.
4. Fixture-group isolation: a look that uses only the back truss, or only the washes.
5. Predrop looks, once the drop predictor's false alarms are measured.
6. More audio characters, as and when a detector is shown to be right.

The design, as proposed:

Your point: a movement only looks good if the starting position is good, and the
starting position has to be uniform and symmetric on whatever rig is in front of it.
Today each pattern in `live_moves` bakes position and motion together, and positions
are raw pan and tilt angles. The same angles do not make the same picture on a
different rig: a truss twice as wide fanned by the same degrees lands its beams
somewhere else.

Consoles solve this with position palettes plus effects. The proposal is the same
idea, with one addition that makes it rig-independent: **positions are aimed at points
in the room, not set as angles.**

| Layer | What it is | Examples |
|---|---|---|
| 1. Rig model | Worked out from any rig automatically: its trusses, each head's place on its truss, and the room's landmarks (dance-floor centre, booth, side walls, a point above the crowd). | Already partly built: `u`, row, `row_dir`. |
| 2. Position | A named shape that gives every head a **target point**. The engine converts the point to that head's pan and tilt from where it hangs. Mirror-symmetric by construction, and the same picture on any rig. | All centre (every beam to one point). X-cross (each side aims across). Fan. Parallel columns. Out over the crowd. To the booth. Split left and right. High knot. |
| 3. Motion | An offset laid over the position: a waveform with a size and a speed. | Tilt up and down. Side-to-side sweep. Circle. Figure-eight. Or a morph from one position to another, which is what a fly-out is (centre → fan). |
| 4. Phase | Who moves when. | Unison. Mirrored. Centre outward. Along the truss. Odd and even. Truss against truss. |
| 5. Look | One position, one motion, one phase mode, a size and a speed. | "All centre + tilt, unison". "X-cross + tilt ripple". "Fan + sweep, mirrored". |
| 6. Chooser | Picks looks from the music: size and speed from energy, a new look on the phrase line, a bigger change at a section change, no repeats, a morph or a move-in-the-dark between them. | Breakdown: narrow, slow, centred. Drop: fly-out, wide. |

Looks can be written by hand as a library, generated by combining layers under rules,
or both: a library of combinations known to work, with generated variations of size,
speed and phase.

**How a look is judged before it reaches a rig.** A "look sheet" from the bench: a top
view and a front view of where every beam lands at the start position and across one
cycle, drawn for several rigs (4 movers, the club rig, the 52-mover room, an
asymmetric rig). Numbers on it: symmetry, evenness of spacing between neighbouring
beams, every beam inside the room, no beam near horizontal toward the audience, and
no move faster than a head can make.

**What it depends on.** Each fixture's real orientation. The conversion from a point
to pan and tilt needs to know which way a head hangs, so the per-fixture invert and
home from the bench-hardware gate (G3) matter more under this design, not less.

**Two faults in the 3D view were found and fixed along the way:**

- Pan did nothing. The head used three.js's default rotation order, which applies pan
  about the beam's own axis. No amount of pan moved a beam on screen, so every look
  appeared to be tilt only. Confirmed with three.js directly, then fixed.
- Switching quality to Perf or Ultra threw an error on every frame and froze the view
  until Balanced was selected again.

**Still true and worth knowing:** the engine's tilt direction is a convention. A real
head can hang either way round, and the engine has no per-fixture invert yet (C3). The
previs and the engine now agree with each other; a real rig needs the bench test.

**What Track I needs from you:** three to five real tracks you have the right to use,
as WAV or FLAC. The repository has only synthetic drums over thin pads, and colour to
mood cannot be judged on those.

---

## 7D. Built and not connected (checked 2026-11-17)

The live show is drawn by one function, `_update_fixtures_rebuild`, and the engine
returns as soon as it has run. Everything below was written for earlier engines and is
never imported, or runs every frame with its answer thrown away, or is used only by the
older renderer further down the same function, which the automatic show never reaches.
The look library was one of these until I1c. Imports and call sites were checked in the
code.

**Worth connecting. Each matters for a venue.**

| System | What it does | State today | Why it matters | Where it belongs |
|---|---|---|---|---|
| Key lighting (`lighting/key_lighting.py`) | Keeps the DJ, a singer or a stage zone lit to a minimum whatever the show is doing | Fully plumbed: rigs store the zones, the wizard and templates assign fixtures, the loader hands them to the engine. Only the older renderer asks for the answer; the live one does not. | An operator can mark the booth lights today and nothing happens. In a breakdown or a blackout the DJ goes dark. | G2, with a decision on what it does in silence and under blackout |
| Move in black (`_apply_mib_transition`, config `mib_enabled`) | Dims a head while it travels a long way, and brings it back when it arrives | Written and switched on in config. Applied only by the older renderer. | The library changes look every phrase, and a big change is a lit glide across the room. A designer hides that. It changes brightness, so it needs the bench. | I1c, beside the dimmer stage |
| Dimmer effects (`effects/dimmer_effects.py`) | Chases, pulses, waves and bumps across fixtures | Updated every frame. The renderer ignores it and uses its own single chase. | It is what each library look's dimmer effect and chase style name. Without it every look is lit the same way. | I1c stage 1 |
| Strobe controller (`effects/strobe_controller.py`) | Strobe modes: on the beat, eighths, bursts, build | Updated every frame, ignored | It is what each library look's strobe mode names. It must run through the accent governor, never beside it. | I1c stage 2 |
| Fixture capabilities (`lighting/fixture_capabilities.py`) | Says what each fixture can do: colour wheel or mixing, gobos, prism, zoom | Consulted only by the older renderer | A real beam usually has a colour wheel, not red, green and blue. Roles, gobos and colour all need it on a real rig. | C1, before the first real rig |
| Gobo engine (`effects/gobo_engine.py`) | Chooses gobos, rotation and prism to the music | Never imported | Gobos in the show and in the 3D view. Needs each fixture's real value ranges first. | I6 |
| The library's `predrop` and `ethereal` looks | Freeze, close-down and suspense looks for the bars before a drop | In the library. The engine has no such section, so never asks for them. | They are the suspense looks. The drop predictor knows when one is coming. | I1c stage 5, after false alarms are measured |

**The idea matters; the code was measured and is not good enough.** These were meant
to feed the look library its audio character and its musical fingerprint. Each would
have to be rebuilt one detector at a time and proven on real tracks.

| System | Was meant to tell the show | Finding |
|---|---|---|
| `audio/audio_intelligence.py`, `spectral_intelligence.py`, `musical_intelligence.py` | Vocal-heavy, synth lead, riser, sparse or full, and the fingerprint | Never imported. Measured in August: could not tell apart the things they named. |
| `audio/drum_intelligence.py` | Kick, snare, hats, fills, drum breakdowns | Never imported. Could not separate drums. |
| `audio/vocal_analyzer.py` | When someone is singing | Never imported. Needs rework. |
| `audio/structure_predictor.py` | What section comes next | Never imported. The drop predictor in the section manager does the part that is used. |

**Leave parked or retire.**

| System | Why |
|---|---|
| `audio/section_detector.py` | Rejected in the bake-off: it called a metronome a drop 54% of the time. |
| `effects/decision_engine.py` (1,235 lines) | Runs every frame and drives layers nobody reads. Its anti-fatigue idea (vary intensity across a night) is worth lifting into I4. |
| `lighting/beam_look_scheduler.py`, `beam_scene_state_machine.py`, `beam_pattern_library.py`, `lighting/movement_patterns.py`, `effects/movement_patterns.py` | Three earlier movement systems. Replaced by positions, motions and the look library. Candidates for removal once the library has run a night. |
| `effects/lfo_engine.py` | A console-style effects engine with its own API. For operators programming by hand, not for the automatic show. |
| `lighting/section_templates.py` | Applied every frame to settings the renderer does not read. |
| `show_engine/show_generator.py`, `lighting/ald_mapper.py`, the video and training pipeline | Offline show generation and training data. On the cut list. |
| `ml/genre_classifier.py`, `ml/music_structure.py`, the club genre model, MERT | Behind a flag or without trained weights. |

---

## 7C. Track S — setup without a specialist (proposed 2026-11-17)

Goal, in your words: easy for non-technical venue owners to set up, with no need to fly
out a specialist, and a previs that recreates the venue.

**The idea that makes this tractable: the system controls the lights, so the lights are
the measuring instrument.** It does not have to guess a rig from a photo. It can turn
one fixture on, look, and know. Anything an AI proposes from a photo is then confirmed
by a test the system runs itself.

| Step | What the owner does | What the system does | Exists today |
|---|---|---|---|
| 1. Connect | Plugs in the node | Finds the node and says so | No (no node discovery, gap A7) |
| 2. Find what is on the line | Nothing | Asks fixtures to identify themselves over RDM where they support it; otherwise steps through addresses and notes which ones make light | No (RDM is a simulated stub) |
| 3. Name each fixture | Photographs its label, or picks make and model | An AI vision model reads the label and proposes profile and mode; the system then **tests** it: dimmer, red, green, blue, shutter | Picker by make and model exists, with an offline library. Photo reading and the test are new. |
| 4. Locate each fixture | Points a camera at the stage, or taps a floor plan | Flashes fixtures one at a time and sees where each is. For moving heads, sweeps pan and tilt, watches where the beam lands, and solves which way the head hangs | Flash-to-identify with tapping exists. The camera and the solving are new. |
| 5. The room | Enters width, depth and height, or taps the floor's corners in a photo; marks booth and dance floor | Builds the room in the previs | Stage size and zones exist. The room model is new. |
| 6. Sign off | Watches | Runs a self-test and compares what the camera sees with what the previs predicts | No |

Step 4 for moving heads is also the fix for a gap the audit raised (C3): it measures each
head's orientation, so invert and home stop being something a person has to know.

**In order of difficulty:**

1. *No camera.* The guided flow above with the owner answering "did it turn red?"
   Mostly joining up what exists. Needs the rig to go live when created (gap A3).
2. *Camera sees flashes.* Comparing a frame with the light off against one with it on
   is classical image processing, not AI, and robust. A laptop webcam at front of
   house is enough.
3. *Moving-head calibration* from the beam spot on the floor.
4. *AI reading labels, console screenshots and patch sheets.* Needs internet at setup
   time only; the show stays offline.
5. *Full venue recreation* from a phone scan or photos. Valuable for the previs as a
   sales tool, not needed for the lights to work. A parametric room gets most of the way.

**Honest limits.** Fixtures without RDM cannot be discovered by model, only by which
addresses respond. A camera in a dark, hazy room saturates easily. A phone used as the
camera needs a secure connection to the laptop, which is extra setup; the laptop's own
webcam does not.

---

## 7B. Is the technology a problem?

Short answer: no rewrite is called for. The weak points are operational, and most are
choices rather than limits.

**Headroom, measured.** The engine takes 0.37 ms per frame and the analyser 0.73 ms per
audio block [audit]; the whole backend used about 20% of one core with flat memory over
nine minutes [wire]. Python is not the bottleneck at one or two universes.

| Kind | Finding | Evidence |
|---|---|---|
| Stack limit | **Windows timer.** Frames leave at alternating ~16 and ~31 ms instead of an even 25 ms, with an occasional gap near 100 ms. Art-Net nodes absorb this; it is not visible. | [wire] |
| Stack limit | **One process, no supervisor.** If it dies, the node holds the last frame and nothing restarts it. | [wire] |
| Stack limit | **A blocked event loop stalls the show.** Starting capture scans devices inline; the audit expects a freeze of a few seconds. The transmit thread keeps repeating the last frame. | [inferred] |
| Design choice | **46 ms audio blocks**, no overlap. With transport this gives about 75 ms from kick to light. A smaller hop, or firing on the predicted beat, fixes it without changing the stack. | [wire] |
| Design choice | **Art-Net only.** No sACN, no USB-DMX, no node discovery, no merge with a house console, one destination for all universes. | [code] |
| Design choice | **Loopback-only audio on Windows.** | [code] |
| Design choice | **A browser UI served by a dev server.** Fine for control; not yet a packaged application. | [code] |
| Unknown | A real node and fixture, a run of hours, and the 3D view running on the show machine at the same time. | — |

Where the stack would start to hurt: many universes with pixel mapping, audio
reactivity under ~20 ms, or reliability a venue depends on unattended. The usual
answer to all three is to move the output stage into its own small process, which is
already where G2 puts the safety limiter.

**Interfacing with a venue's rig live** is where the real risk sits, and it is about
the venue more than the code: their console must release the universes you drive,
every fixture's mode and address must match the patch, and a head hung the other way
round needs an invert the engine does not have. Those are G3 and G4.

---

## 8. Cut list — not before the first demo

- QR scanning, RDM discovery, photo-to-rig.
- Show timeline playback, the training recorder and video pipeline, MIDI, audio fingerprints.
- `operator.html` and the standalone visualizer.
- The club genre model, MERT, BeatNet.
- sACN and USB-DMX, unless the venue has no Art-Net node.
- Docker, Postgres, Redis and the Kubernetes deployment document.
- Reviving beam looks, key lighting, LFO and the pro movement engine.
- Gobo, prism and colour-wheel selection. Until then, flag such fixtures at patch time.
- The five dormant intelligence modules (8,290 lines never imported).

---

## 9. Assumptions and open questions

Assumed, because the plan does not change much either way:

- The demo machine is this Windows 11 laptop.
- Audio arrives as a line feed from a mixer into a USB interface.
- The rig is one or two universes, and you operate it throughout.
- The first demo is DJ-led dance music.

Needed from you:

1. Which copy becomes the base (recommended: GitHub `master`).
2. What bench equipment you have or can get.
3. The venue's fixtures and whether it has an Art-Net node.
4. Whether the first demo runs accents at all.

---

## 10. Smoke soak

Nine minutes of continuous music, ten tracks back to back (a DJ mix alternating with
the intro/build/drop track), sampled once a minute. [wire]

| Measure | Start | End | Note |
|---|---|---|---|
| Memory (backend process tree) | 350 MB | 352 MB | Flat |
| Threads | 63 | 51 | Falling, not leaking |
| CPU | — | 111 s over 9 min | About 20% of one core |
| Frame rate | 40.0 fps | 40.0 fps | Every minute |
| 99th-percentile frame gap | 33.8 ms | 33.8 ms | |
| Longest frame gap per minute | 53–104 ms | | Two minutes reached ~100 ms |
| Channels outside the patch | 0 | 0 | |
| Send errors, malformed packets | 0 | 0 | |
| Backend log growth | — | 3.3 KB per minute | About 5 MB a day, no visualizer polling |

Nothing drifted in nine minutes. This is too short to rule out a slow leak; the
eight-hour run in G1 is still owed.

One show finding came out of it. The drop fell inside the sampled window four times,
in minutes 2, 4, 6 and 8. It was accented in minutes 6 and 8 and missed in 2 and 4.
The misses came early in the session, which points at warm-up or history (D2).

---

## 11. An attended demo as it would have to run today

Not recommended for a venue. This is the shortest honest path on `da3569a`.

1. Fresh clone of GitHub `master`; Python 3.11 or 3.12; `pip install -r requirements.txt`
   in `backend`; `npm install` in `frontend`.
2. `backend\.env` with `ARTNET_IP=<node address>` and no other keys. Unknown keys stop
   the backend at start.
3. Two terminals: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` in
   `backend`, and `npm run dev -- --host` in `frontend`. Not `start.py`.
4. Read the setup code from the backend console; set the password in the UI.
5. Build the rig. Universes are 0-based: a console's "universe 1" is 0 here.
6. **Restart the backend** so the rig goes live (A3).
7. Audio: play the music on this laptop and pick its loopback device (A2).
   *Since this was written, line inputs are accepted on Windows: a USB interface
   or mixer line-in can be picked instead. See "Choosing the audio input" in the
   README.*
8. Check the health bar. It cannot tell you whether the node is listening.
9. Leave Autopilot on. Manual mode has no controls in this UI and gives no drop.
10. Keep a hand on Blackout. Press it before closing anything.

---

## Appendix — reproducing the measurements

`scripts/venue_sim/` holds the harness and the JSON reports from this audit.

```bash
python scripts/venue_sim/venue_sim.py <backend_dir> <output_dir>
```

It uses free loopback ports for HTTP and Art-Net (8031 and 16454 at the time of the
audit), so nothing reaches the network. Run it with the backend's Python environment.

Since 2026-11-20 the harness lives in `backend/tests/wire/` and the rows of section 4
are standing tests: `pytest tests/wire --wire` from `backend`. See
`scripts/venue_sim/README.md`.

| Script | What it measures |
|---|---|
| `venue_sim.py` | First run, music, silence, feed loss, graceful stop, reboot, kill |
| `venue_sim2.py` | Blackout, grand master, section timeline, quiet track, DJ mix |
| `venue_sim3.py` | The same drop three times in one boot |
| `venue_sim4.py` | The token-only safety holes of section 5b |
| `venue_sim5.py`, `venue_sim6.py` | Drop after a profile call, in manual mode, and the control |
| `venue_sim7.py` | Drop in manual mode where autopilot is shown to catch it |
| `venue_soak.py` | Memory, pacing, channel jumps, flash rate, blackout and grand master under continuous music, with a verdict and a written report (one hour by default, `--hours 8` for G1) |
