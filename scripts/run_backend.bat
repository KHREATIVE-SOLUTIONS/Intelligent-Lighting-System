@echo off
REM Backend only. Same launcher as start.bat, without the UI.
REM First-time setup (venv, packages) is scripts\run_dev.bat.
call "%~dp0..\start.bat" --no-ui %*
exit /b %ERRORLEVEL%
