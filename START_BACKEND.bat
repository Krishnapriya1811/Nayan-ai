@echo off
REM Start NAYAN-AI Backend Server
REM This script starts the Flask server on port 5000

cd /d "%~dp0backend"

echo.
echo ╔════════════════════════════════════════╗
echo ║    NAYAN-AI BACKEND - STARTING...      ║
echo ╚════════════════════════════════════════╝
echo.

python app.py

pause
