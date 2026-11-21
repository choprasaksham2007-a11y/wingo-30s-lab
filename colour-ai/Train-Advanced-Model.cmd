@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u src\train_advanced.py
pause
