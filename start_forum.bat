@echo off
chcp 65001 >nul
title NAGIN GTA - Forum
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python не знайдено. Встановіть Python 3.10+ з https://www.python.org/downloads/
  echo (під час встановлення поставте галочку "Add Python to PATH")
  pause
  exit /b 1
)
python server.py
pause
