@echo off
REM Kept so old shortcuts still work. The launcher is start.py in the project
REM root; this passes every option through to it (try --check or --dry-run).
call "%~dp0..\start.bat" %*
exit /b %ERRORLEVEL%
