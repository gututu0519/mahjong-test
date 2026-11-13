@echo off
cd /d "%~dp0..\.."
python -m py.run --service-dir services/mahjong-ways2
pause
