@echo off
title Doro Drop
cd /d "%~dp0"
set PORT=8010

rem si ya esta abierto, solo abrir el navegador
curl -s -o nul http://127.0.0.1:%PORT%/ && goto :open

start "Doro Drop - servidor (cerra esta ventana para apagarlo)" /min "%~dp0python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --app-dir "%~dp0backend"

echo Arrancando Doro Drop...
for /l %%i in (1,1,40) do (
    curl -s -o nul http://127.0.0.1:%PORT%/ && goto :open
    timeout /t 1 /nobreak >nul
)
echo.
echo Doro Drop no pudo arrancar. Puede que el puerto %PORT% este ocupado por otro programa.
echo Revisa la ventana minimizada "Doro Drop - servidor" para ver el error.
pause
exit /b 1

:open
start "" http://localhost:%PORT%
