@echo off
cd /d "%~dp0..\.."
python -m py.run --service-dir services/3-billion-vaults
pause
