@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs game-api %*
pause
