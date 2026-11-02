"""Точка входа в приложение."""

import sys

from src.cli import parse_args
from src.errors import ConfigError, ValidationError
from src.graph import (
    build_dependency_graph,
    get_load_order,
    print_ascii_tree,
    print_dependency_graph,
)
from src.npm_compare import NpmCompareError, compare_with_npm
from src.visualization import VisualizationError, save_graph


def _print_load_order(graph: dict[str, dict[str, str]]) -> None:
    """Определяет и печатает порядок загрузки пакетов.

    Args:
        graph: Граф зависимостей.

    Raises:
        ValidationError: Если граф содержит циклические зависимости.
    """
    load_order = get_load_order(graph)
    print("\nПорядок загрузки пакетов:")
    for index, package in enumerate(load_order, start=1):
        print(f"{index}. {package}")


def _run(config) -> None:
    """Выполняет основной сценарий приложения.

    Args:
        config: Разобранная конфигурация приложения.

    Raises:
        ConfigError: Ошибка построения графа.
        VisualizationError: Ошибка сохранения визуализации.
        NpmCompareError: Ошибка сравнения с npm.
        ValidationError: Ошибка определения порядка загрузки.
    """
    graph = build_dependency_graph(
        package_name=config.package_name,
        repo=config.repo,
        test_mode=config.test_mode,
    )

    print_dependency_graph(graph)
    save_graph(graph, config.output_file)

    if config.compare_npm:
        compare_with_npm(config.package_name, graph)

    if config.load_order:
        _print_load_order(graph)

    if config.ascii_tree:
        print_ascii_tree(config.package_name, graph)


def _format_error(exc: Exception) -> str:
    """Формирует текст сообщения об ошибке для stderr.

    Args:
        exc: Пойманное исключение приложения.

    Returns:
        Строка с префиксом, соответствующим типу ошибки.
    """
    if isinstance(exc, ConfigError):
        return f"Ошибка построения графа: {exc}"
    if isinstance(exc, VisualizationError):
        return f"Ошибка визуализации графа: {exc}"
    if isinstance(exc, NpmCompareError):
        return f"Ошибка сравнения с npm: {exc}"
    if isinstance(exc, ValidationError):
        return f"Ошибка определения порядка загрузки: {exc}"
    return f"Неизвестная ошибка: {exc}"


def main(argv: list[str] | None = None) -> int:
    """Запускает приложение.

    Разбирает аргументы, строит граф зависимостей, сохраняет
    визуализацию и при необходимости выполняет сравнение с npm,
    печать порядка загрузки и ASCII-дерева.

    Args:
        argv: Аргументы командной строки или None для sys.argv.

    Returns:
        Код возврата: 0 при успехе, 1 при ошибке.
    """
    try:
        config = parse_args(argv)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        _run(config)
    except (
        ConfigError,
        VisualizationError,
        NpmCompareError,
        ValidationError,
    ) as exc:
        print(_format_error(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
