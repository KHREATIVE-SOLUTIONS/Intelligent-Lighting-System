@echo off
echo Starting Backend Server...

cd /d "%~dp0..\backend"

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate and run
call venv\Scripts\activate.bat

REM Install dependencies if needed
pip install -r requirements.txt -q

REM Create database tables
python -c "from app.db.database import Base, engine; Base.metadata.create_all(bind=engine)" 2>nul

echo.
echo Backend starting at http://localhost:8000
echo API Docs at http://localhost:8000/docs
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
