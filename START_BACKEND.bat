@echo off
REM Start NAYAN-AI Backend Server
REM This script starts the Flask server on port 5000

set "ROOT=%~dp0"

REM Preferred interpreter when .venv is not present
set "FALLBACK_PY=D:\python\intepretor\Scripts\python.exe"

if exist "%ROOT%.venv\Scripts\python.exe" (
	set "PY=%ROOT%.venv\Scripts\python.exe"
) else if exist "%FALLBACK_PY%" (
	set "PY=%FALLBACK_PY%"
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
