@echo off
cd /d "%~dp0"
echo ===================================================
echo Starting WinGo 30S Platsaas Historical Backfill
echo From 2026-10-12 to Today
echo ===================================================
python wingo_investigation\platsaas_collector.py --mode backfill --start-date 2026-10-12 --end-date 2026-11-11 --page-size 100
pause
