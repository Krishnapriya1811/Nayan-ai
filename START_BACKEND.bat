@echo off
REM Start NAYAN-AI Backend Server
REM This script starts the Flask server on port 5000

set "ROOT=%~dp0"

REM Preferred interpreter when .venv is not present
set "FALLBACK_PY=D:\python\intepretor\Scripts\python.exe"

REM If you want to force a specific Python, set NAYAN_PY to a full python.exe path.
REM Example (PowerShell):
REM   $env:NAYAN_PY = "D:\python\intepretor\Scripts\python.exe"

set "PY="

REM If user provided NAYAN_PY, prefer it.
REM Using FOR %%~fI safely normalizes and strips quotes.
if defined NAYAN_PY (
	for %%I in ("%NAYAN_PY%") do (
		if exist "%%~fI" set "PY=%%~fI"
	)
)

REM Otherwise, prefer fallback interpreter (global) before .venv.
if not defined PY (
	if exist "%FALLBACK_PY%" (
		set "PY=%FALLBACK_PY%"
	) else if exist "%ROOT%.venv\Scripts\python.exe" (
		set "PY=%ROOT%.venv\Scripts\python.exe"
	) else (
		set "PY=python"
	)
)

cd /d "%ROOT%backend"

echo.
echo ╔════════════════════════════════════════╗
echo ║    NAYAN-AI BACKEND - STARTING...      ║
echo ╚════════════════════════════════════════╝
echo.

echo Using Python: %PY%
echo.

"%PY%" app.py

pause
