# Intelligent Lighting System

A real-time intelligent lighting engine for EDM, designed to control professional DMX rigs through deep musical analysis. No hardcoded rules — everything is driven by musical intelligence feeding a tag-based look library with weighted random selection.

Built for a 44-fixture bigroom rig. Controlled via Docker Compose.

## Architecture (v0.2)

The system is organized around clear ownership — each service answers one question and does it well.

### Audio Intelligence Pipeline

**DrumIntelligence** — "What are the drums doing?"
The backbone of EDM understanding. Analyzes kick patterns (four-on-floor, half-time, sparse, absent), snare presence and rolls, hi-hat density/openness/acceleration, overall drum power, groove tightness, and fill detection. Outputs continuous 0-1 dimensions updated every frame. Kick return after absence is the single strongest drop signal in electronic music.

**SpectralIntelligence** — "What kind of sound is playing?"
Understands the character of what's happening beyond frequency bands. Computes spectral shape (brightness, spread, flatness, tilt), onset texture (attack sharpness, sustain level, transient density), and harmonic content (tonality, complexity, pitch stability). Derives composite characters like melodic intensity, wall of sound, ethereal, aggressive, and rising. Prevents misclassifying a loud supersaw solo as a breakdown just because the drums dropped out.

**AudioIntelligence** — "How intense is this moment?"
Tracks energy trajectory (building, sustaining, falling, anticipation), timbral mood (brightness, warmth, noisiness), rhythmic state, and detects events like risers, impacts, and sweeps. Provides a continuous intensity signal that modulates within sections.

**MusicalIntelligence** — "What should this look like?"
Six continuous dimensions: drive, density, ambiance, dominant element, element activity, and texture (tonal vs noisy, percussive vs sustained). Feeds the look library for mood-appropriate aesthetic selection — color palettes, movement styles, chase patterns.

### Section Detection

**SectionDetector** — "Where are we in the song?"
The sole authority on song structure. Drums are the primary signal (65% weight), AudioIntelligence confirms (20%), MusicalIntelligence tiebreaks verse vs chorus (15%), SpectralIntelligence applies corrective adjustments for melodic moments. Features adaptive EMA smoothing (faster when drums are clear), kick-return instant override, drum-clarity-gated minimum dwell times, and a confidence-gated state machine with boundary confirmation.

**StructurePredictor** — "What's coming next?"
Learns within-song patterns to anticipate transitions. Tracks riser progress, bar-level pattern memory, and predicts upcoming drops to lower detection thresholds before they hit.

### Effects Execution

**EffectsEngine** — The executor. Receives section, mood, and intensity as facts, picks looks from the library, and drives 44 fixtures through the dimmer pipeline. Does not make structure decisions.

**LookLibrary** — 67 tag-based look presets selected by weighted random matching against current musical state. Each look specifies dimmer effect, movement pattern, chase parameters, strobe mode, bump style, color character, and fixture group isolation. No look is hardcoded to a section — any look can play anywhere if the tags match.

### Dimmer Philosophy

Fixtures default to dark. Light is always intentional. Every fixture needs an active dimmer effect to produce output:

- **static** — steady glow at section brightness (the "wash" look)
- **chase** — traveling gaussian spotlight across the rig
- **odd_even** — alternating fixtures on beat
- **kick_clap** — odd/even fixtures fire on kick vs snare from actual drum hits
- **left_right_kick** — left/right rig split on kick vs snare
- **circular** — rotating spotlight
- **ramp** — progressive sweep

No effect means blackout. Additive layers (bumps, onset flashes, impact hits) only fire on fixtures the dimmer effect has lit, preserving chase contrast.

## Stack

| Service | Tech | Port |
|---------|------|------|
| Backend API | Python / FastAPI | 8000 |
| Frontend | TypeScript / React / Vite | 80 |
| Database | PostgreSQL 15 | 5432 |
| Cache | Redis 7 | 6379 |
| DMX Output | ArtNet (UDP) | 6454 |

## Quick Start

```bash
# Clone
git clone https://github.com/KHREATIVE-SOLUTIONS/Intelligent-Lighting-System.git
cd Intelligent-Lighting-System

# Run
docker-compose up -d

# Frontend: http://localhost  (also http://<this-machine's-ip> from a tablet)
# Backend API: http://localhost:8000  (this machine only)
# API Docs: http://localhost:8000/docs
```

The operator login is on by default; the first visit asks you to set a password.
For local development (login off, hot reload, database on 127.0.0.1:5432):

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

## Start everything

One command starts the backend and the operator UI, waits until both answer,
and prints the operator URL. Ctrl+C stops both. It needs no internet.

```bash
python start.py          # or start.bat on Windows, sh start.sh on macOS/Linux
```

| Option | What it does |
|--------|--------------|
| `--check` | Preflight only: Python and packages, UI packages, free ports, writable data folder. Lists every problem with the command that fixes it; exits non-zero if there is one. |
| `--dry-run` | Prints the exact commands a start would run, then exits. |
| `--backend-port N` / `--ui-port N` | Ports (default 8000 and 5173). The UI is pointed at the backend port you give. |
| `--no-ui` | Backend only. |
| `--ui-mode dev\|preview` | By default the built app in `frontend/dist` is served if it exists, otherwise the Vite dev server. |
| `--host 0.0.0.0` | Listen on the network so a tablet can open the UI (default is this machine only). |
| `--audio` | Also feed this machine's audio to the backend (`--device "Main Out"`, `--rig-id N`). Otherwise pick the audio device in the UI. |
| `--open` | Open the operator screen in a browser. |

The first time, install the packages (this is the one step that needs
internet): see Development below, or run `scripts\run_dev.bat` on Windows.
The launcher never installs anything and never sets the output target:
`ARTNET_IP` comes from `backend/.env` or the environment, and `--check` shows
which address is in effect. If the UI stops, the backend keeps running.

## Installing at a Venue

Pick one of three ways, by machine:

- **Windows or macOS (recommended): run natively.** Install the backend and
  UI packages (see Development below), then `python start.py` (see Start
  everything above). Without a `.env` it keeps its database in
  `backend/data/lighting.db`. To capture audio from the box and sign the feed
  in without anyone at the keyboard, add the audio feed and name the device:
  `python start.py --audio --device "Main Out"` (or set `ILS_AUDIO_DEVICE`).
  A failed start stops everything it started.
- **Linux: Docker with the venue file.** It puts the backend on the host
  network, so Art-Net broadcast reaches the lights, and gives it the box's
  sound card:

  ```bash
  cp docker-compose.venue-linux.example.yml docker-compose.override.yml
  docker compose up -d
  ```

- **Docker on Windows or macOS.** Docker Desktop gives containers no LAN
  broadcast and no audio devices. Set `ARTNET_IP` to your Art-Net node's IP
  (unicast works), then send audio from the host with
  `scripts/audio_capture.py`. It needs an operator token in `ILS_TOKEN`.

Patch the venue's rig in the app and activate it. Until then, the built-in
demo rig drives the visualizer but nothing is sent to the network.
`ILS_RIG_ID` pins the audio feed (`start.py --audio`), the visualizer or the capture script to one rig;
otherwise they follow the active rig.

### Choosing the audio input

The backend captures audio itself, from the device picked in the **Audio
Device** chooser on the Dashboard. It lists two groups:

- **Inputs (line-in, USB interface, mixer, mic)**: music that arrives on a
  cable, such as the desk or DJ mixer into a USB interface, a mixer's USB
  return, or the sound card's line-in.
- **This computer's audio (loopback)**: whatever this computer is playing.
  Use it when the music is played on the box itself.

Nothing is captured until **Start Capture** is pressed. On Windows, loopback
is still the default: until a device has been picked once, the chooser opens
on the loopback device, and a line-in is used only when you pick it.
(`AUDIO_CAPTURE_AUTO_START=true` starts without a pick, and on Windows that
also tries loopback first.)

To use a line-in or USB interface on Windows:

1. Plug the interface in and feed it from the desk. In Windows *Settings >
   System > Sound > Input*, check that it is listed, enabled and its meter
   moves. A line-in with nothing plugged in is often hidden until it is.
2. In the Dashboard, tap the refresh button next to **Audio Device**, pick the
   interface under **Inputs**, and press **Start Capture**.
3. The chip next to the button shows the signal level. "No input signal" means
   the box hears silence: check the cable, the interface's gain and the
   Windows input level.

Each input is listed once. Windows exposes the same input through several
drivers; the chooser shows the WASAPI one, and the box refuses kernel-streaming
(WDM-KS) and ASIO entries, because those take the device away from other
programs. Inputs are opened in shared mode, so DJ software and other programs
keep using the interface. If the input will not open at the analysis rate, the
box follows the rate Windows runs the device at (usually 48 kHz).

The choice is remembered on the box, in `audio_capture.json` next to the
database, by device name and driver rather than by number, so it survives a
replug or a reboot. The chooser reopens on it from any browser. If capture was
running when the box went down, it restarts on the same device at boot and
keeps retrying until the interface appears; if it was stopped, it stays
stopped.

`python start.py` has its own capture path with its own `--device` list, which
on Windows offers loopback devices only. For a line-in, pick it in the
Dashboard chooser as above.

## Development

Install once:

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

Then `python start.py` from the project root. To run the two halves by hand
(hot reload on the backend): `uvicorn app.main:app --reload` in `backend`,
`npm run dev` in `frontend`.

## Versioning

- **v0.2** (current) — Intelligence-driven architecture, drum-primary section detection, SpectralIntelligence, dimmer-as-effect philosophy
- **v0.1** — Lyric-aware busking engine with mood-driven lighting

Rollback: `git checkout v0.1`

## Key Files

```
backend/app/services/audio/
  drum_intelligence.py        # Kick/snare/hat pattern analysis
  spectral_intelligence.py    # Sound character understanding
  audio_intelligence.py       # Energy trajectory and events
  musical_intelligence.py     # Mood and aesthetic dimensions
  section_detector.py         # Song structure state machine
  structure_predictor.py      # Anticipatory transition prediction
  audio_analyzer.py           # FFT, beat detection, band extraction
  vocal_analyzer.py           # Vocal cadence detection

backend/app/services/effects/
  effects_engine.py           # Main executor — fixtures, dimmer pipeline
  look_library.py             # 67 tag-based look presets
  color_mapper.py             # Mood-to-color mapping
  movement_patterns.py        # Pan/tilt choreography
  dimmer_effects.py           # Chase, kick_clap, etc.
  gobo_engine.py              # Gobo wheel control
  lfo_engine.py               # Low-frequency oscillator effects
  strobe_controller.py        # Strobe timing and modes
```
