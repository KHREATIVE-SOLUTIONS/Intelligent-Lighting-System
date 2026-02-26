@echo off
echo ========================================
echo Intelligent Lighting System - Full Stack
echo ========================================
echo.

REM Get the script directory
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..

echo [1/3] Starting Backend API Server (port 8000)...
cd /d "%ROOT_DIR%\backend"
start "ILS Backend" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo Waiting for backend to start...
timeout /t 3 /nobreak > nul

echo [2/3] Starting Frontend Dashboard (port 5173)...
cd /d "%ROOT_DIR%\frontend"
start "ILS Frontend" cmd /k "npm run dev -- --host 0.0.0.0 --port 5173"

echo Waiting for frontend to start...
timeout /t 2 /nobreak > nul

echo [3/3] Starting Audio Capture...
cd /d "%ROOT_DIR%\scripts"
start "ILS Audio Capture" cmd /k "python audio_capture.py"

echo.
echo ========================================
echo All services starting!
echo ========================================
echo.
echo Backend API:    http://localhost:8000
echo API Docs:       http://localhost:8000/docs
echo Dashboard:      http://localhost:5173
echo Debug Pipeline: http://localhost:8000/api/effects/debug/pipeline
echo.
echo Opening dashboard in browser...
timeout /t 2 /nobreak > nul
start http://localhost:5173

echo.
echo Press any key to open debug pipeline endpoint...
pause > nul
start http://localhost:8000/api/effects/debug/pipeline
