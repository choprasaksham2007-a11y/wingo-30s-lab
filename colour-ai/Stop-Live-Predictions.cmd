@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$predictionWorker = Get-Content -LiteralPath 'results\neural_worker.json' | ConvertFrom-Json; $predictionProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$predictionWorker.pid); $predictionPython = (Resolve-Path -LiteralPath '.venv\Scripts\python.exe').Path; if ($predictionProcess -and $predictionProcess.ExecutablePath -eq $predictionPython -and $predictionProcess.CommandLine -match '(neural|category)_predictor\.py watch') { taskkill /PID $predictionWorker.pid /T /F; if ($LASTEXITCODE -eq 0) { Write-Host 'Live predictor stopped. Saved predictions are preserved.' } } else { Write-Host 'No matching background predictor is running.' }"
pause
