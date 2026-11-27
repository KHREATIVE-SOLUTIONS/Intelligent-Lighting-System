@echo off
REM UI dev server only, for working on the UI against a backend that is already
REM running on port 8000. To start everything, use start.bat in the project root.
echo Starting Frontend Server...

cd /d "%~dp0..\frontend"

REM Install dependencies if needed
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
)

echo.
echo Frontend starting at http://localhost:5173
echo.

npm run dev
