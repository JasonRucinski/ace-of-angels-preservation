@echo off
rem Double-click to choose client visuals and play Ace of Angels.
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Missing project Python environment: .venv\Scripts\pythonw.exe
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -I tools\client_launcher.py %*
