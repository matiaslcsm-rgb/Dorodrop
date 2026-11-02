@echo off
rem Abre Doro Drop en su propia ventana (ver backend\launcher.py).
cd /d "%~dp0"
if exist "python\pythonw.exe" (
    start "" "python\pythonw.exe" "backend\launcher.py"
) else (
    start "" "backend\venv\Scripts\pythonw.exe" "backend\launcher.py"
)
