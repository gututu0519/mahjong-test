@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs admin %*
pause
