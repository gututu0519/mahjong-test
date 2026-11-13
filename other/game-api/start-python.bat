@echo off
node "%~dp0..\tooling\run.mjs" python -m py.run --service-dir "%~dp0." %*
pause
