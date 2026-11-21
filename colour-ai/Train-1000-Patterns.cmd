@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u src\train_thousand.py
echo See results\latest_thousand_test.json for the report, 5000 predictions and saved model.
pause
