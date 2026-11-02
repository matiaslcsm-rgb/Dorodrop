@echo off
title Doro Drop
cd /d "%~dp0backend"

if not exist venv\Scripts\python.exe (
    echo No se encontro el entorno virtual. Corre la instalacion primero ^(ver README.md^).
    pause
    exit /b 1
)

start "Doro Drop - servidor" /min cmd /c "venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8010"
timeout /t 2 /nobreak >nul
start "" http://localhost:8010
