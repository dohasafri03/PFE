@echo off
title Reset admin password (Docker)
echo Reinitialisation du mot de passe admin dans PostgreSQL (conteneur API)...
docker ps --filter "name=marche-ai-api" --format "{{.Names}}" | findstr /i "marche-ai-api" >nul
if errorlevel 1 (
    echo ERREUR: conteneur marche-ai-api non demarre. Lancez: docker compose up -d
    pause
    exit /b 1
)
set /p PWD="Mot de passe admin (defaut: Doha 2003): "
if "%PWD%"=="" set PWD=Doha 2003
docker exec marche-ai-api python -c "from app.database import SessionLocal; from api.main import _set_user_password, _verify_login; s=SessionLocal(); _set_user_password('admin', '%PWD%', db=s); s.close(); s2=SessionLocal(); ok=_verify_login('admin','%PWD%',db=s2); s2.close(); print('OK' if ok else 'ECHEC')"
echo.
echo Connectez-vous sur http://localhost:8080 avec admin / %PWD%
pause
