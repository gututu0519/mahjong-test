@echo off
cd /d "%~dp0../.."
python -m server.run --service-dir services/le-vampire
pause
