@echo off
cd /d "%~dp0\..\.."
python -m server.run --service-dir services/dr-zappo
pause
