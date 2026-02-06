@echo off
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
