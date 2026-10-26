"""Точка входа в приложение."""

import sys

from src.cli import parse_args
from src.errors import ConfigError
from src.graph import (
    build_dependency_graph,
    print_ascii_tree,
    print_dependency_graph,
)


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

    print_dependency_graph(graph)

    if config.ascii_tree:
        print_ascii_tree(config.package_name, graph)

    return 0


if __name__ == "__main__":
    sys.exit(main())
