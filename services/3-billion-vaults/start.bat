@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs 3-billion-vaults %*
pause
