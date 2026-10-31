@echo off
title Ofrenda
cd /d "%~dp0"

rem First run only: create a private Python environment
if not exist ".venv\Scripts\activate.bat" (
    echo Setting things up, this takes a minute the first time...
    py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\activate.bat" (
    echo Python was not found. Install it from python.org and tick "Add python.exe to PATH".
    pause
    exit /b
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo.
echo Ofrenda is running. Your browser will open. Close this window to stop it.
python app.py
pause
