@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs money-pot-deluxe %*
pause
