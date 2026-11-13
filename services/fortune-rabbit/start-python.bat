@echo off
cd /d "%~dp0..\.."
python -m py.run --service-dir services/fortune-rabbit
pause
