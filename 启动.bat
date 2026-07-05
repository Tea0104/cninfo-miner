@echo off
cd /d "%~dp0"

echo Announcement Extractor Launcher
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.x first.
    echo https://python.org
    pause
    exit /b 1
)

echo Installing dependencies...
pip install -r requirements.txt -q

echo Starting...
python app.py
pause
