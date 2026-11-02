"""Модуль разбора и валидации параметров командной строки."""

import argparse
import os
from urllib.parse import urlparse

from src.config import AppConfig
from src.errors import ValidationError


def _add_required_arguments(parser: argparse.ArgumentParser) -> None:
    """Добавляет в парсер обязательные аргументы --package и --repo.

    Args:
        parser: Парсер аргументов командной строки.
    """
    parser.add_argument(
        "--package",
        required=True,
        help="Имя анализируемого пакета.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="URL репозитория или путь к тестовому JSON-файлу.",
    )


def _add_optional_arguments(parser: argparse.ArgumentParser) -> None:
    """Добавляет в парсер опциональные флаги и --output.

    Args:
        parser: Парсер аргументов командной строки.
    """
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Режим работы с тестовым репозиторием.",
    )
    parser.add_argument(
        "--output",
        default="graph.svg",
        help="Имя генерируемого файла с изображением графа.",
    )
    parser.add_argument(
        "--ascii-tree",
        action="store_true",
        help="Вывести зависимости в формате ASCII-дерева.",
    )
    parser.add_argument(
        "--load-order",
        action="store_true",
        help="Вывести порядок загрузки пакетов с учётом зависимостей.",
    )
    parser.add_argument(
        "--compare-npm",
        action="store_true",
        help="Сравнить граф зависимостей с реальным npm.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки.

    Returns:
        Настроенный argparse.ArgumentParser со всеми аргументами CLI.
    """
    parser = argparse.ArgumentParser(
        prog="dependency-visualizer",
        description="Инструмент визуализации графа зависимостей.",
    )
    _add_required_arguments(parser)
    _add_optional_arguments(parser)
    return parser


def validate_package(package_name: str) -> None:
    """Проверяет корректность параметра --package.

    Args:
        package_name: Значение аргумента --package.

    Raises:
        ValidationError: Если имя пустое или содержит пробелы по краям.
    """
    if not package_name.strip():
        raise ValidationError("Параметр --package не может быть пустым.")

    if package_name != package_name.strip():
        raise ValidationError(
            "Имя пакета не должно содержать пробелы по краям."
        )


def _validate_test_repo_path(repo: str) -> None:
    """Проверяет путь к тестовому репозиторию в тестовом режиме.

    Args:
        repo: Путь к файлу тестового репозитория.

    Raises:
        ValidationError: Если файл не существует или не является файлом.
    """
    if not os.path.exists(repo):
        raise ValidationError(f"Файл тестового репозитория не найден: {repo}")

    if not os.path.isfile(repo):
        raise ValidationError(
            f"Путь тестового репозитория не является файлом: {repo}"
        )


def _validate_repo_url(repo: str) -> None:
    """Проверяет, что repo — корректный http(s)-URL.

    Args:
        repo: URL репозитория npm.

    Raises:
        ValidationError: Если URL некорректен.
    """
    parsed = urlparse(repo)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or any(char.isspace() for char in repo)
    ):
        raise ValidationError(
            f"Некорректный URL репозитория: {repo}. "
            "Ожидается полный URL с протоколом http или https."
        )


def validate_repo(repo: str, test_mode: bool) -> None:
    """Проверяет корректность параметра --repo.

    В тестовом режиме repo должен указывать на существующий файл,
    иначе — быть корректным http(s)-URL.

    Args:
        repo: Значение аргумента --repo.
        test_mode: Включён ли тестовый режим.

    Raises:
        ValidationError: Если repo пуст или не соответствует режиму.
    """
    if not repo.strip():
        raise ValidationError("Параметр --repo не может быть пустым.")

    if test_mode:
        _validate_test_repo_path(repo)
    else:
        _validate_repo_url(repo)


def validate_output(output: str) -> None:
    """Проверяет корректность параметра --output.

    Args:
        output: Значение аргумента --output.

    Raises:
        ValidationError: Если путь пуст или указывает на директорию.
    """
    if not output.strip():
        raise ValidationError("Параметр --output не может быть пустым.")

    if os.path.isdir(output):
        raise ValidationError(
            f"Параметр --output указывает на директорию: {output}"
        )


def parse_args(argv: list[str] | None = None) -> AppConfig:
    """Парсит аргументы командной строки и валидирует их.

    Args:
        argv: Список аргументов или None для sys.argv[1:].

    Returns:
        Заполненный объект AppConfig.

    Raises:
        ValidationError: Если какой-либо аргумент некорректен.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    validate_package(args.package)
    validate_repo(args.repo, args.test_mode)
    validate_output(args.output)

    return AppConfig(
        package_name=args.package,
        repo=args.repo,
        test_mode=args.test_mode,
        output_file=args.output,
        ascii_tree=args.ascii_tree,
        load_order=args.load_order,
        compare_npm=args.compare_npm,
    )
