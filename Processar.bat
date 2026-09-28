@echo off
cd /d "%~dp0"
echo ============================================================
echo   FINANCIAL RECONCILIATION - PROCESSAMENTO LOCAL
echo ============================================================

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" "src\run_pipeline.py" %*
) else (
    py -3 "src\run_pipeline.py" %*
)

if errorlevel 1 (
    echo.
    echo O processamento terminou com erro. Leia a mensagem acima.
)
pause
