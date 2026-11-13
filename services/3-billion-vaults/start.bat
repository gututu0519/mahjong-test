@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs 3-billion-vaults %*
pause
