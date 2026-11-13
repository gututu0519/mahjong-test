@echo off
cd /d "%~dp0..\.."
python -m py.run --service-dir services/roma-x-10000
pause
