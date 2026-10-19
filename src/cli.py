"""Модуль разбора и валидации параметров командной строки."""

import argparse
import os
from urllib.parse import urlparse

from src.config import AppConfig
from src.errors import ValidationError


def build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        prog="dependency-visualizer",
        description="Инструмент визуализации графа зависимостей (Этап 1).",
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Имя анализируемого пакета.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="URL-адрес репозитория или путь к файлу тестового репозитория.",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Режим работы с тестовым репозиторием.",
    )
    parser.add_argument(
        "--output",
        default="graph.svg",
        help="Имя сгенерированного файла с изображением графа.",
    )
    parser.add_argument(
        "--ascii-tree",
        action="store_true",
        help="Режим вывода зависимостей в формате ASCII-дерева.",
    )
    return parser


def validate_package(package_name: str) -> None:
    """Проверяет корректность параметра --package."""
    if not package_name.strip():
        raise ValidationError(
            "Параметр --package не может быть пустым.",
        )
    if package_name != package_name.strip():
        raise ValidationError(
            "Имя пакета не должно содержать пробелы по краям."
        )


def validate_repo(repo: str, test_mode: bool) -> None:
    """Проверяет корректность параметра --repo."""
    if not repo.strip():
        raise ValidationError("Параметр --repo не может быть пустым.")

    if test_mode:
        if not os.path.exists(repo):
            raise ValidationError(
                f"Файл тестового репозитория не найден: {repo}"
            )
        if not os.path.isfile(repo):
            raise ValidationError(
                f"Путь тестового репозитория не является файлом: {repo}"
            )
    else:
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


def validate_output(output: str) -> None:
    """Проверяет корректность параметра --output."""
    if not output.strip():
        raise ValidationError("Параметр --output не может быть пустым.")
    if os.path.isdir(output):
        raise ValidationError(
            f"Параметр --output указывает на директорию: {output}"
        )


def parse_args(argv: list[str] | None = None) -> AppConfig:
    """Парсит аргументы командной строки и валидирует их."""
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
    )
