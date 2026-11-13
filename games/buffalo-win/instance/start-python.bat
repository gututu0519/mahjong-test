@echo off
node "%~dp0..\..\..\other\tooling\run.mjs" python -u -m py.services.buffalo_demo %*
pause
