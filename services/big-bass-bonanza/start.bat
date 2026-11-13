@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs big-bass-bonanza %*
pause
