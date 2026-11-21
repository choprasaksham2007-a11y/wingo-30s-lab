@echo off
cd /d "%~dp0"
echo ===================================================
echo Running WinGo 30S Data Quality & Research Audit
echo ===================================================
python wingo_investigation\platsaas_collector.py --mode audit
pause
