@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "New-Item -ItemType File -Path 'wingo_investigation\collected_data\collector.stop' -Force | Out-Null"
echo Stop requested. The Platsaas collector will finish its active batch, save to CSV/SQLite, and exit cleanly.
pause
