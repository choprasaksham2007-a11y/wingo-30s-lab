@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$worker = Get-Content -LiteralPath 'results\neural_worker.json' | ConvertFrom-Json; Get-Content -LiteralPath $worker.stdout -Tail 30 -Wait"
pause
