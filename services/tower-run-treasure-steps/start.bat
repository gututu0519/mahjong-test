@echo off
cd /d "%~dp0..\.."
node node\tools\start.mjs tower-run-treasure-steps %*
pause
