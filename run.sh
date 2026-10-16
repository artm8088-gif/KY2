#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[INFO] Виртуальное окружение не найдено. Создаём..."
    python3 -m venv .venv
    echo "[INFO] Устанавливаем зависимости..."
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python -m src.main "$@"