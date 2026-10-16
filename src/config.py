"""Хранение конфигурации приложения."""

from dataclasses import dataclass


@dataclass
class AppConfig:
    """Конфигурация приложения, собранная из параметров командной строки."""

    package_name: str
    repo: str
    test_mode: bool
    output_file: str
    ascii_tree: bool

    def to_key_value(self) -> str:
        """Возвращает параметры в формате ключ-значение."""
        lines = [
            f"package_name = {self.package_name}",
            f"repo = {self.repo}",
            f"test_mode = {self.test_mode}",
            f"output_file = {self.output_file}",
            f"ascii_tree = {self.ascii_tree}",
        ]
        return "\n".join(lines)
