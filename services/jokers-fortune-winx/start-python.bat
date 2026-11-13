@echo off
cd /d "%~dp0..\.."
python -m py.run --service-dir services/jokers-fortune-winx
pause
