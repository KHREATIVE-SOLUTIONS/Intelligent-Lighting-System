#!/bin/bash
echo "========================================"
echo "Intelligent Lighting System"
echo "Audio Capture for Reactive Lighting"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_PYTHON="$ROOT_DIR/backend/venv/bin/python"

if [ -x "$BACKEND_PYTHON" ]; then
    PYTHON_EXE="$BACKEND_PYTHON"
    echo "Using backend virtual environment Python:"
    echo "  $PYTHON_EXE"
else
    if ! command -v python3 &> /dev/null; then
        echo "Error: Python 3 is not installed or not in PATH"
        echo "Please install Python 3.9+ (brew install python3)"
        exit 1
    fi
    PYTHON_EXE="python3"
    echo "Using system Python from PATH."
fi

# Install dependencies if needed
echo "Checking dependencies..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: need portaudio for pyaudio
    if ! brew list portaudio &> /dev/null 2>&1; then
        echo "Installing portaudio (required for audio capture on macOS)..."
        brew install portaudio
    fi
    # Use regular pyaudio on macOS (not pyaudiowpatch which is Windows-only)
    $PYTHON_EXE -c "import pyaudio" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "Installing pyaudio..."
        $PYTHON_EXE -m pip install pyaudio
    fi
else
    # Linux
    $PYTHON_EXE -c "import pyaudio" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "Installing pyaudio..."
        $PYTHON_EXE -m pip install pyaudio
    fi
fi

$PYTHON_EXE -c "import numpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing numpy..."
    $PYTHON_EXE -m pip install numpy
fi

$PYTHON_EXE -c "import websockets" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing websockets..."
    $PYTHON_EXE -m pip install websockets
fi

echo ""
echo "========================================"
echo "Starting Audio Capture"
echo "========================================"
echo ""
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macOS detected. For system audio capture,"
    echo "install BlackHole: brew install blackhole-2ch"
    echo "Then select BlackHole as the input device."
    echo ""
fi
echo "Play music and the lights will react!"
echo "Press Ctrl+C to stop."
echo ""

$PYTHON_EXE "$SCRIPT_DIR/audio_capture.py"
