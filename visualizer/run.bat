@echo off
echo Starting ILS Visualizer...
echo.
echo Web UI: http://localhost:8080
echo Art-Net: Listening on port 6454
echo.
cd /d "%~dp0"
python server.py
pause
