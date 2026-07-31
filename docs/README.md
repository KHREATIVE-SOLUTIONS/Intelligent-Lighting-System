# Intelligent Lighting System

An emotionally intelligent lighting control system that uses real-time audio analysis to generate dynamic lighting shows.

## Features

- **Real-Time Audio Analysis**
  - Beat detection using BeatNet neural network
  - Mood classification using HuBERT transformer
  - Frequency band analysis with spectral features
  - Audio fingerprinting for song recognition

- **Show Generation**
  - Emotion-to-lighting color mapping
  - Beat-synchronized effects
  - Multi-track show programming
  - Real-time audio-reactive cues

- **DMX Control**
  - ArtNet protocol support
  - Multi-universe output
  - Fixture library with GDTF support
  - Real-time cue execution

- **3D Visualization**
  - Three.js-powered stage visualization
  - Real-time fixture preview
  - Interactive rig editor

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for development)
- Python 3.11+ (for development)

### Running with Docker

```bash
# Clone the repository
git clone https://github.com/yourusername/intelligent-lighting.git
cd intelligent-lighting

# Start all services
docker-compose up -d

# Access the application
# Frontend: http://localhost
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Development Setup

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up database
alembic upgrade head

# Run development server
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

## The operator password

The lighting box asks for one password. There are no user accounts and no email
addresses - one venue, one password, and anything you can reach the lights with
needs it.

### Switching a new box on for the first time

The very first time the box runs, nobody has a password yet, so the box prints a
**setup code** in its console window. It looks like this:

```
=================================================================
 LIGHTING BOX FIRST RUN - no operator password is set yet.
 Setup code: K5SZ-69SN-CCWH
 Open the lighting page and enter this code to choose a password.
 It is valid until this box restarts, and once a password is set
 it stops working.
=================================================================
```

Open the lighting page, type that code in, and choose your password. The code is
only good until you use it or until the box restarts, and it only exists while
no password is set. Asking for it is what stops the first person who finds the
box on your wifi from claiming it.

You can use a short PIN if that suits you better than a phrase - four characters
is the minimum.

### Changing the password

Sign in, open the password screen, type the current password once and the new one
once. You stay signed in afterwards.

### If you forget the password

You do **not** need to phone anybody. You need to be standing at the machine the
lighting box runs on - that is the whole point, it cannot be done over the
network.

1. Open the folder that holds the lighting database file `lighting_dev.db`. On a
   normal install that is the `backend` folder. (The same folder holds the `logs`
   folder and a file called `secret_key`, so you know you are in the right place.)
2. Make an empty file in that folder called **RESET-PASSWORD**. On Windows:
   right-click in the folder, choose *New > Text Document*, and name it
   `RESET-PASSWORD`. It does not matter if Windows adds `.txt` on the end, and
   capital letters do not matter.
3. Reload the lighting page in your browser.

The box is now back to how it was on day one: it forgets the old password, deletes
the `RESET-PASSWORD` file so it does not keep doing this, and prints a fresh setup
code in its console window. Use that code to choose a new password, exactly like
the first time. Your shows, rigs and fixture patch are untouched - only the
password is cleared.

If you would rather do it from a command line, set the environment variable
`RESET_OPERATOR_PASSWORD=1` and start the box:

```bash
# Windows PowerShell
$env:RESET_OPERATOR_PASSWORD = "1"; uvicorn app.main:app

# macOS / Linux
RESET_OPERATOR_PASSWORD=1 uvicorn app.main:app
```

Clear that variable again afterwards, or every restart will wipe the password.

### If you think somebody else is still signed in

Resetting the password does not by itself kick out a laptop or phone that was
already signed in - it keeps working until it is signed out or the sign-in expires
after 30 days. To throw everybody off at once:

1. Delete the file called `secret_key` in that same folder.
2. Restart the lighting box.

Everyone, including you, is signed out and has to type the password again. The box
makes itself a new `secret_key` on the way up.

### Too many wrong tries

Five wrong passwords in a row from the same computer, and the sixth try is made to
wait - 15 seconds, then 30, then a minute, doubling up to a five minute ceiling.
Getting it right clears the slate for that computer. Every wrong try is written to
the log with the address it came from.

Two things are deliberate here. The wait is counted **per computer**, so somebody
guessing at the password from the corner of the room cannot stop you signing in
from behind the bar. And the wait never grows past five minutes, so even in the
worst case - your laptop and theirs sharing one address through a router - the
longest you are ever kept out is five minutes. If you cannot wait, the reset above
clears the waiting list too.

## Architecture

```
┌─────────────────────────────────────────┐
│   React Frontend (Dashboard + Editor)   │
│   WebSocket + REST API Client           │
└─────────────┬───────────────────────────┘
              │ WebSocket & REST
┌─────────────▼───────────────────────────┐
│  FastAPI Backend                        │
│  ├─ Audio Analysis (Beat, Mood, Freq)   │
│  ├─ Show Generator (Emotion → Lighting) │
│  ├─ DMX Controller (ArtNet output)      │
│  └─ Database (Shows, Rigs, Analysis)    │
└─────────────┬───────────────────────────┘
              │ DMX/ArtNet
┌─────────────▼───────────────────────────┐
│  Stage Lighting Hardware                │
│  (Moving Heads, LEDs, Spots, etc)       │
└─────────────────────────────────────────┘
```

## API Documentation

- **OpenAPI/Swagger**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

Every route under `/api` and all three WebSocket channels need an operator token,
except `GET /health`, the docs, and the three sign-in routes below.

- `GET /api/auth/status` - `{configured, authenticated}`; drives the login vs
  first-run screen. Never returns the setup code.
- `POST /api/auth/setup` - `{setup_code, password}`; first run only
- `POST /api/auth/login` - `{password}` -> `{token, token_type, expires_at}`
- `POST /api/auth/logout` - ends the session on this device
- `POST /api/auth/change-password` - `{current_password, new_password}`
- `GET /api/shows` - List all shows
- `POST /api/shows` - Create a new show
- `GET /api/rigs` - List all rigs
- `WS /ws/audio` - Real-time audio streaming
- `WS /ws/dmx` - Real-time DMX updates

## Configuration

Environment variables (`.env`):

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/lighting_db
REDIS_URL=redis://localhost:6379
ARTNET_IP=0.0.0.0
ARTNET_PORT=6454
DMX_UNIVERSE=0
DMX_FPS=40
```

## ML Models

The system uses three ML models:

1. **BeatNet** - Real-time beat detection (optional extra, not bundled; falls back to librosa beat tracking)
2. **HuBERT** - Emotion/mood classification
3. **YOLOv9** - Fixture detection (optional extra, not bundled; detection endpoints return 503 without it)

See `ml_models/*/config.yaml` for download instructions.

## Testing

```bash
# Backend tests
cd backend
pytest tests/ -v

# Frontend tests
cd frontend
npm test
```

## Quality Assurance

- [Beam Operator QA Plan](./BEAM_OPERATOR_QA_PLAN.md)
- [Diagnostic Show Regression Mode](./DIAGNOSTIC_SHOW_MODE.md)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

Proprietary. Copyright (c) 2026 Alexander Kinghorn. All Rights Reserved.
See the [LICENSE](../LICENSE) file at the repository root for the full terms.

Third-party dependencies remain under their own licenses. Copyleft-licensed
optional extras (`ultralytics`, AGPL-3.0; `BeatNet`/`madmom`, CC-BY-4.0 and
non-commercial models) are deliberately **not** bundled - see the notes in
`backend/requirements.txt` before installing them.
