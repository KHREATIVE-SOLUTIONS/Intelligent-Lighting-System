@echo off
echo ========================================
echo Intelligent Lighting System
echo Audio Capture for Reactive Lighting
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
set BACKEND_PYTHON=%ROOT_DIR%\backend\venv\Scripts\python.exe

if exist "%BACKEND_PYTHON%" (
    set PYTHON_EXE=%BACKEND_PYTHON%
    echo Using backend virtual environment Python:
    echo   %PYTHON_EXE%
) else (
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo Error: Python is not installed or not in PATH
        echo Please install Python 3.9+ from https://python.org
        pause
        exit /b 1
    )
    set PYTHON_EXE=python
    echo Using system Python from PATH.
)

REM Install dependencies if needed
echo Checking dependencies...
%PYTHON_EXE% -m pip show pyaudiowpatch >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pyaudiowpatch...
    %PYTHON_EXE% -m pip install pyaudiowpatch
)

%PYTHON_EXE% -m pip show numpy >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing numpy...
    %PYTHON_EXE% -m pip install numpy
)

%PYTHON_EXE% -m pip show websockets >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing websockets...
    %PYTHON_EXE% -m pip install websockets
)

echo.
echo ========================================
echo Starting Audio Capture
echo ========================================
echo.
echo Play music (YouTube, Spotify, etc.) and
echo the lights will react to the audio!
echo.
echo You will be prompted to choose a specific audio device.
echo Press Ctrl+C to stop.
echo.

%PYTHON_EXE% "%SCRIPT_DIR%audio_capture.py"

pause
