@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs le-vampire %*
pause
