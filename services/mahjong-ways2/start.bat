@echo off
cd /d "%~dp0..\.."
node server\tools\start.mjs mahjong-ways2 %*
pause
