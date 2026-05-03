@echo off
title Marche AI Platform - API pour n8n
echo ============================================
echo   Marche AI Platform - API Server
echo   http://localhost:8011
echo   Docs: http://localhost:8011/docs
echo ============================================
echo.

cd /d "%~dp0"

:: Activer le venv
call .venv\Scripts\activate.bat

:: Installer fastapi/uvicorn si absent
pip show fastapi >nul 2>&1 || pip install fastapi uvicorn[standard]

:: Lancer l'API
echo Demarrage API sur port 8011...
set PORT=8011
REM Disable env password fallback (prevents old default password working after change)
set AUTH_ALLOW_ENV_FALLBACK=0
REM Keep debug endpoint disabled by default
set DEBUG_AUTH=0
REM --- Safety: stop any existing process holding the port (prevents WinError 10048) ---
powershell -NoProfile -Command ^
  "$pids = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique); " ^
  "foreach ($p in $pids) { Write-Host ('Port %PORT% deja utilise (PID ' + $p + '). Arret...'); Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }"
REM Bind on IPv4 so tools calling 127.0.0.1 work reliably (n8n, curl, etc.)
python -m uvicorn api.main:app --host 127.0.0.1 --port %PORT% --log-level info
