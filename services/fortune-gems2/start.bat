@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs fortune-gems2 %*
pause
