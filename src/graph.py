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

Константы модуля:
    TIMEOUT: максимальное время ожидания ответа от npm Registry (секунды).
    HTTP_404: HTTP-код «пакет не найден».
    MAX_ATTEMPTS: максимальное количество попыток загрузить метаданные.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from src.errors import ValidationError

TIMEOUT = 15
HTTP_404 = 404
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


def _load_repository_json(path: str) -> Any:
    """Читает JSON-файл и возвращает разобранный Python-объект.

    Args:
        path: Путь к локальному JSON-файлу.

    Returns:
        Разобранный JSON-объект.

    Raises:
        ValidationError: Если файл недоступен или JSON некорректен.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(
            f"Не удалось прочитать тестовый репозиторий: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Некорректный JSON в тестовом репозитории: {exc}"
        ) from exc


def read_test_repository(path: str) -> dict[str, dict[str, Any]]:
    """Загружает и проверяет описание тестового графа из JSON-файла.

    Проверяются: доступность файла и корректность JSON, объектный
    корень, имена пакетов из заглавных A–Z, объектные описания пакетов
    и поле dependencies, а также типы имён и версий зависимостей.

    Args:
        path: Путь к локальному JSON-файлу с описанием пакетов.

    Returns:
        Словарь {имя пакета: описание пакета}.

    Raises:
        ValidationError: Если файл недоступен, JSON некорректен
            или данные не соответствуют ожидаемой структуре.
    """
    data = _load_repository_json(path)

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


def _raise_registry_http_error(
    exc: urllib.error.HTTPError,
    url: str,
    package_name: str,
) -> None:
    """Преобразует HTTP-ошибку npm Registry в ValidationError."""
    if exc.code == HTTP_404:
        raise ValidationError(
            f"Пакет {package_name!r} не найден: {url}"
        ) from exc
    raise ValidationError(
        f"npm Registry вернул HTTP {exc.code}: {url}"
    ) from exc


def fetch_registry_package(
    registry: str,
    package_name: str,
) -> dict[str, Any]:
    """Получает метаданные latest-версии пакета из npm Registry.

    Формирует URL с кодированием имени пакета и отправляет HTTP-запрос.
    Ответ декодируется из UTF-8 и разбирается как JSON, после чего
    проверяется, что данные — объект, а dependencies — словарь.
    HTTP 404 означает «пакет не найден». Сетевые ошибки повторяются
    до MAX_ATTEMPTS раз; при неудаче сообщается последняя причина.

    Args:
        registry: Базовый URL npm Registry.
        package_name: Имя пакета, метаданные которого нужно получить.

    Returns:
        Словарь с метаданными пакета из реестра.

    Raises:
        ValidationError: Если пакет не найден, сервер вернул ошибку,
            ответ некорректен или все попытки запроса не удались.
    """
    url, request = _build_registry_request(registry, package_name)
    last_error = None

    for _ in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
            return _parse_registry_response(raw, package_name)
        except urllib.error.HTTPError as exc:
            _raise_registry_http_error(exc, url, package_name)
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


def _enqueue_new_dependencies(
    dependencies: dict[str, str],
    scheduled: set[str],
    queue: deque[str],
) -> None:
    """Добавляет в очередь ещё не запланированные зависимости."""
    for dependency in dependencies:
        if dependency not in scheduled:
            scheduled.add(dependency)
            queue.append(dependency)


def build_dependency_graph(
    package_name: str,
    repo: str,
    test_mode: bool = False,
) -> dict[str, dict[str, str]]:
    """Строит транзитивный граф зависимостей алгоритмом BFS без рекурсии.

    Args:
        package_name: Имя пакета, с которого начинается обход.
        repo: Путь к тестовому JSON-файлу или URL npm Registry.
        test_mode: Если True, данные берутся из локального файла repo.

    Returns:
        Граф {имя пакета: {имя зависимости: версия}}.

    Raises:
        ValidationError: Если данные пакета некорректны или отсутствуют.
    """
    test_repository: dict[str, dict[str, Any]] = {}
    if test_mode:
        test_repository = read_test_repository(repo)

    graph: dict[str, dict[str, str]] = {}
    visited: set[str] = set()
    scheduled: set[str] = {package_name}
    queue: deque[str] = deque([package_name])

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
        _enqueue_new_dependencies(dependencies, scheduled, queue)

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


def _push_children(
    stack: list[tuple[str, str, frozenset[str], bool, bool]],
    dependencies: list[str],
    child_prefix: str,
    next_ancestors: frozenset[str],
) -> None:
    """Кладёт в стек дочерние узлы в обратном порядке для LIFO-вывода."""
    last_index = len(dependencies) - 1
    for index in range(last_index, -1, -1):
        stack.append(
            (
                dependencies[index],
                child_prefix,
                next_ancestors,
                index == last_index,
                False,
            )
        )


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

    stack: list[tuple[str, str, frozenset[str], bool, bool]] = [
        (root, "", frozenset(), True, True)
    ]

    while stack:
        package, prefix, ancestors, is_last, is_root = stack.pop()
        print(_format_tree_node(package, prefix, ancestors, is_last, is_root))

        if package in ancestors:
            continue

        next_ancestors = ancestors | {package}
        dependencies = sorted(graph.get(package, {}))
        child_prefix = (
            "" if is_root else prefix + ("    " if is_last else "|   ")
        )
        _push_children(stack, dependencies, child_prefix, next_ancestors)


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


def _raise_cycle_error(dependency_count: dict[str, int]) -> None:
    """Сообщает о циклических зависимостях, оставшихся необработанными."""
    cyclic_packages = sorted(
        package for package, count in dependency_count.items() if count > 0
    )
    raise ValidationError(
        "Невозможно определить полный порядок загрузки: "
        "обнаружены циклические зависимости. "
        f"Затронутые пакеты: {', '.join(cyclic_packages)}"
    )


def get_load_order(
    graph: dict[str, dict[str, str]],
) -> list[str]:
    """Определяет порядок загрузки пакетов алгоритмом Кана (без рекурсии).

    Каждая зависимость должна идти раньше пакета, которому она нужна.

    Args:
        graph: Граф {пакет: {зависимость: версия}}.

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
        _raise_cycle_error(dependency_count)

    return load_order
