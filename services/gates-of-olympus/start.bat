@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs gates-of-olympus %*
pause
