@echo off
title Rebuild Dashboard Docker
echo Reconstruction de l'image dashboard (dernier code React)...
cd /d "%~dp0.."
docker compose build --no-cache dashboard
if errorlevel 1 (
    echo ERREUR: build echoue.
    pause
    exit /b 1
)
docker compose up -d dashboard
echo.
echo OK. Ouvrez http://localhost:8080 (Ctrl+F5 pour vider le cache navigateur).
pause
