@echo off
REM First-time setup, then start. Setup needs internet once; after that
REM start.bat in the project root is all that is needed, and needs none.
setlocal
set "ROOT=%~dp0.."

echo ========================================
echo Intelligent Lighting System - Setup
echo ========================================

if not exist "%ROOT%\backend\venv\Scripts\python.exe" (
    echo Creating the backend virtual environment...
    python -m venv "%ROOT%\backend\venv" || exit /b 1
    echo Installing backend packages...
    "%ROOT%\backend\venv\Scripts\python.exe" -m pip install -r "%ROOT%\backend\requirements.txt" || exit /b 1
)

if not exist "%ROOT%\frontend\node_modules" (
    echo Installing UI packages...
    pushd "%ROOT%\frontend"
    call npm install
    if errorlevel 1 (
        popd
        exit /b 1
    )
    popd
)

call "%ROOT%\start.bat" %*
exit /b %ERRORLEVEL%
