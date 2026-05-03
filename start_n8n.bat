@echo off
title n8n - Orchestrateur Workflow
echo ============================================
echo   n8n Workflow Orchestrator
echo   http://localhost:5678
echo ============================================
echo.

:: Check if Docker is available
docker --version >nul 2>&1
if errorlevel 1 (
    echo Docker non trouve. Installation de n8n via npm...
    echo.
    where npx >nul 2>&1
    if errorlevel 1 (
        echo ERREUR: ni Docker ni Node.js ne sont installes.
        echo Installer Docker Desktop ou Node.js 18+
        pause
        exit /b 1
    )
    set GENERIC_TIMEZONE=Africa/Casablanca
    npx n8n start --tunnel
) else (
    echo Lancement de n8n via Docker...
    docker run -it --rm ^
        --name marche-ai-n8n ^
        -p 5678:5678 ^
        -v n8n_data:/home/node/.n8n ^
        -v "%~dp0n8n":/home/node/workflows ^
        -e GENERIC_TIMEZONE=Africa/Casablanca ^
        -e N8N_SECURE_COOKIE=false ^
        --add-host=host.docker.internal:host-gateway ^
        docker.n8n.io/n8nio/n8n:latest
)
