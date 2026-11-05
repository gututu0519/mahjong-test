@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs wicked-grin %*
pause
