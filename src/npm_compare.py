"""Сравнение графа зависимостей с деревом, полученным через npm."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class NpmCompareError(Exception):
    """Ошибка получения дерева зависимостей через npm."""


def _collect_npm_graph(
    node: dict[str, Any],
    parent_name: str | None = None,
    nodes: set[str] | None = None,
    edges: set[tuple[str, str]] | None = None,
) -> tuple[set[str], set[tuple[str, str]]]:
    """Собирает имена пакетов и связи из дерева npm."""
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
        for dependency_name, dependency_node in dependencies.items():
            if not isinstance(dependency_node, dict):
                continue

            child = dict(dependency_node)
            child.setdefault("name", dependency_name)
            _collect_npm_graph(child, name, nodes, edges)

    return nodes, edges


def _run_npm_tree(
    package_name: str,
) -> tuple[set[str], set[tuple[str, str]]]:
    """Устанавливает пакет во временную папку и получает дерево npm."""
    npm_path = shutil.which("npm")
    if npm_path is None:
        raise NpmCompareError(
            "Команда npm не найдена. Установи Node.js вместе с npm."
        )

    with tempfile.TemporaryDirectory(
        prefix="dependency-visualizer-"
    ) as temp_dir:
        workdir = Path(temp_dir)

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
            raise NpmCompareError(
                "npm не смог установить пакет: " + details[:1200]
            )

        result = subprocess.run(
            [npm_path, "ls", "--all", "--json"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            details = (result.stderr or result.stdout).strip()
            raise NpmCompareError(
                "Не удалось разобрать ответ npm: " + details[:1200]
            ) from exc

        if not isinstance(data, dict):
            raise NpmCompareError("npm вернул неожиданный формат дерева.")

        # Исключаем временный корневой проект и начинаем с нужного пакета.
        top_dependencies = data.get("dependencies", {})
        if not isinstance(top_dependencies, dict):
            raise NpmCompareError("В ответе npm отсутствует дерево пакетов.")

        target = top_dependencies.get(package_name)
        if not isinstance(target, dict):
            raise NpmCompareError(
                f"Пакет {package_name!r} не найден в дереве npm."
            )

        target_node = dict(target)
        target_node["name"] = package_name
        nodes, edges = _collect_npm_graph(target_node)

        if not nodes:
            raise NpmCompareError("npm вернул пустое дерево зависимостей.")

        return nodes, edges


def compare_with_npm(
    package_name: str,
    graph: dict[str, dict[str, str]],
) -> None:
    """Сравнивает граф приложения с деревом зависимостей npm."""
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

    app_nodes = set(graph)
    app_edges = {
        (parent, dependency)
        for parent, dependencies in graph.items()
        for dependency in dependencies
    }

    missing_nodes = sorted(app_nodes - npm_nodes)
    extra_nodes = sorted(npm_nodes - app_nodes)
    missing_edges = sorted(app_edges - npm_edges)
    extra_edges = sorted(npm_edges - app_edges)

    print("\nСравнение графа с npm:")
    print(f"Пакетов в графе программы: {len(app_nodes)}")
    print(f"Пакетов в дереве npm:      {len(npm_nodes)}")
    print(f"Связей в графе программы:  {len(app_edges)}")
    print(f"Связей в дереве npm:       {len(npm_edges)}")

    if not any((missing_nodes, extra_nodes, missing_edges, extra_edges)):
        print("Результат: граф совпадает с деревом npm.")
        return

    print("Результат: обнаружены различия.")

    if missing_nodes:
        print("\nПакеты есть в графе программы, но отсутствуют в npm:")
        for name in missing_nodes:
            print(f"  - {name}")

    if extra_nodes:
        print("\nПакеты есть в npm, но отсутствуют в графе программы:")
        for name in extra_nodes:
            print(f"  + {name}")

    if missing_edges:
        print("\nСвязи есть в графе программы, но отсутствуют в npm:")
        for parent, dependency in missing_edges:
            print(f"  - {parent} -> {dependency}")

    if extra_edges:
        print("\nСвязи есть в npm, но отсутствуют в графе программы:")
        for parent, dependency in extra_edges:
            print(f"  + {parent} -> {dependency}")
