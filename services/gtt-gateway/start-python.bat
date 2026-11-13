@echo off
cd /d "%~dp0..\.."
python -m py.merchant.sandbox gateway
pause
