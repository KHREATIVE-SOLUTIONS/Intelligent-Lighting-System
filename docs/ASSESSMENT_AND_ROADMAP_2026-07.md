# Full App Assessment & Commercial Roadmap — July 2026

Produced from a four-track deep audit of the entire codebase (fixture library, venue
layouts, music intelligence, architecture/commercial readiness). Every claim below was
verified against source with file:line evidence; the OFL API claims were verified with
live probes.

---

## 1. The headline: two severed spines

The app is far more built-out than it appears — GDTF/MVR parsers, a 50-profile bundled
fixture library, a rig wizard, auto-patching, a section manager with hysteresis, beam
look scheduling, genre strobe budgets, key lighting. **Most of it is disconnected from
the live show by exactly two structural breaks:**

### Break #1 — The rig you build never drives the lights
- The effects engine hardcodes an 18-fixture demo rig at startup
  (`backend/app/services/effects/effects_engine.py:146` → `create_demo_rig()`,
  `fixture_groups.py:317`), and `main.py:130-145` force-applies the `pro_beam_room`
  demo preset on *every* boot, overwriting anything the user configured.
- No code path anywhere constructs an engine fixture from a DB
  `Fixture`/`FixtureMode`/`FixtureChannel`. `grep "RigFixture" backend/app/services/`
  → zero hits.
- The reactive WebSocket path takes a `rig_id` param and ignores it, blasting
  hardcoded DMX addresses 1/17/33/… (`api/endpoints/websocket.py:567,714,735,754`).
- Result: a venue owner can import a perfect fixture profile and build a perfect rig,
  and the engine still outputs the demo channel map at demo addresses.

### Break #2 — The intelligence you wrote is switched off
- `effects_engine.py:1513-1519`: in the default config (`auto_mode=True`,
  `_rebuild_busker_enabled=True`) the update loop takes an early return. Everything
  after it — DecisionEngine, SectionManager, BeamLookScheduler, BeamSceneStateMachine,
  ProEffects (incl. genre strobe budgets), KeyLighting, LFOEngine application, MIB —
  is **dead code at runtime**.
- The live show is rendered by one 345-line function (`_update_fixtures_rebuild`,
  `effects_engine.py:509-854`) fed by a 28-line threshold ladder
  (`_rebuild_update_intent`, `:480-507`).

### Break #3 (runtime, fatal) — the async DB bug
Nine endpoint modules call sync SQLAlchemy (`db.query()`, unawaited
`flush/commit/refresh`) on the **AsyncSession** yielded by `get_db`
(`db/database.py:67`). ~45 call sites across: `wizard.py` (the wizard's final
"Create Rig" button **cannot succeed**), `templates.py`, `rig_patching.py`
(auto-patch, conflict detection), `rig_import_export.py` (MVR/console import, all
exports), `qr_scanning.py`, `discovery.py`, `fixture_test.py`, `fixture_library.py`
(incl. `sync-bundled` — so the 50 bundled profiles can never be loaded), plus 2
handlers in `rigs.py` (batch-update — also shadowed by route ordering at
`rigs.py:801` vs `:233` — and duplicate).

### Break #4 (hardware, fatal) — out of the box, zero DMX leaves the box
- `backend/.env:26` `ARTNET_IP=0.0.0.0` → `sendto` fails with WinError 10049
  (`backend.err.log:11`), error suppressed after first occurrence
  (`dmx_controller.py:186-191`), `/health` still reports `"dmx": "connected"`.
- Universe 0 only in the hot path (`effects_engine.py:1517,1673`, `main.py:166`).
  Fixtures auto-patched to universes 1+ render into no frame. Schema caps universes
  at 16 (`schemas/dmx.py:20,35`). No sACN. Net/SubNet declared but never packed.

**Consequence of all four:** the demo experience convincingly works (visualizer, audio
reactivity) while the product path (real fixtures, real rig, real venue) has never been
exercised — the 33MB runtime log confirms not one wizard/template/patch/import call was
ever made against a live instance.

---

## 2. Assessment by area

### 2.1 Fixture library ("import any light like a GrandMA")

**Works:** GDTF ZIP parsing (real, wired to `POST /api/fixtures/import/gdtf` —
the healthiest import path); MVR parsing incl. embedded GDTF + positions; grandMA/Hog/
Eos patch-list parsers; 50 hand-authored bundled profiles (91 modes, 1,317 channels,
schema-perfect); a genuinely capable manual FixtureEditor UI; `fixture_test_service.py`
contains the only *correct* profile→DMX mapping in the codebase.

**Broken/missing:**
- Frontend GDTF import is fake: builds FormData, throws it away, creates an empty
  fixture named after the file (`ImportExportDialog.tsx:167-172`) — and that dialog is
  orphaned anyway; the RigList import option is hardcoded `disabled` ("coming soon").
- OFL client targets endpoints that don't exist (verified live: 500s). Real search is
  `POST /api/v1/get-search-results` returning flat strings. Errors are swallowed to
  `[]`, so the UI silently shows zero results forever. Frontend also expects objects,
  not strings.
- GDTF parser ignores `Offset` → every 16-bit channel shifts the whole channel map;
  fine flag is backwards; no namespace handling (namespaced GDTF → 1-channel dimmer
  fallback); CMY dumped to `other`.
- OFL converter destroys 16-bit movement (fine channel aliases → `other`).
- `ChannelType` enum missing: CMY, iris, frost, CTO/CTB, lime/indigo, animation wheel,
  framing shutters, gobo2/3. No pixel/matrix concept. `value_ranges` (gobo/color-wheel
  slot semantics) populated **nowhere** — not bundled data, not parsers.
- `fixture_capabilities.py` is a 4-entry static table keyed on fixture *type string*,
  never reads actual channels.
- Even the demo output path silently drops all channels outside a 10-key set
  (`fixture_groups.py:296-312`) — gobo/prism/zoom/focus/color-wheel/amber/UV never
  written; LED-bar strobe dead (key mismatch `strobe` vs `shutter`).
- Pan/tilt→DMX assumes every fixture is 540°/270° (`fixture_groups.py:292-293`).

### 2.2 Venue layouts

**Works:** wizard steps 1–2 and auto-place math; PatchingService (clean conflict/gap
logic); programming audit; WizardService DMX walking with universe rollover; React
RigVisualizer correctly renders DB rigs; JSON/CSV export code; MVR/console import code.

**Broken/missing:**
- Wizard step 3 hard-stops: presets request fixture types that don't exist in the
  seeded DB (only 2 generic fixtures; the 50 bundled ones need a broken sync endpoint;
  0 of them are `moving_head`, which 7 of 8 presets require) → **Next is permanently
  greyed with no explanation**.
- Wizard "Create Rig" crashes (async bug). So the wizard has never completed.
- Coordinate conventions disagree: wizard emits z ∈ [0, depth], 3D previs floor spans
  [−depth/2, +depth/2] → auto-placed fixtures render off the back of the stage.
- Auto-placement is a group-name substring heuristic (`"front"`, `"wash"`, `"cyc"`…)
  that collides entire groups onto identical positions and never sets rotation.
- 2D builder: drags never persisted; palette drag-and-drop wired to nothing; 3D toggle
  and snap modes decorative; undo/redo permanently disabled.
- Templates: table exists, never seeded, gallery orphaned, endpoints broken.
- QR scanning: decoder is a placeholder on non-Chrome; request/response shapes
  mismatch backend; label "PDF" endpoint returns JSON.
- RDM discovery: entirely simulated, populates nothing; frontend mis-reads the payload
  shape anyway.
- Photo-to-rig: depends on unloaded YOLO model with an aspirational class map
  (`'traffic light': 'led_par'`); also AGPL-licensed (see 2.4).
- No zone concept in the persisted model — `group_name` free text only. Meanwhile the
  demo presets have a real `KeyZoneSpec` (DJ booth, stage center…) wired to key
  lighting. **A venue owner can't say "this light points at the singer"** — the most
  valuable non-expert input there is.
- ~1,530 lines of orphaned UI (TemplateGallery, ImportExportDialog, QRScanner,
  RDMDiscovery — none imported by any route).

### 2.3 Music intelligence (why it feels "good but not great")

Signal path today: WASAPI loopback → 2048-sample non-overlapping FFT at ~21.5 Hz →
hand-written onset/flux beat detector → threshold-ladder section detector →
`_update_fixtures_rebuild` at 60fps → ArtNet at 40fps. Electrical latency ~50–95 ms
(fine); the *perceived* lag comes from smoothing time-constants (τ ≈ 1–2.4 s on
mood/BPM) and the issues below.

Ranked weaknesses (all with file:line evidence in the audit):

1. **No clock is phase-locked to the music.** `bar_clock` and `beat_phase` derive from
   engine wall-time, never reset to a detected beat (`effects_engine.py:524,563,733`).
   Right tempo, arbitrary phase, continuous drift — "never on the one."
2. **Downbeat is fake**: `beat_position = (beat_position % 4) + 1` — a modulo counter
   phased off whichever onset was detected first (`audio_analyzer.py:401`).
3. **No loudness normalization/AGC.** All section thresholds are raw RMS numbers
   (`e>0.58` buildup, `e>0.64` chorus…). At normal mastering levels the show sits in
   "verse" forever; −6 dB of system volume = permanent "breakdown". The state machine
   is effectively a volume knob.
4. **Strobes are triple-disabled** (`main.py:82`, `audio.py:361`,
   `accessibility_mode="no_strobe"`), so drops have no accent at all. And if enabled,
   the live path's snare strobe can fire 6 bursts/sec indefinitely, bypassing the
   (dead) genre strobe budget.
5. **No anticipation.** Build-up detection and pre-drop blackout exist but route into
   the dead pro path. Drops land ~1.5 bars late as just `dimmer = energy`.
6. **Five competing section detectors; the crudest is live.** The best one
   (`section_manager.py:491` — EMA novelty, hysteresis, min-hold, drop refractory) is
   dead code. The live one has an ordering bug making `chorus` mostly unreachable.
7. **Frame-rate aliasing**: `is_beat` stays true ~3 engine frames → DecisionEngine bar
   counter runs 3× fast; breakdown look re-rolls `random.choice` 60×/sec; drop strobe
   retriggers every frame.
8. **Color is a timbre meter, not musical**: palette chosen by round-robin on silence
   gaps; "mood" = spectral centroid + band ratio; no chroma/key analysis anywhere.
9. **Movement vocabulary = 6 sine formulas** at 4–6% of pan/tilt range, selected by
   `bar_clock % len(pool)`. The good stuff (BEAM_LOOK_LIBRARY, pro movement presets,
   ballyhoo/fan/sweep) is unreachable.
10. **ML is aspirational**: BeatNet not installed, MERT path empty, allin1 absent,
    Essentia absent, YOLO path wrong. Everything runs on spectral heuristics.
    (The HuBERT model on disk is a *speech*-emotion model — don't route music to it.)
11. **Effective analysis rate is 21.5 Hz, not 86 Hz**: `AUDIO_HOP_LENGTH=512` is
    config-defined and never used; no overlapping STFT → ±23 ms beat quantization.
12. Analyzer sample rate never syncs to the device's native rate (44.1k assumed, 48k
    typical) → all band edges ~9% off.
13. No dynamics management on the live path (anti-fatigue scaler exists, never called;
    dimmer is a single scalar of energy, rig sits near full).
14. Hardcoded musical worldview: 4/4 only, 8-bar phrases, EDM section grammar, 5 genres
    (country/latin/DnB/metal/funk unrepresented; classifier confidence gate 0.48 vs
    typical winner ~0.2 means genre never auto-switches from the startup EDM default).

### 2.4 Architecture / commercial readiness

- **No failsafe**: audio thread exits permanently on device loss
  (`system_audio_capture.py:294-297`) — and post zero-floor refactor, no audio =
  **room goes black and stays black**. Graceful shutdown deliberately blacks out
  (`effects_engine.py:2567`). No ArtPoll node discovery/monitoring. No watchdog.
- **No auth at all** on 242 routes + 3 WS channels, bound to 0.0.0.0. Anyone on venue
  WiFi can strobe or blackout the room. Safety issue (photosensitive epilepsy), not
  just security.
- **AGPL-3.0 `ultralytics`** in requirements (only for the non-working photo-detect
  feature) — a commercial distribution blocker. BeatNet is CC-BY with non-commercial
  madmom models — also unshippable. README claims MIT license; no LICENSE file exists.
- **No packaging story**: four disagreeing launchers, three overlapping UIs, dev-mode
  docker-compose (with unused Redis/Postgres paths), a K8s deployment doc that's wrong
  for an appliance, `start.py` blocks on interactive input, frontend `dist/` stale and
  never mounted (`StaticFiles` imported, unused).
- **DMX transmitter shares the asyncio loop** with the 30fps WebSocket broadcast and
  all HTTP — blocking `sendto` + Windows 15.6 ms timer granularity = visible stutter
  under UI load.
- **Tests don't test the product**: the QA harness asserts hand-written literals
  satisfy thresholds (EffectsEngine never imported); conftest uses removed
  httpx/pytest-asyncio APIs; **CI has never run** (triggers on `main`/`develop`;
  repo branch is `master`).
- Migrations never run at startup; `is_active` rig flag is set by four writers and
  consumed by nobody; 59 MB of stray logs, two `nul` files, no logging config
  (everything is `print()`).
- Memory-note correction: the cross-platform audio + zero-floor work **is committed**
  (`47e8a15`), clean and coherent. One leftover: `main.py:115` still hardcodes
  `min_intensity=0.4` for DJ_BOOTH, contradicting the zero-floor default.

---

## 3. The roadmap

Ordering principle: **first make what exists true, then connect it, then make it
smart, then make it a product.** Phases 0–1 are prerequisites for everything else.

### Phase 0 — Stop the bleeding (foundation, ~days)
1. Fix the async-session bug across all 9 routers (convert to `select()`/`await`, or
   route them to `get_sync_db`). This single fix revives: wizard create, templates,
   auto-patch, conflict detection, MVR/console import, exports, QR, RDM endpoints,
   fixture tests, bundled-library sync.
2. Fix route-order shadowing of `batch-update` (`rigs.py:801`).
3. Run `alembic upgrade head` + bundled-fixture seed on startup; seed from
   `data/fixtures/bundled/` (all 50), not just the 2 top-level generics.
4. ArtNet: default to broadcast (or last-known unicast), surface a config UI, add
   ArtPoll discovery, make `/health` truthful, un-suppress send errors into a status
   flag the UI shows.
5. Point CI at `master`, fix conftest, make one smoke test that boots the app and
   completes wizard→rig→engine→DMX frame.
6. Remove `ultralytics` (+ the photo-detect endpoints for now), remove BeatNet/madmom
   from any install path, add a LICENSE file, fix the README claim.
7. Repo hygiene: delete stray logs/`nul` files, add log rotation via `logging` config.

### Phase 1 — Connect the spine (rig → profile → engine → DMX, ~1-2 weeks)
The single most valuable engineering step in the whole plan:
1. **Profile→engine adapter**: build engine `Fixture` objects from a DB rig
   (RigFixture + FixtureMode.channels → `{channel_type: offset}` map, per-fixture
   pan/tilt ranges, universe, address). Replace `create_demo_rig()` /
   `create_venue_rig()` as the engine's source; keep demo presets as *sample rigs*
   that go through the same adapter.
2. **Profile-driven rendering**: rewrite `get_dmx_frame` to emit every channel type
   the profile declares (CMY via RGB→CMY conversion, color wheel via nearest-slot
   from `value_ranges`, gobo/prism/zoom/focus defaults, real strobe channel
   semantics, 16-bit where fine channels exist, per-fixture pan/tilt scaling).
3. **Multi-universe output**: iterate all universes with patched fixtures; lift the
   16-universe schema cap; pack Net/SubNet properly.
4. **Persist and honor the active rig** across restarts; delete the boot-time
   `pro_beam_room` override; make the WebSocket reactive path use the engine rig
   (delete the hardcoded address lists).
5. Move DMX TX to a dedicated thread with a precise timer.

### Phase 2 — "Buy any light" fixture pipeline (~1-2 weeks)
1. Fix GDTF parser: honor `Offset` (16-bit footprints, correct numbering,
   coarse/fine pairing), namespace handling, CMY/iris/frost/CTO/gobo2 types, read
   `ChannelSet` → `value_ranges`, read per-geometry pan/tilt ranges.
2. Rewrite OFL client against the real API (`POST /get-search-results`), convert
   `fineChannelAliases` correctly, surface errors; fix the frontend result shape.
3. Wire the frontend: enable the import option, connect GDTF upload to the real
   endpoint (`POST /api/fixtures/import/gdtf`), real server-side preview.
4. Derive `fixture_capabilities` from the actual channel list, not a 4-entry table.
5. Extend ChannelType + add multi-wheel support and (later) pixel/cell modeling.
6. Later: GDTF Share integration (account-based download), profile request flow
   ("can't find your light? request it"), community profile sharing.

### Phase 3 — Venue layouts for normal humans (~2 weeks)
Recommended implementation (simplest that works, reusing what exists):
1. **Fix the wizard end-to-end** — it's already the right shape (venue type → stage
   size → fixtures → review). Make step 3 search the full library (with "closest
   match" suggestions instead of exact type-string matching and a silent disabled
   button), unify the Z coordinate convention, replace the group-name heuristic with
   explicit mounting positions (front truss / back truss / floor / side / ceiling
   grid), compute rotations, show the real 2D preview in review.
2. **Zones as a first-class concept**: stage left/center/right, DJ booth, dance
   floor, bar, audience — picked by tapping a floor-plan diagram. Wire zones to the
   existing KeyZoneSpec/key-lighting machinery so "keep the singer lit" works for
   every rig, not just demo presets.
3. **2D floor-plan editor that saves**: persist drags (batch-update endpoint), wire
   palette drag-drop, keep it top-down 2D (venue owners think in floor plans, not 3D).
4. **Flash-to-identify walkthrough** (the killer feature for non-experts): the app
   flashes each patched fixture in turn (fixture_test_service already does this);
   the owner taps where that light is on the floor plan. Physical layout mapped with
   zero DMX knowledge. Same flow doubles as "verify my patch."
5. Seed 8–10 venue templates (bar, small club, church, band stage…) through the same
   pipeline; template gallery already exists.
6. Drop QR/RDM/photo-detect from the near-term story (QR needs a decoder lib; RDM
   needs hardware work; photo-detect needs a licensed model). Revisit post-launch.

### Phase 4 — Intelligence overhaul (~2-4 weeks, biggest musical payoff first)
1. **AGC / loudness normalization** feeding all thresholds (running percentile or
   LUFS-style); per-venue input trim in UI. Single biggest musical fix.
2. **Phase-lock the clocks**: reset beat/bar phase on detected beats; estimate
   downbeat from bass-onset periodicity + novelty (replace the modulo counter).
   Changes land *on the one*.
3. **One section detector**: promote `section_manager.detect_section_from_energy`
   (hysteresis, min-hold, refractory) to the live path; delete/merge the other four.
4. **Re-enable accents safely**: strobe via the genre budget + venue safety governor
   (Hz cap, duty cycle, audience cap — machinery already exists); pre-drop
   dip/blackout and build ramps wired into the live path.
5. **Un-dead the pro path**: either remove the early return and make the pro modules
   the renderer, or (recommended) port the best pieces — beam look library, pro
   movement presets, key-light override, LFO, MIB, anti-fatigue dynamics — into the
   rebuild renderer incrementally, behind tests.
6. Fix per-frame retrigger/aliasing bugs (edge-trigger `is_beat`, once-per-state
   decisions).
7. Overlapping STFT at hop 512 (config value already exists); sync analyzer sample
   rate to the capture device.
8. Color musicality: section-contrast palettes, complementary accents on drops;
   later, lightweight chroma→key detection to tint palettes.
9. Later (license-clean): modern beat/downbeat model (e.g. beat_this), structure
   segmentation, real genre model with an expanded genre→profile map.
10. Regression harness: canned audio WAVs → run the *real* engine → assert DMX frame
    properties (beat alignment, strobe budget, blackout policy). Replaces the
    tautological QA harness.

### Phase 5 — Appliance & commercialization (~3-4 weeks, parallelizable)
1. One process: FastAPI serves the built React app; kill the standalone visualizer
   servers (fold previs into the React app; it already renders DB rigs correctly).
2. One launcher → installed service (WinSW/NSSM on Windows; systemd on a future
   Pi/mini-PC image), auto-start, auto-restart, bundled Python runtime.
3. **Failsafe & watchdog** (mandatory given zero-floor): audio-loss → hold an ambient
   look + auto-reconnect loop; crash → DMX hold-last-look policy; explicit
   house-lights button; never black the room as a side effect.
4. Auth (even a device PIN + operator token), plus the strobe/intensity safety
   governor enforced server-side.
5. sACN output alongside ArtNet; per-universe destinations.
6. Licensing/entitlement, crash telemetry, structured logs, signed updates.
7. Simple mode UI: one screen — rig picker, START button, energy/vibe dial,
   house-lights, blackout. The 242-route surface stays as "advanced".

---

## 4. Go-to-market recommendation

**Start with small venues (bars, small clubs, churches, mobile DJs/bands) — but the
architecture above removes all venue-size ceilings.** Reasons:

- Small venues are the underserved buyer ("avoiding paying for a lighting operator" is
  literally their situation; large venues already have LDs and consoles).
- One-universe rigs (8–40 fixtures) are the current de facto working envelope; Phase 1
  removes the ceiling, but polish for big rigs (fan/spread choreography across 50+
  movers, multi-node output health) is Phase 4/5 material.
- An appliance + simple-mode story sells to a bar owner; a GrandMA-replacement story
  invites feature-comparison against consoles you won't win yet.
- Like GrandMA, nothing in the software should *limit* venue size — after Phase 1
  (multi-universe, profile-driven) and Phase 5 (sACN, watchdogs), the same product
  scales up. Sell small first, grow with reference installs.

## 5. Success gates

- **Gate A (after Phase 1):** wizard → real rig → music-reactive DMX on *user*
  addresses across ≥2 universes, verified on hardware. This is "the product exists."
- **Gate B (after Phase 3):** a non-expert can go box-to-beams in under 30 minutes
  without reading docs (fixture search → flash-to-identify → START).
- **Gate C (after Phase 4):** A/B against today's build on 10 tracks across 6 genres —
  changes land on the one, drops visibly hit, quiet songs look quiet.
- **Gate D (after Phase 5):** unplug audio mid-show → room holds ambient look and
  recovers; kill the process → lights hold; reboot → same rig, same show.
