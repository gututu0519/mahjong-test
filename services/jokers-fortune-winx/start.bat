@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs jokers-fortune-winx %*
pause
