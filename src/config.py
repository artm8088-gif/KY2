"""Конфигурация приложения."""

from dataclasses import dataclass


@dataclass
class AppConfig:
    """Хранит параметры запуска приложения."""

    package_name: str
    repo: str
    test_mode: bool = False
    output_file: str = "graph.svg"
    ascii_tree: bool = False
    load_order: bool = False
    compare_npm: bool = False
