@echo off
cd /d "%~dp0..\.."
python -m server.run --service-dir services/3-billion-vaults
pause
