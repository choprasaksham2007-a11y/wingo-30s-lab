@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u src\neural_predictor.py train
pause
