@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs roma-x-10000 %*
pause
