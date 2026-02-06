@echo off
echo ========================================
echo Intelligent Lighting System
echo ML Model Installation
echo ========================================
echo.

REM Check if we're in the right directory
if not exist "backend" (
    cd /d "%~dp0.."
)

if not exist "backend" (
    echo Error: Run this script from the project root directory
    exit /b 1
)

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.9 or higher from https://python.org
    exit /b 1
)

echo.
echo [1/2] Activating virtual environment...
cd backend

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo.
echo [2/2] Running model installation script...
cd ..
python scripts\install_models.py

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo Next steps:
echo   1. Restart Docker containers: docker-compose restart backend
echo   2. Or restart local server: cd backend ^&^& uvicorn app.main:app --reload
echo.
pause
