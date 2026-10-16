"""Точка входа в приложение."""

import sys

from src.cli import parse_args
from src.errors import ConfigError


def main(argv: list[str] | None = None) -> int:
    """Точка входа приложения."""
    try:
        config = parse_args(argv)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0

    print("Параметры приложения:")
    print(config.to_key_value())
    return 0


if __name__ == "__main__":
    sys.exit(main())
