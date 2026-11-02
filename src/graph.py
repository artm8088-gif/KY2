"""Построение транзитивного графа зависимостей алгоритмом BFS.

Модуль позволяет получать зависимости пакетов из двух источников:
1. Локального JSON-файла, используемого в тестовом режиме.
2. npm Registry, из которого загружаются метаданные latest-версии пакета.

Для построения полного графа используется алгоритм поиска в ширину (BFS).
Он последовательно обрабатывает пакеты и добавляет в граф все обнаруженные
зависимости, включая зависимости зависимостей.

Для предотвращения повторной обработки пакетов используются множества
visited и scheduled. Благодаря этому алгоритм корректно работает с графами,
в которых есть общие зависимости и циклические связи.

Рекурсия при построении графа не используется.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from src.errors import ValidationError

# Максимальное время ожидания ответа от npm Registry в секундах.
TIMEOUT = 15

# HTTP-код, обозначающий, что запрашиваемый пакет не найден.
HTTP_404 = 404

# Максимальное количество попыток загрузить метаданные пакета.
MAX_ATTEMPTS = 3


def _validate_package_name(name: Any) -> None:
    """Проверяет, что имя пакета состоит из заглавных латинских букв A–Z."""
    if (
        not isinstance(name, str)
        or not name
        or not all("A" <= char <= "Z" for char in name)
    ):
        raise ValidationError(
            f"Недопустимое имя пакета {name!r}: "
            "используйте заглавные латинские буквы."
        )


def _validate_package_dependencies(name: str, package: Any) -> None:
    """Проверяет структуру описания пакета и его зависимостей."""
    if not isinstance(package, dict):
        raise ValidationError(f"Описание пакета {name} должно быть объектом.")

    dependencies = package.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ValidationError(
            f"Зависимости пакета {name} должны быть объектом."
        )

    for dep_name, version in dependencies.items():
        if not isinstance(dep_name, str) or not isinstance(
            version, (str, int, float)
        ):
            raise ValidationError(f"Некорректная зависимость пакета {name}.")


def read_test_repository(path: str) -> dict[str, dict[str, Any]]:
    """Загружает и проверяет описание тестового графа из JSON-файла.

    Функция читает локальный файл, преобразует JSON в Python-объект
    и проверяет его структуру перед использованием при построении графа.

    Проверяются следующие условия:
    - файл доступен для чтения и содержит корректный JSON;
    - корневой элемент JSON является объектом;
    - имена пакетов состоят только из заглавных латинских букв A–Z;
    - описание каждого пакета является объектом;
    - поле dependencies является объектом;
    - имя каждой зависимости является строкой, а её версия —
      строкой, целым числом или числом с плавающей точкой.

    Args:
        path: Путь к локальному JSON-файлу с описанием пакетов
            и их зависимостей.

    Returns:
        Словарь, в котором ключи — имена пакетов, а значения —
        их описания, включая поле dependencies.

    Raises:
        ValidationError: Если файл недоступен, JSON некорректен
            или данные не соответствуют ожидаемой структуре.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(
            f"Не удалось прочитать тестовый репозиторий: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Некорректный JSON в тестовом репозитории: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError("Тестовый репозиторий должен быть JSON-объектом.")

    for name, package in data.items():
        _validate_package_name(name)
        _validate_package_dependencies(name, package)

    return data


def _build_registry_request(
    registry: str,
    package_name: str,
) -> tuple[str, urllib.request.Request]:
    """Формирует URL и HTTP-запрос к npm Registry для пакета."""
    base = registry.rstrip("/") + "/"
    encoded_name = urllib.parse.quote(package_name, safe="@")
    url = urllib.parse.urljoin(base, encoded_name + "/latest")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "dependency-visualizer/1.0",
            "Accept": "application/json",
        },
    )
    return url, request


def _parse_registry_response(
    raw: bytes,
    package_name: str,
) -> dict[str, Any]:
    """Разбирает тело ответа npm Registry и проверяет его структуру."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(
            f"Некорректный ответ npm Registry для {package_name}."
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError(
            f"Ожидался JSON-объект для пакета {package_name}."
        )

    dependencies = data.get("dependencies") or {}
    if not isinstance(dependencies, dict):
        raise ValidationError(
            f"Некорректное поле dependencies у {package_name}."
        )

    return data


def fetch_registry_package(
    registry: str,
    package_name: str,
) -> dict[str, Any]:
    """Получает метаданные latest-версии пакета из npm Registry.

    Функция формирует URL запроса, кодируя имя пакета для корректной
    передачи в адресе, и отправляет HTTP-запрос к реестру npm.

    При успешном ответе тело HTTP-ответа декодируется из UTF-8
    и разбирается как JSON. Затем проверяется, что полученные данные
    представлены объектом, а поле dependencies — словарём.

    Если сервер возвращает HTTP 404, функция сообщает, что пакет
    не найден. Другие HTTP-ошибки преобразуются в ValidationError.

    Ошибки соединения, тайм-ауты и другие сетевые ошибки повторяются
    до MAX_ATTEMPTS раз. Если все попытки завершились неудачно,
    функция сообщает последнюю обнаруженную причину ошибки.

    Args:
        registry: Базовый URL npm Registry, например
            https://registry.npmjs.org/.
        package_name: Имя пакета, метаданные которого нужно получить.

    Returns:
        Словарь с метаданными пакета, полученными из реестра.

    Raises:
        ValidationError: Если пакет не найден, сервер вернул ошибку,
            ответ содержит некорректный JSON или данные имеют
            неподходящую структуру, либо все попытки запроса не удались.

    Note:
        Запрашивается endpoint /latest. Функция не разрешает диапазоны
        версий зависимостей и не загружает архивы пакетов.
    """
    url, request = _build_registry_request(registry, package_name)
    last_error = None

    for _ in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
            return _parse_registry_response(raw, package_name)

        except urllib.error.HTTPError as exc:
            if exc.code == HTTP_404:
                raise ValidationError(
                    f"Пакет {package_name!r} не найден: {url}"
                ) from exc
            raise ValidationError(
                f"npm Registry вернул HTTP {exc.code}: {url}"
            ) from exc

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc

    raise ValidationError(
        f"Не удалось загрузить пакет {package_name!r} "
        f"по адресу {url} после {MAX_ATTEMPTS} попыток. "
        f"Причина: {last_error}"
    )


def _load_package_data(
    current: str,
    repo: str,
    test_mode: bool,
    test_repository: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Возвращает описание пакета из тестового репозитория или npm Registry."""
    if not test_mode:
        return fetch_registry_package(repo, current)

    if current not in test_repository:
        raise ValidationError(
            f"Пакет {current!r} отсутствует в тестовом репозитории."
        )
    return test_repository[current]


def _normalize_dependencies(
    package_data: dict[str, Any],
    current: str,
) -> dict[str, str]:
    """Извлекает и приводит зависимости пакета к виду {str: str}."""
    raw_dependencies = package_data.get("dependencies") or {}
    if not isinstance(raw_dependencies, dict):
        raise ValidationError(f"Некорректные зависимости пакета {current}.")
    return {
        str(name): str(version) for name, version in raw_dependencies.items()
    }


def build_dependency_graph(
    package_name: str,
    repo: str,
    test_mode: bool = False,
) -> dict[str, dict[str, str]]:
    """Строит полный транзитивный граф зависимостей алгоритмом BFS.

    Начинает обход с указанного пакета и последовательно находит
    его зависимости, а затем зависимости найденных пакетов.
    Обход выполняется без рекурсии с помощью очереди.

    Args:
        package_name: Имя пакета, с которого начинается обход.
        repo: Путь к тестовому JSON-файлу либо базовый URL npm Registry.
        test_mode: Если True, данные берутся из локального файла repo.

    Returns:
        Граф, в котором ключи — имена пакетов, а значения — словари
        их прямых зависимостей с версиями.

    Raises:
        ValidationError: Если данные пакета некорректны или отсутствуют.
    """
    test_repository: dict[str, dict[str, Any]] = {}
    if test_mode:
        test_repository = read_test_repository(repo)

    graph: dict[str, dict[str, str]] = {}
    visited: set[str] = set()
    scheduled: set[str] = {package_name}
    queue = deque([package_name])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        package_data = _load_package_data(
            current, repo, test_mode, test_repository
        )
        dependencies = _normalize_dependencies(package_data, current)
        graph[current] = dependencies

        for dependency in dependencies:
            if dependency not in scheduled:
                scheduled.add(dependency)
                queue.append(dependency)

    return graph


def print_dependency_graph(
    graph: dict[str, dict[str, str]],
) -> None:
    """Выводит граф зависимостей в текстовом виде.

    Печатает общую статистику (число пакетов и связей) и перечисляет
    пакеты в алфавитном порядке вместе с их прямыми зависимостями.

    Args:
        graph: Граф зависимостей, построенный build_dependency_graph.
    """
    edge_count = sum(len(deps) for deps in graph.values())

    print("\nГраф транзитивных зависимостей:")
    print(f"Всего пакетов: {len(graph)}")
    print(f"Всего связей: {edge_count}")

    for package in sorted(graph):
        dependencies = graph[package]

        if not dependencies:
            print(f"{package}: зависимостей нет")
            continue

        print(f"{package}:")
        for name, version in sorted(dependencies.items()):
            print(f"  -> {name} ({version})")


def _format_tree_node(
    package: str,
    prefix: str,
    ancestors: frozenset[str],
    is_last: bool,
    is_root: bool,
) -> str:
    """Формирует строку вывода для одного узла ASCII-дерева."""
    if is_root:
        return package

    branch = "`-- " if is_last else "|-- "
    cycle_mark = " [цикл]" if package in ancestors else ""
    return f"{prefix}{branch}{package}{cycle_mark}"


def print_ascii_tree(
    root: str,
    graph: dict[str, dict[str, str]],
) -> None:
    """Печатает ASCII-дерево зависимостей без использования рекурсии.

    Узлы, которые уже встречались среди предков текущей ветви,
    помечаются меткой [цикл] и повторно не раскрываются.

    Args:
        root: Имя корневого пакета.
        graph: Граф зависимостей, построенный build_dependency_graph.
    """
    print(f"\nASCII-дерево зависимостей: {root}")

    stack = [(root, "", frozenset(), True, True)]

    while stack:
        package, prefix, ancestors, is_last, is_root = stack.pop()
        print(_format_tree_node(package, prefix, ancestors, is_last, is_root))

        if package in ancestors:
            continue

        next_ancestors = ancestors | {package}
        dependencies = sorted(graph.get(package, {}))

        if is_root:
            child_prefix = ""
        else:
            child_prefix = prefix + ("    " if is_last else "|   ")

        for index in range(len(dependencies) - 1, -1, -1):
            dependency = dependencies[index]
            stack.append(
                (
                    dependency,
                    child_prefix,
                    next_ancestors,
                    index == len(dependencies) - 1,
                    False,
                )
            )


def _build_dependency_count(
    graph: dict[str, dict[str, str]],
) -> dict[str, int]:
    """Считает число зависимостей каждого пакета, присутствующих в графе."""
    return {
        package: sum(dependency in graph for dependency in dependencies)
        for package, dependencies in graph.items()
    }


def _build_dependents(
    graph: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    """Строит обратные связи: зависимость -> пакеты, которым она нужна."""
    dependents: dict[str, list[str]] = {package: [] for package in graph}
    for package, dependencies in graph.items():
        for dependency in dependencies:
            if dependency in graph:
                dependents[dependency].append(package)
    return dependents


def get_load_order(
    graph: dict[str, dict[str, str]],
) -> list[str]:
    """Определяет порядок загрузки пакетов топологической сортировкой.

    Пакеты располагаются так, чтобы каждая зависимость находилась
    раньше пакета, которому она необходима.

    Используется алгоритм Кана без рекурсии. Если граф содержит цикл,
    полный порядок загрузки построить невозможно.

    Args:
        graph: Граф, в котором ключи — пакеты, а значения —
            словари их прямых зависимостей.

    Returns:
        Список имён пакетов в порядке загрузки.

    Raises:
        ValidationError: Если граф содержит циклические зависимости.
    """
    dependency_count = _build_dependency_count(graph)
    dependents = _build_dependents(graph)

    queue = deque(
        sorted(
            package for package, count in dependency_count.items() if count == 0
        )
    )

    load_order: list[str] = []

    while queue:
        package = queue.popleft()
        load_order.append(package)

        for dependent in sorted(dependents[package]):
            dependency_count[dependent] -= 1
            if dependency_count[dependent] == 0:
                queue.append(dependent)

    if len(load_order) != len(graph):
        cyclic_packages = sorted(
            package for package, count in dependency_count.items() if count > 0
        )
        raise ValidationError(
            "Невозможно определить полный порядок загрузки: "
            "обнаружены циклические зависимости. "
            f"Затронутые пакеты: {', '.join(cyclic_packages)}"
        )

    return load_order
