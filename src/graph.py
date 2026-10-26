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

    Если файл не удаётся прочитать, JSON некорректен или структура
    не соответствует ожидаемому формату, функция вызывает ValidationError.

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
        if (
            not isinstance(name, str)
            or not name
            or not all("A" <= char <= "Z" for char in name)
        ):
            raise ValidationError(
                f"Недопустимое имя пакета {name!r}: "
                "используйте заглавные латинские буквы."
            )

        if not isinstance(package, dict):
            raise ValidationError(
                f"Описание пакета {name} должно быть объектом."
            )

        dependencies = package.get("dependencies", {})
        if not isinstance(dependencies, dict):
            raise ValidationError(
                f"Зависимости пакета {name} должны быть объектом."
            )

        for dep_name, version in dependencies.items():
            if not isinstance(dep_name, str) or not isinstance(
                version, (str, int, float)
            ):
                raise ValidationError(
                    f"Некорректная зависимость пакета {name}."
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

    last_error = None

    for _ in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))

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

        except urllib.error.HTTPError as exc:
            if exc.code == HTTP_404:
                raise ValidationError(
                    f"Пакет {package_name!r} не найден: {url}"
                ) from exc

            raise ValidationError(
                f"npm Registry вернул HTTP {exc.code}: {url}"
            ) from exc

        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            last_error = exc

        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError(
                f"Некорректный ответ npm Registry: {url}"
            ) from exc

    raise ValidationError(
        f"Не удалось загрузить пакет {package_name!r} "
        f"по адресу {url} после {MAX_ATTEMPTS} попыток. "
        f"Причина: {last_error}"
    )


def build_dependency_graph(
    package_name: str,
    repo: str,
    test_mode: bool = False,
) -> dict[str, dict[str, str]]:
    """Строит полный транзитивный граф зависимостей алгоритмом BFS.

    Начинает обход с указанного пакета и последовательно находит
    его зависимости, а затем зависимости найденных пакетов.
    Обход выполняется без рекурсии с помощью очереди.
    """
    # Словарь для хранения данных тестового репозитория.
    # Изначально он пустой и заполняется только в тестовом режиме.
    test_repository: dict[str, dict[str, Any]] = {}

    # Если включён тестовый режим, читаем и проверяем JSON-файл.
    if test_mode:
        test_repository = read_test_repository(repo)

    # Итоговый граф:
    # ключ — имя пакета, значение — его прямые зависимости с версиями.
    graph: dict[str, dict[str, str]] = {}

    # Множество обработанных пакетов.
    # Оно позволяет не обрабатывать один и тот же пакет повторно.
    visited: set[str] = set()

    # Множество запланированных пакетов.
    # Пакет добавляется сюда, когда помещается в очередь.
    # Это предотвращает повторное добавление пакета в очередь.
    scheduled: set[str] = {package_name}

    # Очередь BFS (FIFO):
    # первым обрабатывается пакет, который был добавлен раньше.
    # Начинаем обход с пакета, указанного пользователем.
    queue = deque([package_name])

    # Продолжаем обход, пока в очереди остаются пакеты.
    while queue:
        # Получаем первый пакет из очереди и удаляем его оттуда.
        current = queue.popleft()

        # Если пакет уже обработан, пропускаем его.
        # Это дополнительная защита от повторной обработки.
        if current in visited:
            continue

        # Отмечаем пакет как обработанный.
        # Теперь алгоритм не будет повторно исследовать его зависимости.
        visited.add(current)

        # Выбираем источник данных в зависимости от режима работы.
        if test_mode:
            # Проверяем, есть ли текущий пакет в тестовом JSON.
            if current not in test_repository:
                raise ValidationError(
                    f"Пакет {current!r} отсутствует " "в тестовом репозитории."
                )

            # Получаем описание пакета из локального репозитория.
            package_data = test_repository[current]
        else:
            # В обычном режиме запрашиваем метаданные пакета из npm Registry.
            package_data = fetch_registry_package(repo, current)

        # Извлекаем прямые зависимости текущего пакета.
        # Если поле отсутствует или содержит None, используем пустой словарь.
        raw_dependencies = package_data.get("dependencies") or {}

        # Проверяем, что зависимости представлены словарём.
        if not isinstance(raw_dependencies, dict):
            raise ValidationError(f"Некорректные зависимости пакета {current}.")

        # Приводим имена зависимостей и версии к строкам.
        # Это обеспечивает единый формат данных в итоговом графе.
        dependencies = {
            str(name): str(version)
            for name, version in raw_dependencies.items()
        }

        # Сохраняем прямые зависимости текущего пакета в графе.
        # Даже если зависимостей нет, пакет будет присутствовать в графе
        # со значением {}.
        graph[current] = dependencies

        # Рассматриваем каждую прямую зависимость текущего пакета.
        for dependency in dependencies:
            # Если пакет ещё не планировался для обработки,
            # добавляем его в множество запланированных.
            if dependency not in scheduled:
                scheduled.add(dependency)

                # Помещаем найденную зависимость в конец очереди.
                # Её собственные зависимости будут изучены позднее.
                queue.append(dependency)

    # Когда очередь опустела, все достижимые пакеты обработаны.
    # Возвращаем построенный граф зависимостей.
    return graph


def print_dependency_graph(
    graph: dict[str, dict[str, str]],
) -> None:
    """Выводит граф зависимостей в текстовом виде."""
    # Подсчитываем общее количество связей.
    # Каждая прямая зависимость одного пакета считается отдельным ребром.
    edge_count = sum(len(deps) for deps in graph.values())

    # Выводим заголовок и общую статистику графа.
    # Количество пакетов соответствует числу ключей в графе.
    print("\nГраф транзитивных зависимостей:")
    print(f"Всего пакетов: {len(graph)}")
    print(f"Всего связей: {edge_count}")

    # Перебираем пакеты в алфавитном порядке для стабильного вывода.
    for package in sorted(graph):
        # Получаем словарь прямых зависимостей текущего пакета.
        dependencies = graph[package]

        if not dependencies:
            print(f"{package}: зависимостей нет")
            continue

        # Выводим имя пакета, у которого есть зависимости.
        print(f"{package}:")

        # Выводим каждую зависимость и её версию.
        # Сортировка делает результат более удобным для чтения.
        for name, version in sorted(dependencies.items()):
            print(f"  -> {name} ({version})")


def print_ascii_tree(
    root: str,
    graph: dict[str, dict[str, str]],
) -> None:
    """Печатает ASCII-дерево зависимостей без использования рекурсии."""
    # Выводим заголовок дерева и имя корневого пакета.
    print(f"\nASCII-дерево зависимостей: {root}")

    # Создаём стек для обхода дерева без рекурсии.
    # Каждый элемент содержит:
    # 1. Имя пакета.
    # 2. Префикс отступа для отображения ветви.
    # 3. Множество предков пакета в текущей ветви.
    # 4. Признак того, что пакет является последним среди соседей.
    # 5. Признак того, что пакет является корневым.
    #
    # frozenset() — неизменяемое пустое множество предков.
    # Корневой пакет помещается в стек первым.
    stack = [(root, "", frozenset(), True, True)]

    # Обходим узлы, пока стек не станет пустым.
    while stack:
        # Извлекаем последний добавленный элемент стека.
        package, prefix, ancestors, is_last, is_root = stack.pop()

        # Корневой пакет выводится без символов ветвей.
        if is_root:
            print(package)
        else:
            # Для последнего дочернего узла используется `--,
            # для остальных — |--.
            branch = "`-- " if is_last else "|-- "

            # Если пакет уже встречался среди предков текущей ветви,
            # отмечаем его как цикл.
            cycle_mark = " [цикл]" if package in ancestors else ""

            # Выводим пакет с нужным отступом и, если необходимо, меткой цикла.
            print(f"{prefix}{branch}{package}{cycle_mark}")

        # Если пакет уже находится среди предков, цикл обнаружен.
        # Повторно раскрывать его зависимости не нужно.
        if package in ancestors:
            continue

        # Создаём множество предков для следующих узлов.
        # Оператор | объединяет предков с именем текущего пакета.
        # Исходное множество ancestors при этом не изменяется.
        next_ancestors = ancestors | {package}

        # Получаем зависимости пакета и сортируем их по имени.
        # Если пакет отсутствует в графе, используем пустой словарь.
        dependencies = sorted(graph.get(package, {}))

        # Подготавливаем отступ для дочерних узлов.
        if is_root:
            # У корневого пакета нет дополнительного префикса.
            child_prefix = ""
        else:
            # Если текущий узел последний, вертикальная линия
            # для продолжения ветви не нужна — добавляем пробелы.
            # Иначе сохраняем вертикальную линию | для соседних ветвей.
            child_prefix = prefix + ("    " if is_last else "|   ")

        # Стек работает по принципу LIFO, поэтому зависимости
        # добавляем в обратном порядке. При извлечении они будут
        # выведены в исходном алфавитном порядке.
        for index in range(len(dependencies) - 1, -1, -1):
            # Получаем имя зависимости по индексу.
            dependency = dependencies[index]

            # Добавляем зависимость в стек вместе с информацией
            # о её положении в дереве и предках текущей ветви.
            stack.append(
                (
                    dependency,
                    child_prefix,
                    next_ancestors,
                    # Последней является зависимость с максимальным индексом
                    # Этот признак определяет символ её ветви и отступы потомков
                    index == len(dependencies) - 1,
                    # Добавляемая зависимость не является корнем дерева
                    False,
                )
            )
