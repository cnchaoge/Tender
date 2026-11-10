@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo Tender: one process, no --reload, no --workers
echo Listening on 127.0.0.1:8000
echo Build the frontend first: cd web ^&^& npm run build
echo First-run password file: data\initial_admin_password.txt
echo Do not start a second process against the same data\ directory.
echo.
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
pause
