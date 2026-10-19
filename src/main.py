"""Точка входа в приложение."""

import sys

from src.cli import parse_args
from src.errors import ConfigError
from src.npm import (
    fetch_remote_package_json,
    get_direct_dependencies,
    read_local_package_json,
)


def main(argv: list[str] | None = None) -> int:
    """Точка входа приложения. Возвращает код завершения (0-успех,1-ошибка)."""
    try:
        """ parse_args читает sys.argv, проверяет параметры (через src.cli)
        и возвращает объект AppConfig с настройками"""
        config = parse_args(argv)
    except ConfigError as exc:
        """Если в параметрах что-то не так (пустой пакет, битый URL, etc.),
        выводим ошибку в stderr (поток ошибок) и возвращаем 1"""
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        """Это перехват стандартного поведения argparse.
        Например, если пользователь ввёл`--help`,argparse вызывает sys.exit(0).
        Или если не передал обязательный аргумент — sys.exit(2).
        Мы аккуратно возвращаем этот код, чтобы скрипт завершился корректно"""
        return int(exc.code) if exc.code is not None else 0
    print("Параметры приложения:")
    print(config.to_key_value())  # Методиз src.config, печатает ключ = значение
    print()  # Пустая строка для визуального отделения этапов

    try:
        # Получаем package.json
        # В зависимости от режима (тестовый или реальный)
        if config.test_mode:
            # Тестовый режим: читаем локальный файл по пути config.repo
            package_json = read_local_package_json(config.repo)
            source = config.repo
        else:
            # Реальный режим: скачиваем по URL (GitHub/GitLab)
            package_json = fetch_remote_package_json(config.repo)
            source = config.repo

        # Извлекаем прямые зависимости
        # Возвращает словарь: {"имя_зависимости": "версия", ...}
        deps = get_direct_dependencies(package_json)

        # Достаём имя и версию пакета для красивого вывода
        # Если в JSON нет поля "name", берём имя из аргументов командной строки
        name = package_json.get("name", config.package_name)
        version = package_json.get(
            "version", "?"
        )  # Если версии нет, ставим "?"

        # Выводим результат на экран
        print(f"Пакет: {name}@{version}")
        print(f"Источник: {source}")

        # Если зависимостей нет вообще
        if not deps:
            print("Прямых зависимостей нет.")
            return 0

        # Если есть — выводим их количество и отсортированный список
        # sorted(deps) сортирует ключи словаря (имена пакетов) по алфавиту
        print(f"Прямые зависимости ({len(deps)}):")
        for dep in sorted(deps):
            print(f"  - {dep} {deps[dep]}")

        return 0

    except ConfigError as exc:
        # Если что-то пошло не так на этапе скачивания/чтения/парсинга
        # (например, 404, битый JSON, нет прав на чтение файла)
        # выводим ошибку и возвращаем 1
        print(f"Ошибка сбора данных: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # sys.exit(main()) передаёт код возврата из main() в операционную систему.
    # Это нужно для того, чтобы инструменты вроде CI/CD или bash-скриптов
    # могли понять, успешно завершилась программа (0) или упала (1).
    sys.exit(main())
