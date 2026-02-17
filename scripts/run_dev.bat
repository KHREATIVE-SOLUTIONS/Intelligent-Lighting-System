@echo off
echo ========================================
echo Intelligent Lighting System - Dev Setup
echo ========================================

REM Check if we're in the right directory
if not exist "backend" (
    echo Error: Run this script from the project root directory
    exit /b 1
)

echo.
echo [1/4] Setting up Backend...
cd backend

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing backend dependencies...
pip install -r requirements.txt -q

REM Create database tables
echo Creating database tables...
python -c "from app.db.database import Base, engine; Base.metadata.create_all(bind=engine)"

echo.
echo [2/4] Starting Backend Server...
start "Backend" cmd /c "venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000"

cd ..

echo.
echo [3/4] Setting up Frontend...
cd frontend

REM Install npm dependencies if node_modules doesn't exist
if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

echo.
echo [4/4] Starting Frontend Server...
start "Frontend" cmd /c "npm run dev"

cd ..

echo.
echo ========================================
echo Servers starting...
echo.
echo Backend API:  http://localhost:8000
echo API Docs:     http://localhost:8000/docs
echo Frontend:     http://localhost:5173
echo ========================================
echo.
echo Press any key to open the application in browser...
pause >nul

start http://localhost:5173
