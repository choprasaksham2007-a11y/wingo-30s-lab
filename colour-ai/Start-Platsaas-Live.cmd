@echo off
cd /d "%~dp0"
echo ===================================================
echo Starting WinGo 30S Platsaas Live Continuous Polling
echo Polling every 30 seconds... (Press Ctrl+C or run Stop-Platsaas-Collector.cmd to exit)
echo ===================================================
python wingo_investigation\platsaas_collector.py --mode live --poll-interval 30
pause
