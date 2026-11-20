@echo off
rem Double-click to open the Ace of Angels player window (setup, play, join a friend). Needs only Python 3.10 or later, no packages.
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && set "PY=python")
if defined PY (%PY% -I -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul || set "PY=")
if not defined PY (
  echo Python 3.10 or later was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo then double-click Play.cmd again.
  pause
  exit /b 1
)
rem python.exe, not pythonw.exe: an error before the window opens stays readable here.
%PY% -I tools\client_launcher.py %*
if errorlevel 1 (
  echo.
  echo The window stopped with an error; see the message above. Details: work\logs\launcher.log
  pause
)
