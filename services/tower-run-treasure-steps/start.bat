@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs tower-run-treasure-steps %*
pause
