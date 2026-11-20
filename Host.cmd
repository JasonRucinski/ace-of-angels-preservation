@echo off
rem Double-click to open the Ace of Angels host window. Needs only Python 3.10 or later, no packages.
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && set "PY=python")
if defined PY (%PY% -I -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul || set "PY=")
if not defined PY (
  echo Python 3.10 or later was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo then double-click Host.cmd again.
  pause
  exit /b 1
)
rem python.exe, not pythonw.exe: an error before the window opens stays readable here.
%PY% -I tools\host_control.py %*
if errorlevel 1 (
  echo.
  echo The window stopped with an error; see the message above. Details: work\logs\host.log
  pause
)
