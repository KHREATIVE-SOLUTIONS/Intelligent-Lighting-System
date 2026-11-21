@echo off
REM Intelligent Lighting System - starts everything. All options go to start.py:
REM   start.bat --check      start.bat --dry-run      start.bat --no-ui
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%backend\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%ROOT%start.py" %*
exit /b %ERRORLEVEL%
