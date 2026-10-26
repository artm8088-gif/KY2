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

    # Ненулевой код завершения означает, что команда сообщила об ошибке.
    if result.returncode != 0:
        raise RuntimeError(
            f"Команда завершилась с ошибкой:\n"
            f"{' '.join(command)}\n"
            f"{result.stderr}"
        )

    return result


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
    counter = 0

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
        nonlocal counter

        # Если сведения отсутствуют, используются значения по умолчанию.
        name = package.get("name", "unknown")
        version = package.get("version", "unknown")

        # Уникальный идентификатор нужен даже при повторении имени пакета.
        node_id = f"n{counter}"
        counter += 1

        # Формируем читаемую подпись узла.
        label = f"{name}@{version}"
        label = (
            label.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        lines.append(f'    {node_id}["{label}"]')

        # Соединяем текущий пакет с родительским узлом.
        if parent_id is not None:
            lines.append(f"    {parent_id} --> {node_id}")

        # Обрабатываем зависимости в алфавитном порядке,
        # чтобы результат был более предсказуемым.
        dependencies = package.get("dependencies", {})

        for dep_name, dependency in sorted(dependencies.items()):
            # Имя зависимости обычно уже присутствует в JSON npm.
            # setdefault заполняет его только при отсутствии значения.
            dependency.setdefault("name", dep_name)
            add_node(dependency, node_id)

    # Начинаем построение диаграммы с выбранного пакета.
    add_node(tree)

    # Завершающий перевод строки упрощает чтение файла .mmd.
    return "\n".join(lines) + "\n"


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
    # Файлы создаются в каталоге, из которого запущена программа.
    output_dir = Path.cwd()

    # Преобразуем имя пакета в более удобный фрагмент имени файла.
    # Например, @scope/package превращается в scope-package.
    safe_name = package_name.replace("/", "-").replace("@", "")

    # Временный каталог автоматически удаляется после выхода из блока.
    with tempfile.TemporaryDirectory(prefix="npm-graph-") as temp:
        temp_dir = Path(temp)

        # Создаём минимальный package.json для отдельного npm-проекта.
        run_command(["npm", "init", "-y"], temp_dir)

        # Устанавливаем пакет вместе с его зависимостями.
        # --ignore-scripts запрещает выполнение lifecycle-скриптов.
        # --no-audit отключает аудит безопасности при установке.
        # --no-fund отключает сообщения о финансировании пакетов.
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

        # Получаем полное установленное дерево в формате JSON.
        result = run_command(
            ["npm", "ls", "--all", "--json"],
            temp_dir,
        )
        tree = json.loads(result.stdout)

        # Из корневого проекта извлекаем установленный целевой пакет.
        root_dependencies = tree.get("dependencies", {})
        package_tree = root_dependencies.get(package_name)

        if package_tree is None:
            raise RuntimeError(
                f"Пакет {package_name} не найден в выводе npm ls."
            )

        # Некоторые версии npm могут не включать имя в ожидаемом месте.
        package_tree.setdefault("name", package_name)

        # Формируем пути к трём файлам результата.
        json_path = output_dir / f"{safe_name}-npm.json"
        mmd_path = output_dir / f"{safe_name}-npm.mmd"
        svg_path = output_dir / f"{safe_name}-npm.svg"

        # Сохраняем исходные данные npm с отступами для удобного чтения.
        json_path.write_text(
            json.dumps(
                package_tree,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Преобразуем дерево в Mermaid и сохраняем текст диаграммы.
        mermaid_text = npm_tree_to_mermaid(
            package_name,
            package_tree,
        )
        mmd_path.write_text(
            mermaid_text,
            encoding="utf-8",
        )

        # Создаём SVG на основе Mermaid-описания.
        diagram = mermaidx.render(mermaid_text)
        diagram.save(str(svg_path.resolve()))

        # Выводим расположение сформированных файлов.
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
        epilog=("Пример: python -m src.npm_visualization " "--package axios"),
    )

    parser.add_argument(
        "--package",
        required=True,
        help="Имя пакета npm, например axios или webpack.",
    )

    args = parser.parse_args()

    try:
        create_npm_visualization(args.package)
    except (
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        parser.exit(1, f"Ошибка: {exc}\n")


if __name__ == "__main__":
    main()
