"""Пользовательские исключения приложения."""


class ConfigError(Exception):
    """Ошибка конфигурации приложения."""


class ValidationError(ConfigError):
    """Ошибка валидации параметров."""
