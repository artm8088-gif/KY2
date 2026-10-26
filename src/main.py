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


def main(argv: list[str] | None = None) -> int:
    """Запускает приложение."""
    try:
        config = parse_args(argv)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        graph = build_dependency_graph(
            package_name=config.package_name,
            repo=config.repo,
            test_mode=config.test_mode,
        )
    except ConfigError as exc:
        print(f"Ошибка построения графа: {exc}", file=sys.stderr)
        return 1

    # Выводим общую информацию о графе зависимостей.
    print_dependency_graph(graph)

    # Сравниваем граф с реальным деревом npm, если указан флаг.
    if config.compare_npm:
        try:
            compare_with_npm(config.package_name, graph)
        except NpmCompareError as exc:
            print(
                f"Ошибка сравнения с npm: {exc}",
                file=sys.stderr,
            )
            return 1

    # Выводим порядок загрузки, если указан флаг --load-order.
    if config.load_order:
        try:
            load_order = get_load_order(graph)
        except ValidationError as exc:
            print(
                f"Ошибка определения порядка загрузки: {exc}",
                file=sys.stderr,
            )
            return 1

        print("\nПорядок загрузки пакетов:")
        for index, package in enumerate(load_order, start=1):
            print(f"{index}. {package}")

    # Выводим ASCII-дерево, если указан флаг --ascii-tree.
    if config.ascii_tree:
        print_ascii_tree(config.package_name, graph)

    return 0


if __name__ == "__main__":
    sys.exit(main())
