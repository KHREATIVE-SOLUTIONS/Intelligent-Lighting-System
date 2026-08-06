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

# Frontend: http://localhost
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Development

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install && npm run dev
```

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
