@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs big-bass-bonanza %*
pause
