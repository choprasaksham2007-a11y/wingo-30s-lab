@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u src\train_patterns.py
echo Training creates a separate pattern candidate and evaluation report.
echo It does not replace an existing live pattern learner or reset neural memory.
pause
