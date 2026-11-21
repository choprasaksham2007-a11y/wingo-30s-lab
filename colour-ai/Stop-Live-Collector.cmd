@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "New-Item -ItemType File -Path 'wingo_investigation\collected_data\collector.stop' -Force | Out-Null"
echo Stop requested. Collector will finish its poll, save and release sleep prevention.
echo If the API requested a backoff, stopping can take up to five minutes.
pause
