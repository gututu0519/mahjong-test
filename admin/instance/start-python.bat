@echo off
node "%~dp0..\..\other\tooling\run.mjs" python -m py.merchant.sandbox admin %*
pause
