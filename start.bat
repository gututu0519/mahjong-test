@echo off
title Mahjong Local Server - Logs
cd /d "%~dp0"
echo Starting server: http://localhost:8080
echo Request logs will appear below. Press Ctrl+C to stop.
echo.
python -u serve_local.py
echo.
echo Server stopped.
pause
