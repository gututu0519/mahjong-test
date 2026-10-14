@echo off
cd /d "%~dp0../.."
python -u -m server.services.buffalo_demo
pause
