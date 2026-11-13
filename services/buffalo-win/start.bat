@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs buffalo-win %*
pause
