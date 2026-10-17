"""Модуль получения данных о зависимостях из npm (package.json)."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from src.errors import ValidationError

TIMEOUT = 15  # секунд


def _get_raw_url(repo_url: str) -> str:
    """Преобразует URL репозитория в прямую ссылку на package.json."""
    parsed = urlparse(repo_url)
    host = parsed.netloc.lower()

    # --- GitHub: https://github.com/owner/repo ---
    if host in {"github.com", "www.github.com"}:
        # path.strip("/").split("/") превращает "/owner/repo" в ["owner", "repo"]
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) < 2:
            raise ValidationError(f"Не удалось разобрать GitHub URL: {repo_url}")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        # Используем HEAD, чтобы всегда брать дефолтную ветку (main/master)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/package.json"

    # --- GitLab: https://gitlab.com/owner/repo ---
    if host in {"gitlab.com", "www.gitlab.com"}:
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) < 2:
            raise ValidationError(f"Не удалось разобрать GitLab URL: {repo_url}")
        owner, repo = parts[0], parts[1].removesuffix(".git")
        return f"https://gitlab.com/{owner}/{repo}/-/raw/HEAD/package.json"

    # --- Если это уже прямая ссылка на .json файл ---
    if parsed.scheme in {"http", "https"} and parsed.path.lower().endswith(".json"):
        return repo_url

    raise ValidationError(
        f"Неподдерживаемый URL репозитория: {repo_url}. "
        "Ожидается GitHub, GitLab или прямая ссылка на package.json."
    )


def _parse_payload(payload: str, source: str) -> dict:
    """Парсит JSON-строку и проверяет, что это словарь."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        # Перехватываем стандартную ошибку и превращаем в нашу ValidationError,
        # чтобы в main() было единое сообщение "Ошибка сбора данных: ..."
        raise ValidationError(
            f"Некорректный JSON в {source}: {exc.msg} (строка {exc.lineno})"
        ) from exc

    # package.json всегда должен быть объектом (словарём), а не массивом или строкой
    if not isinstance(data, dict):
        raise ValidationError(f"Ожидался JSON-объект в {source}.")
    return data


def fetch_remote_package_json(repo_url: str) -> dict:
    """Скачивает package.json по URL репозитория."""
    raw_url = _get_raw_url(repo_url)
    try:
        # User-Agent нужен, чтобы некоторые сервера (например, GitHub) не блокировали запрос
        req = urllib.request.Request(
            raw_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = resp.read().decode("utf-8")

    # HTTPError — сервер ответил, но с ошибкой (404, 403, 500 и т.д.)
    except urllib.error.HTTPError as exc:
        raise ValidationError(f"HTTP {exc.code} при скачивании {raw_url}") from exc

    # URLError — сетевая проблема (нет интернета, DNS не резолвится, таймаут соединения)
    except urllib.error.URLError as exc:
        raise ValidationError(f"Сетевая ошибка при скачивании {raw_url}: {exc.reason}") from exc

    # TimeoutError — сервер не ответил за TIMEOUT секунд
    except TimeoutError as exc:
        raise ValidationError(f"Таймаут при скачивании {raw_url}") from exc

    return _parse_payload(payload, raw_url)


def read_local_package_json(path: str) -> dict:
    """Читает локальный package.json."""
    p = Path(path)
    try:
        payload = p.read_text(encoding="utf-8")
    except OSError as exc:
        # OSError покрывает FileNotFoundError, PermissionError, IsADirectoryError и т.д.
        raise ValidationError(f"Не удалось прочитать {path}: {exc}") from exc
    return _parse_payload(payload, str(p))


def get_direct_dependencies(package_json: dict) -> dict[str, str]:
    """Возвращает прямые зависимости из поля dependencies."""
    # Если поля "dependencies" нет, возвращаем пустой словарь (пакет без зависимостей)
    # Если там null, тоже превращаем в пустой словарь благодаря `or {}`
    deps = package_json.get("dependencies") or {}

    # Защита от невалидного package.json, где dependencies — это, например, список
    if not isinstance(deps, dict):
        raise ValidationError("Поле 'dependencies' должно быть объектом (словарём).")

    # Приводим все ключи и значения к строкам (на случай, если в JSON были числа)
    # Это нужно для будущих этапов (BFS, сравнение версий), где важна стабильность типов
    return {str(k): str(v) for k, v in deps.items()}
