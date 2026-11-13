@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs wicked-grin %*
pause
