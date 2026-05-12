@echo off
chcp 65001 >nul 2>&1
echo ======================================
echo  ClawOS X Starting...
echo ======================================
echo.

cd /d "%~dp0server"

echo [1/2] Checking dependencies...
python -c "import fastapi, uvicorn, chromadb" 2>nul
if errorlevel 1 (
    echo [ERROR] Dependencies not found, installing...
    pip install -r requirements.txt
)

echo.
echo [2/2] Starting server...
echo   Admin UI: http://localhost:8000/web
echo   Login: admin / admin123
echo.
echo Press Ctrl+C to stop
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
