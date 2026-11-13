@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b
)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" goto ready
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" goto ready
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 (
  pause
  exit /b
)
:ready
.venv\Scripts\python.exe app.py --open
pause
