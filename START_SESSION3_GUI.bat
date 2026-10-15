@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" session3_dashboard.py
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
    py -3 session3_dashboard.py
    ) else (
        python session3_dashboard.py
    )
)
if errorlevel 1 pause
