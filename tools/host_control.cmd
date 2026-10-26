@echo off
rem Double-click to open the Ace of Angels host window (tools\host_control.py).
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Missing project Python environment: .venv\Scripts\pythonw.exe
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" tools\host_control.py %*
