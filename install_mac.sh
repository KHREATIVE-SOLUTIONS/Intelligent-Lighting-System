#!/bin/bash
# ============================================================
#  Intelligent Lighting System - Mac Dependency Installer
# ============================================================
set -e

echo "============================================================"
echo "  Intelligent Lighting System - Mac Setup"
echo "============================================================"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"

# -----------------------------------------------------------
# 1. Check for Homebrew
# -----------------------------------------------------------
if ! command -v brew &>/dev/null; then
    echo "[!] Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "[✓] Homebrew found"
fi

# -----------------------------------------------------------
# 2. Install system-level dependencies via Homebrew
# -----------------------------------------------------------
echo ""
echo "[1/5] Installing system dependencies..."

# PortAudio is required for PyAudio (audio capture)
if ! brew list portaudio &>/dev/null 2>&1; then
    echo "  Installing portaudio..."
    brew install portaudio
else
    echo "  [✓] portaudio already installed"
fi

# Python 3 (in case they only have system Python)
if ! command -v python3 &>/dev/null; then
    echo "  Installing python3..."
    brew install python@3.11
else
    echo "  [✓] python3 found: $(python3 --version)"
fi

# -----------------------------------------------------------
# 3. Create virtual environment
# -----------------------------------------------------------
echo ""
echo "[2/5] Setting up Python virtual environment..."

if [ -d "$VENV_DIR" ]; then
    echo "  [✓] Virtual environment already exists at $VENV_DIR"
else
    echo "  Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    echo "  [✓] Virtual environment created"
fi

# Activate venv
source "$VENV_DIR/bin/activate"
echo "  Using Python: $(which python)"
echo "  Python version: $(python --version)"

# Upgrade pip
echo "  Upgrading pip..."
pip install --upgrade pip --quiet

# -----------------------------------------------------------
# 4. Install Python packages (essentials only - no ML/AI)
# -----------------------------------------------------------
echo ""
echo "[3/5] Installing Python packages..."

echo "  Installing core framework..."
pip install --quiet \
    "fastapi==0.109.0" \
    "uvicorn[standard]==0.27.0" \
    "pydantic==2.5.3" \
    "pydantic-settings==2.1.0"

echo "  Installing database drivers..."
pip install --quiet \
    "sqlalchemy==2.0.25" \
    "aiosqlite==0.19.0" \
    "alembic==1.13.1"

# asyncpg and psycopg2 are for PostgreSQL - install but don't fail if they can't build
echo "  Installing PostgreSQL drivers (optional)..."
pip install --quiet "asyncpg==0.29.0" 2>/dev/null || echo "    [!] asyncpg skipped (needs PostgreSQL - not critical)"
pip install --quiet "psycopg2-binary==2.9.9" 2>/dev/null || echo "    [!] psycopg2-binary skipped (not critical)"

echo "  Installing audio processing..."
pip install --quiet \
    "numpy==1.26.3" \
    "scipy==1.12.0" \
    "librosa==0.10.1"

echo "  Installing PyAudio..."
pip install --quiet "pyaudio" || {
    echo "    [!] PyAudio failed. Trying with portaudio path..."
    CFLAGS="-I$(brew --prefix portaudio)/include" \
    LDFLAGS="-L$(brew --prefix portaudio)/lib" \
    pip install --quiet "pyaudio"
}

echo "  Installing networking & utilities..."
pip install --quiet \
    "websockets==12.0" \
    "python-multipart==0.0.6" \
    "python-dotenv==1.0.0" \
    "httpx==0.26.0" \
    "aiofiles==23.2.1" \
    "aiohttp>=3.9.0" \
    "redis==5.0.1" \
    "aioredis==2.0.1"

echo "  Installing MIDI support..."
pip install --quiet "mido" "python-rtmidi" 2>/dev/null || echo "    [!] MIDI packages skipped (not critical)"

# -----------------------------------------------------------
# 5. Install BlackHole for system audio capture
# -----------------------------------------------------------
echo ""
echo "[4/5] Checking for BlackHole (system audio capture)..."

if brew list blackhole-2ch &>/dev/null 2>&1; then
    echo "  [✓] BlackHole 2ch already installed"
else
    echo "  BlackHole lets you capture system audio (YouTube, Spotify, etc.)"
    echo "  Installing blackhole-2ch..."
    brew install blackhole-2ch 2>/dev/null || {
        echo "  [!] Could not auto-install BlackHole."
        echo "      Install manually: brew install blackhole-2ch"
        echo "      Or download from: https://existential.audio/blackhole/"
    }
fi

# -----------------------------------------------------------
# 6. Verify installation
# -----------------------------------------------------------
echo ""
echo "[5/5] Verifying installation..."

python -c "
import sys
packages = {
    'fastapi': 'fastapi',
    'uvicorn': 'uvicorn',
    'pydantic': 'pydantic',
    'pydantic_settings': 'pydantic-settings',
    'sqlalchemy': 'sqlalchemy',
    'numpy': 'numpy',
    'scipy': 'scipy',
    'librosa': 'librosa',
    'websockets': 'websockets',
    'aiofiles': 'aiofiles',
    'pyaudio': 'pyaudio',
}
ok = True
for mod, name in packages.items():
    try:
        __import__(mod)
        print(f'  [✓] {name}')
    except ImportError:
        print(f'  [✗] {name} - MISSING')
        ok = False

if ok:
    print()
    print('  All essential packages installed!')
else:
    print()
    print('  Some packages are missing - check errors above')
    sys.exit(1)
"

# -----------------------------------------------------------
# Done!
# -----------------------------------------------------------
echo ""
echo "============================================================"
echo "  Setup complete!"
echo "============================================================"
echo ""
echo "  To start the system:"
echo "    cd $PROJECT_DIR"
echo "    python start.py"
echo ""
echo "  For system audio capture (YouTube/Spotify):"
echo "    1. Open Audio MIDI Setup (Spotlight: 'Audio MIDI Setup')"
echo "    2. Click '+' at bottom left → Create Multi-Output Device"
echo "    3. Check both your speakers AND BlackHole 2ch"
echo "    4. Set the Multi-Output Device as your system output"
echo "       (System Settings → Sound → Output → Multi-Output Device)"
echo "    5. In start.py, select BlackHole as the input device"
echo ""
echo "============================================================"
