@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "runtime=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%runtime%" (
  "%runtime%" "%~dp0preview.py" %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python "%~dp0preview.py" %*
  ) else (
    py -3 "%~dp0preview.py" %*
  )
)
set "result=%errorlevel%"
if "%~1"=="" if not "%result%"=="0" pause
exit /b %result%
