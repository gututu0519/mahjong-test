@echo off
cd /d "%~dp0..\.."
python -m py.run --service-dir services/money-pot-deluxe
pause
