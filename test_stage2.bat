@echo off
chcp 65001 >nul
setlocal


echo.
echo === Проверка ручного сценария (test-mode) ===
.venv\Scripts\python.exe -m src.main --package requests --repo .\tests\fixtures\package.json --test-mode
if %ERRORLEVEL% neq 0 goto :error
