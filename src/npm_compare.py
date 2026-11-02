"""Сравнение графа зависимостей с деревом, полученным через npm."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class NpmCompareError(Exception):
    """Ошибка получения дерева зависимостей через npm."""


def _collect_children(
    dependencies: dict[str, Any],
    parent_name: str,
    nodes: set[str],
    edges: set[tuple[str, str]],
) -> None:
    """Рекурсивно обходит дочерние узлы и накапливает пакеты и связи.

    Args:
        dependencies: Словарь {имя зависимости: узел} из поля dependencies.
        parent_name: Имя родительского пакета для добавления рёбер.
        nodes: Множество имён пакетов для накопления.
        edges: Множество рёбер (родитель, зависимость) для накопления.
    """
    for dependency_name, dependency_node in dependencies.items():
        if not isinstance(dependency_node, dict):
            continue
        child = dict(dependency_node)
        child.setdefault("name", dependency_name)
        _collect_npm_graph(child, parent_name, nodes, edges)


def _collect_npm_graph(
    node: dict[str, Any],
    parent_name: str | None = None,
    nodes: set[str] | None = None,
    edges: set[tuple[str, str]] | None = None,
) -> tuple[set[str], set[tuple[str, str]]]:
    """Собирает имена пакетов и связи из дерева npm.

    Рекурсивно обходит словарь зависимостей и накапливает множества
    имён пакетов и рёбер (родитель, зависимость).

    Args:
        node: Узел дерева npm с полями name и dependencies.
        parent_name: Имя родительского пакета или None для корня.
        nodes: Множество имён пакетов (создаётся при None).
        edges: Множество рёбер (создаётся при None).

    Returns:
        Кортеж (nodes, edges) с накопленными значениями.
    """
    if nodes is None:
        nodes = set()
    if edges is None:
        edges = set()

    name = node.get("name")
    if not isinstance(name, str) or not name:
        return nodes, edges

    nodes.add(name)
    if parent_name is not None:
        edges.add((parent_name, name))

    dependencies = node.get("dependencies", {})
    if isinstance(dependencies, dict):
        _collect_children(dependencies, name, nodes, edges)

    return nodes, edges


def _find_npm_executable() -> str:
    """Возвращает путь к исполняемому файлу npm.

    Raises:
        NpmCompareError: Если npm не найден в PATH.
    """
    npm_path = shutil.which("npm")
    if npm_path is None:
        raise NpmCompareError(
            "Команда npm не найдена. Установи Node.js вместе с npm."
        )
    return npm_path


def _install_package(
    npm_path: str,
    workdir: Path,
    package_name: str,
) -> None:
    """Устанавливает пакет во временный npm-проект.

    Args:
        npm_path: Путь к исполняемому файлу npm.
        workdir: Временный рабочий каталог.
        package_name: Имя устанавливаемого пакета.

    Raises:
        NpmCompareError: Если npm завершился с ошибкой.
    """
    install = subprocess.run(
        [
            npm_path,
            "install",
            "--package-lock=false",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            package_name,
        ],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    if install.returncode != 0:
        details = (install.stderr or install.stdout).strip()
        raise NpmCompareError("npm не смог установить пакет: " + details[:1200])


def _parse_npm_tree(
    result: subprocess.CompletedProcess,
    package_name: str,
) -> dict[str, Any]:
    """Разбирает вывод npm ls и извлекает поддерево целевого пакета.

    Args:
        result: Результат вызова npm ls --all --json.
        package_name: Имя целевого пакета.

    Returns:
        Словарь-поддерево целевого пакета с заполненным полем name.

    Raises:
        NpmCompareError: Если JSON некорректен, структура неожиданна
            или целевой пакет отсутствует в дереве.
    """
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        details = (result.stderr or result.stdout).strip()
        raise NpmCompareError(
            "Не удалось разобрать ответ npm: " + details[:1200]
        ) from exc

    if not isinstance(data, dict):
        raise NpmCompareError("npm вернул неожиданный формат дерева.")

    top_dependencies = data.get("dependencies", {})
    if not isinstance(top_dependencies, dict):
        raise NpmCompareError("В ответе npm отсутствует дерево пакетов.")

    target = top_dependencies.get(package_name)
    if not isinstance(target, dict):
        raise NpmCompareError(f"Пакет {package_name!r} не найден в дереве npm.")

    target_node = dict(target)
    target_node["name"] = package_name
    return target_node


def _run_npm_tree(
    package_name: str,
) -> tuple[set[str], set[tuple[str, str]]]:
    """Устанавливает пакет во временную папку и получает дерево npm.

    Args:
        package_name: Имя пакета для установки и анализа.

    Returns:
        Кортеж (nodes, edges) с множествами пакетов и рёбер.

    Raises:
        NpmCompareError: Если npm недоступен, установка не удалась,
            вывод некорректен или дерево пустое.
    """
    npm_path = _find_npm_executable()

    with tempfile.TemporaryDirectory(
        prefix="dependency-visualizer-"
    ) as temp_dir:
        workdir = Path(temp_dir)
        _install_package(npm_path, workdir, package_name)

        result = subprocess.run(
            [npm_path, "ls", "--all", "--json"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        target_node = _parse_npm_tree(result, package_name)
        nodes, edges = _collect_npm_graph(target_node)

        if not nodes:
            raise NpmCompareError("npm вернул пустое дерево зависимостей.")

        return nodes, edges


def _compute_differences(
    graph: dict[str, dict[str, str]],
    npm_nodes: set[str],
    npm_edges: set[tuple[str, str]],
) -> dict[str, Any]:
    """Вычисляет различия между графом приложения и деревом npm.

    Args:
        graph: Граф приложения.
        npm_nodes: Множество пакетов из дерева npm.
        npm_edges: Множество рёбер из дерева npm.

    Returns:
        Словарь с ключами app_nodes, app_edges, missing_nodes,
        extra_nodes, missing_edges, extra_edges.
    """
    app_nodes = set(graph)
    app_edges = {
        (parent, dependency)
        for parent, dependencies in graph.items()
        for dependency in dependencies
    }

    return {
        "app_nodes": app_nodes,
        "app_edges": app_edges,
        "missing_nodes": sorted(app_nodes - npm_nodes),
        "extra_nodes": sorted(npm_nodes - app_nodes),
        "missing_edges": sorted(app_edges - npm_edges),
        "extra_edges": sorted(npm_edges - app_edges),
    }


def _print_summary(
    diff: dict[str, Any],
    npm_nodes: set[str],
    npm_edges: set[tuple[str, str]],
) -> bool:
    """Печатает общую статистику сравнения.

    Args:
        diff: Словарь различий из _compute_differences.
        npm_nodes: Множество пакетов из дерева npm.
        npm_edges: Множество рёбер из дерева npm.

    Returns:
        True, если различий нет; False в противном случае.
    """
    print("\nСравнение графа с npm:")
    print(f"Пакетов в графе программы: {len(diff['app_nodes'])}")
    print(f"Пакетов в дереве npm:      {len(npm_nodes)}")
    print(f"Связей в графе программы:  {len(diff['app_edges'])}")
    print(f"Связей в дереве npm:       {len(npm_edges)}")

    has_diff = any(
        (
            diff["missing_nodes"],
            diff["extra_nodes"],
            diff["missing_edges"],
            diff["extra_edges"],
        )
    )
    if not has_diff:
        print("Результат: граф совпадает с деревом npm.")
    else:
        print("Результат: обнаружены различия.")
    return not has_diff


def _print_differences(diff: dict[str, Any]) -> None:
    """Печатает списки различий между графом и деревом npm.

    Args:
        diff: Словарь различий из _compute_differences.
    """
    if diff["missing_nodes"]:
        print("\nПакеты есть в графе программы, но отсутствуют в npm:")
        for name in diff["missing_nodes"]:
            print(f"  - {name}")

    if diff["extra_nodes"]:
        print("\nПакеты есть в npm, но отсутствуют в графе программы:")
        for name in diff["extra_nodes"]:
            print(f"  + {name}")

    if diff["missing_edges"]:
        print("\nСвязи есть в графе программы, но отсутствуют в npm:")
        for parent, dependency in diff["missing_edges"]:
            print(f"  - {parent} -> {dependency}")

    if diff["extra_edges"]:
        print("\nСвязи есть в npm, но отсутствуют в графе программы:")
        for parent, dependency in diff["extra_edges"]:
            print(f"  + {parent} -> {dependency}")


def compare_with_npm(
    package_name: str,
    graph: dict[str, dict[str, str]],
) -> None:
    """Сравнивает граф приложения с деревом зависимостей npm.

    Получает дерево зависимостей пакета через npm, вычисляет
    различия по множествам пакетов и связей и выводит отчёт.

    Args:
        package_name: Имя пакета для установки и сравнения.
        graph: Граф зависимостей приложения.

    Raises:
        NpmCompareError: Если npm недоступен, установка не удалась,
            вывод некорректен или дерево пустое.
    """
    try:
        npm_nodes, npm_edges = _run_npm_tree(package_name)
    except (
        NpmCompareError,
        subprocess.TimeoutExpired,
        OSError,
    ) as exc:
        if isinstance(exc, NpmCompareError):
            raise
        raise NpmCompareError(f"Не удалось выполнить npm: {exc}") from exc

    diff = _compute_differences(graph, npm_nodes, npm_edges)
    if _print_summary(diff, npm_nodes, npm_edges):
        return

    _print_differences(diff)
