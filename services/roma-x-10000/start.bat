@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs roma-x-10000 %*
pause
