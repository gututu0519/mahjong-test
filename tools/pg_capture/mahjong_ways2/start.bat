@echo off
title Local Multi-Game Server - Logs
cd /d "%~dp0..\..\.."
echo Starting generated game server: http://localhost:8080/?mock=1
echo Request logs will appear below. Press Ctrl+C to stop.
echo.
python -u -m server.app
echo.
echo Server stopped.
pause
