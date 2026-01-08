@echo off
REM Start NAYAN-AI Backend Server
REM This script starts the Flask server on port 5000

set "ROOT=%~dp0"

if exist "%ROOT%.venv\Scripts\python.exe" (
	set "PY=%ROOT%.venv\Scripts\python.exe"
) else (
	set "PY=python"
)

cd /d "%ROOT%backend"

echo.
echo ╔════════════════════════════════════════╗
echo ║    NAYAN-AI BACKEND - STARTING...      ║
echo ╚════════════════════════════════════════╝
echo.

"%PY%" app.py

pause
