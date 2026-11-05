@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs sweet-bonanza-pop %*
pause
