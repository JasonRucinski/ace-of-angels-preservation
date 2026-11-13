@echo off
rem Double-click to choose client visuals and play Ace of Angels.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Missing project Python environment: .venv\Scripts\python.exe
  echo Create it as docs\play.md describes: py -3.12 -m venv .venv
  pause
  exit /b 1
)
rem python.exe, not pythonw.exe: an error before the window opens stays readable here.
".venv\Scripts\python.exe" -I tools\client_launcher.py %*
if errorlevel 1 (
  echo.
  echo The client launcher stopped with an error; see the message above.
  pause
)
