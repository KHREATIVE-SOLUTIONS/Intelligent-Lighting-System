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

1. **BeatNet** - Real-time beat detection
2. **HuBERT** - Emotion/mood classification
3. **YOLOv9** - Fixture detection (optional)

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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
