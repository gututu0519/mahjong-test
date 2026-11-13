@echo off
node "%~dp0..\tooling\run.mjs" python -u -m py.services.local_demo %*
pause
