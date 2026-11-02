"""Создание визуализации дерева зависимостей npm.

Модуль использует штатные инструменты npm для получения дерева
установленных зависимостей выбранного пакета, преобразует полученные
данные в формат Mermaid и сохраняет результаты в корне проекта.

Для каждого пакета создаются три файла:
    <package>-npm.json — дерево зависимостей в формате JSON;
    <package>-npm.mmd  — описание графа на языке Mermaid;
    <package>-npm.svg  — графическое представление дерева.

Для получения дерева используются команды:
    npm init -y
    npm install <package>
    npm ls --all --json

Временный проект создаётся в отдельном каталоге и автоматически
удаляется после завершения обработки.

Пример запуска:
    python -m src.npm_visualization --package axios
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import mermaidx


def run_command(
    command: list[str],
    cwd: Path,
) -> subprocess.CompletedProcess:
    """Выполняет внешнюю команду в указанном рабочем каталоге.

    Команда запускается без оболочки, поэтому её аргументы передаются
    списком. Стандартный вывод и поток ошибок считываются как текст
    в кодировке UTF-8.

    Args:
        command: Команда и её аргументы, например
            ["npm", "ls", "--all", "--json"].
        cwd: Каталог, в котором должна выполняться команда.

    Returns:
        Результат выполнения subprocess.run, содержащий код завершения,
        стандартный вывод и поток ошибок.

    Raises:
        RuntimeError: Если команда завершилась с ненулевым кодом.
        OSError: Если операционная система не смогла запустить команду,
            например, если npm не установлен или недоступен через PATH.
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Команда завершилась с ошибкой:\n"
            f"{' '.join(command)}\n"
            f"{result.stderr}"
        )

    return result


def _escape_label(label: str) -> str:
    """Экранирует HTML-символы и кавычки для подписи узла Mermaid."""
    return (
        label.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def npm_tree_to_mermaid(package_name: str, tree: dict) -> str:
    """Преобразует дерево зависимостей npm в описание Mermaid.

    Каждому экземпляру пакета присваивается уникальный идентификатор
    узла. Это позволяет корректно отображать несколько экземпляров
    одного пакета, если они присутствуют в разных ветвях дерева.

    Узлы подписываются именем и версией пакета. Связь между узлами
    направлена от родительского пакета к его зависимости.

    Args:
        package_name: Имя анализируемого пакета. Используется для
            обозначения входного пакета в интерфейсе функции.
        tree: Словарь с данными о пакете, полученными от npm.

    Returns:
        Строка с описанием диаграммы Mermaid в формате flowchart TD.

    Note:
        Идентификаторы узлов формируются независимо от имён пакетов,
        поэтому специальные символы в именах не влияют на связи.
        Перед вставкой подписи в Mermaid экранируются некоторые
        HTML-символы и кавычки.
    """
    lines = ["flowchart TD"]
    state = {"counter": 0}

    def add_node(
        package: dict,
        parent_id: str | None = None,
    ) -> None:
        """Добавляет узел пакета и рекурсивно обрабатывает его зависимости.

        Args:
            package: Словарь с информацией о пакете и его зависимостях.
            parent_id: Идентификатор родительского узла. Для корневого
                пакета значение равно None.
        """
        name = package.get("name", "unknown")
        version = package.get("version", "unknown")

        node_id = f"n{state['counter']}"
        state["counter"] += 1

        label = _escape_label(f"{name}@{version}")
        lines.append(f'    {node_id}["{label}"]')

        if parent_id is not None:
            lines.append(f"    {parent_id} --> {node_id}")

        dependencies = package.get("dependencies", {})
        for dep_name, dependency in sorted(dependencies.items()):
            dependency.setdefault("name", dep_name)
            add_node(dependency, node_id)

    add_node(tree)
    return "\n".join(lines) + "\n"


def _install_and_get_tree(
    package_name: str,
    temp_dir: Path,
) -> dict:
    """Инициализирует npm-проект, устанавливает пакет и возвращает дерево.

    Args:
        package_name: Имя устанавливаемого npm-пакета.
        temp_dir: Временный каталог для npm-проекта.

    Returns:
        Словарь с деревом зависимостей из вывода npm ls --all --json.

    Raises:
        RuntimeError: Если npm завершился с ошибкой.
        ValueError: Если вывод npm содержит некорректный JSON.
    """
    run_command(["npm", "init", "-y"], temp_dir)
    run_command(
        [
            "npm",
            "install",
            package_name,
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ],
        temp_dir,
    )
    result = run_command(["npm", "ls", "--all", "--json"], temp_dir)
    return json.loads(result.stdout)


def _extract_package_tree(tree: dict, package_name: str) -> dict:
    """Извлекает поддерево целевого пакета из корневого дерева npm.

    Args:
        tree: Полное дерево зависимостей из вывода npm ls.
        package_name: Имя целевого пакета.

    Returns:
        Поддерево целевого пакета с гарантированно заполненным полем name.

    Raises:
        RuntimeError: Если пакет отсутствует в выводе npm ls.
    """
    root_dependencies = tree.get("dependencies", {})
    package_tree = root_dependencies.get(package_name)

    if package_tree is None:
        raise RuntimeError(f"Пакет {package_name} не найден в выводе npm ls.")

    package_tree.setdefault("name", package_name)
    return package_tree


def _write_outputs(
    package_tree: dict,
    package_name: str,
    safe_name: str,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    """Сохраняет JSON, Mermaid и SVG-файлы визуализации.

    Args:
        package_tree: Поддерево целевого пакета.
        package_name: Имя пакета (используется при построении Mermaid).
        safe_name: Безопасное имя пакета для имени файла.
        output_dir: Каталог, в который сохраняются файлы.

    Returns:
        Кортеж путей (json_path, mmd_path, svg_path).
    """
    json_path = output_dir / f"{safe_name}-npm.json"
    mmd_path = output_dir / f"{safe_name}-npm.mmd"
    svg_path = output_dir / f"{safe_name}-npm.svg"

    json_path.write_text(
        json.dumps(package_tree, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    mermaid_text = npm_tree_to_mermaid(package_name, package_tree)
    mmd_path.write_text(mermaid_text, encoding="utf-8")

    diagram = mermaidx.render(mermaid_text)
    diagram.save(str(svg_path.resolve()))

    return json_path, mmd_path, svg_path


def create_npm_visualization(package_name: str) -> None:
    """Получает дерево npm и сохраняет его визуализацию в текущем каталоге.

    Последовательность действий:
        1. Создаёт временный каталог.
        2. Инициализирует временный npm-проект.
        3. Устанавливает анализируемый пакет.
        4. Получает дерево зависимостей через npm ls.
        5. Сохраняет дерево в JSON.
        6. Преобразует дерево в описание Mermaid.
        7. Создаёт и сохраняет SVG-изображение.

    Args:
        package_name: Имя npm-пакета, например "axios" или "webpack".

    Raises:
        RuntimeError: Если npm завершился с ошибкой или пакет отсутствует
            в полученном дереве.
        OSError: Если невозможно запустить npm или записать файлы.
        ValueError: Если вывод npm содержит некорректный JSON.
        KeyError: Если при обработке данных отсутствует обязательный ключ.
        Exception: Библиотека mermaidx может выбросить собственную ошибку
            при формировании или сохранении SVG.
    """
    output_dir = Path.cwd()
    safe_name = package_name.replace("/", "-").replace("@", "")

    with tempfile.TemporaryDirectory(prefix="npm-graph-") as temp:
        temp_dir = Path(temp)
        tree = _install_and_get_tree(package_name, temp_dir)
        package_tree = _extract_package_tree(tree, package_name)
        json_path, mmd_path, svg_path = _write_outputs(
            package_tree, package_name, safe_name, output_dir
        )

        print(f"Дерево npm: {json_path}")
        print(f"Mermaid:    {mmd_path}")
        print(f"SVG:        {svg_path}")


def main() -> None:
    """Точка входа для запуска модуля из командной строки.

    Аргумент --package обязателен и задаёт пакет npm для анализа.
    При возникновении ожидаемой ошибки выводится сообщение,
    а программа завершается с кодом 1.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Получение дерева зависимостей npm и создание "
            "Mermaid/SVG-визуализации."
        ),
        epilog=("Пример: python -m src.npm_visualization --package axios"),
    )

    parser.add_argument(
        "--package",
        required=True,
        help="Имя пакета npm, например axios или webpack.",
    )

    args = parser.parse_args()

    try:
        create_npm_visualization(args.package)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Ошибка: {exc}\n")


if __name__ == "__main__":
    main()
