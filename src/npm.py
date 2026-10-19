"""Модуль получения данных о зависимостях из npm (package.json)."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from src.errors import ValidationError

# Таймаут HTTP-запроса в секундах.
TIMEOUT = 15

# Минимум частей пути в URL репозитория (owner + repo).
MIN_PATH_PARTS = 2


def _parse_repo_parts(
    parsed,
    platform: str,
    repo_url: str,
) -> tuple[str, str]:
    """Извлекает owner и repo из URL репозитория.

    Args:
        parsed: Результат urlparse.
        platform: Имя платформы (GitHub, GitLab) для сообщения.
        repo_url: Исходный URL.

    Returns:
        Кортеж (owner, repo).

    Raises:
        ValidationError: Если в URL меньше нужного числа частей.
    """
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < MIN_PATH_PARTS:
        raise ValidationError(
            f"Не удалось разобрать {platform} URL: {repo_url}"
        )
    return parts[0], parts[1].removesuffix(".git")


def _github_raw_url(parsed, repo_url: str) -> str:
    """Строит raw-ссылку на package.json для GitHub.

    Args:
        parsed: Результат urlparse.
        repo_url: Исходный URL.

    Returns:
        Прямая ссылка на package.json.
    """
    owner, repo = _parse_repo_parts(parsed, "GitHub", repo_url)
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}" "/HEAD/package.json"
    )


def _gitlab_raw_url(parsed, repo_url: str) -> str:
    """Строит raw-ссылку на package.json для GitLab.

    Args:
        parsed: Результат urlparse.
        repo_url: Исходный URL.

    Returns:
        Прямая ссылка на package.json.
    """
    owner, repo = _parse_repo_parts(parsed, "GitLab", repo_url)
    return f"https://gitlab.com/{owner}/{repo}/-/raw/HEAD/package.json"


def _get_raw_url(repo_url: str) -> str:
    """Преобразует URL репозитория в прямую ссылку на package.json.

    Args:
        repo_url: URL репозитория (GitHub, GitLab или прямой .json).

    Returns:
        Прямая ссылка на package.json.

    Raises:
        ValidationError: Если URL не поддерживается.
    """
    parsed = urlparse(repo_url)
    host = parsed.netloc.lower()

    if host in {"github.com", "www.github.com"}:
        return _github_raw_url(parsed, repo_url)
    if host in {"gitlab.com", "www.gitlab.com"}:
        return _gitlab_raw_url(parsed, repo_url)
    if parsed.scheme in {"http", "https"} and parsed.path.lower().endswith(
        ".json"
    ):
        return repo_url

    raise ValidationError(
        f"Неподдерживаемый URL репозитория: {repo_url}. "
        "Ожидается GitHub, GitLab или прямая ссылка на package.json."
    )


def _parse_payload(payload: str, source: str) -> dict:
    """Парсит JSON-строку и проверяет, что это словарь.

    Args:
        payload: Строка с JSON.
        source: Источник (для сообщений об ошибке).

    Returns:
        Словарь с данными package.json.

    Raises:
        ValidationError: Если JSON некорректный или это не объект.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Некорректный JSON в {source}: " f"{exc.msg} (строка {exc.lineno})"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError(f"Ожидался JSON-объект в {source}.")
    return data


def _build_request(raw_url: str) -> urllib.request.Request:
    """Строит HTTP-запрос с User-Agent для обхода блокировок.

    Args:
        raw_url: URL для запроса.

    Returns:
        Объект Request с заголовком User-Agent.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    return urllib.request.Request(raw_url, headers=headers)


def _read_url(req: urllib.request.Request) -> str:
    """Выполняет HTTP-запрос и возвращает тело ответа.

    Args:
        req: Объект Request.

    Returns:
        Тело ответа в виде строки UTF-8.

    Raises:
        ValidationError: При HTTP, сетевой ошибке или таймауте.
    """
    raw_url = req.full_url
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValidationError(
            f"HTTP {exc.code} при скачивании {raw_url}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ValidationError(
            f"Сетевая ошибка при скачивании {raw_url}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise ValidationError(f"Таймаут при скачивании {raw_url}") from exc


def fetch_remote_package_json(repo_url: str) -> dict:
    """Скачивает package.json по URL репозитория.

    Args:
        repo_url: URL репозитория (GitHub, GitLab или прямой .json).

    Returns:
        Словарь с данными package.json.

    Raises:
        ValidationError: При ошибке URL, сети или парсинга JSON.
    """
    raw_url = _get_raw_url(repo_url)
    req = _build_request(raw_url)
    payload = _read_url(req)
    return _parse_payload(payload, raw_url)


def read_local_package_json(path: str) -> dict:
    """Читает локальный package.json.

    Args:
        path: Путь к файлу package.json.

    Returns:
        Словарь с данными package.json.

    Raises:
        ValidationError: При ошибке чтения или парсинга JSON.
    """
    p = Path(path)
    try:
        payload = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"Не удалось прочитать {path}: {exc}") from exc
    return _parse_payload(payload, str(p))


def get_direct_dependencies(package_json: dict) -> dict[str, str]:
    """Возвращает прямые зависимости из поля dependencies.

    Args:
        package_json: Словарь с данными package.json.

    Returns:
        Словарь вида {имя: версия} для прямых зависимостей.

    Raises:
        ValidationError: Если поле dependencies не словарь.
    """
    deps = package_json.get("dependencies") or {}

    if not isinstance(deps, dict):
        raise ValidationError(
            "Поле 'dependencies' должно быть объектом (словарём)."
        )

    return {str(k): str(v) for k, v in deps.items()}
