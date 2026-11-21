@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$worker = Get-Content -LiteralPath 'results\collector_worker.json' | ConvertFrom-Json; Get-Content -LiteralPath $worker.stdout -Tail 15 -Wait"
pause
