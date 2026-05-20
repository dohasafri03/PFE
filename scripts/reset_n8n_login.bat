@echo off
title Reset n8n owner login
echo ============================================
echo   Reset compte proprietaire n8n (Docker)
echo ============================================
echo.
echo Ce script reinitialise le compte admin n8n.
echo Vous pourrez recreer email + mot de passe au prochain acces.
echo.
pause

docker ps --filter "name=marche-ai-n8n" --format "{{.Names}}" | findstr /i "marche-ai-n8n" >nul
if errorlevel 1 (
    echo ERREUR: conteneur marche-ai-n8n non demarre.
    echo Lancez d'abord: docker compose up -d
    pause
    exit /b 1
)

echo Reset user-management (peut prendre ~30 s)...
docker exec marche-ai-n8n n8n user-management:reset
if errorlevel 1 (
    echo Retry apres arret du conteneur...
    docker stop marche-ai-n8n
    docker run --rm -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n n8n user-management:reset
    docker start marche-ai-n8n
) else (
    docker restart marche-ai-n8n
)

echo.
echo OK. Ouvrez http://localhost:5678 et creez un nouveau compte proprietaire.
echo.
pause
