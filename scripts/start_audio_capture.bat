@echo off
echo ========================================
echo Intelligent Lighting System
echo Audio Capture for Reactive Lighting
echo ========================================
echo.

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
pip show sounddevice >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing sounddevice...
    pip install sounddevice
)

pip show websockets >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing websockets...
    pip install websockets
)

pip show aiohttp >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing aiohttp...
    pip install aiohttp
)

echo.
echo ========================================
echo Starting Audio Capture
echo ========================================
echo.
echo Play music (YouTube, Spotify, etc.) and
echo the lights will react to the audio!
echo.
echo Press Ctrl+C to stop
echo.

python "%~dp0audio_capture.py"

pause
