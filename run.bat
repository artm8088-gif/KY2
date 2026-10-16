@echo off
setlocal

REM Переходим в директорию, где лежит сам скрипт
cd /d "%~dp0"

REM Проверяем наличие Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не найден в PATH. Установите Python 3.10+.
    exit /b 1
)

REM Проверяем версию Python
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VERSION=%%v
echo [INFO] Найден Python %PY_VERSION%

REM Создаём виртуальное окружение, если его нет
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Виртуальное окружение не найдено. Создаём...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Не удалось создать виртуальное окружение.
        exit /b 1
    )
    echo [INFO] Обновляем pip и устанавливаем зависимости...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

REM Запускаем приложение, передавая все аргументы дальше
".venv\Scripts\python.exe" -m src.main %*

endlocal