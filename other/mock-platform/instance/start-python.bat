@echo off
node "%~dp0..\..\tooling\run.mjs" python -m py.merchant.sandbox platform %*
pause
