@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs mock %*
pause
