@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u src\category_predictor.py train
pause
