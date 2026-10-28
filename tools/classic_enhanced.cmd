@echo off
cd /d "%~dp0.."
python -I tools\classic_enhanced.py launch game\classic-enhanced
if errorlevel 1 pause
