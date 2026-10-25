@echo off
cd /d "%~dp0..\.."
python -m server.merchant.sandbox gateway
pause
