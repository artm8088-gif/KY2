"""Точка входа в приложение."""

import sys

from src.cli import parse_args
from src.config import AppConfig
from src.errors import ConfigError
from src.npm import (
    fetch_remote_package_json,
    get_direct_dependencies,
    read_local_package_json,
)


def load_package_json(config: AppConfig) -> dict:
    """Загружает package.json согласно режиму работы.

    Args:
        config: Конфигурация приложения.

    Returns:
        Словарь с данными package.json.

    Raises:
        ValidationError: При ошибке загрузки или парсинга.
    """
    if config.test_mode:
        return read_local_package_json(config.repo)
    return fetch_remote_package_json(config.repo)


def print_dependencies(
    package_json: dict,
    dependencies: dict[str, str],
    source: str,
    fallback_name: str,
) -> None:
    """Печатает информацию о пакете и его прямых зависимостях.

    Args:
        package_json: Данные package.json.
        dependencies: Словарь зависимостей (имя → версия).
        source: Источник данных (URL или путь).
        fallback_name: Имя пакета, если в JSON его нет.
    """
    name = package_json.get("name", fallback_name)
    version = package_json.get("version", "?")
    print(f"Пакет: {name}@{version}")
    print(f"Источник: {source}")

    if not dependencies:
        print("Прямых зависимостей нет.")
        return

    print(f"Прямые зависимости ({len(dependencies)}):")
    for dep_name in sorted(dependencies):
        print(f"  - {dep_name} {dependencies[dep_name]}")


def parse_config(argv: list[str] | None) -> AppConfig | None:
    """Парсит аргументы командной строки.

    Args:
        argv: Аргументы командной строки (или None для sys.argv).

    Returns:
        Объект AppConfig или None при ошибке парсинга.
    """
    try:
        return parse_args(argv)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return None
    except SystemExit as exc:
        if exc.code is not None and exc.code != 0:
            return None
        return None


def main(argv: list[str] | None = None) -> int:
    """Запускает приложение и возвращает код завершения.

    Args:
        argv: Аргументы командной строки (по умолчанию sys.argv).

    Returns:
        0 при успехе, 1 при ошибке.
    """
    config = parse_config(argv)
    if config is None:
        return 1

    print("Параметры приложения:")
    print(config.to_key_value())
    print()

    try:
        package_json = load_package_json(config)
        dependencies = get_direct_dependencies(package_json)
    except ConfigError as exc:
        print(f"Ошибка сбора данных: {exc}", file=sys.stderr)
        return 1

    print_dependencies(
        package_json,
        dependencies,
        config.repo,
        config.package_name,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
