"""Визуализация графа зависимостей в форматах Mermaid и SVG.

Модуль преобразует граф зависимостей пакетов в текстовое описание
диаграммы Mermaid и сохраняет его вместе с SVG-изображением.

Входной граф представлен словарём:
    ключ — имя родительского пакета;
    значение — коллекция имён пакетов, от которых он зависит.

Например:
    {
        "axios": ["follow-redirects", "form-data"],
        "form-data": ["asynckit"]
    }

В результате создаются два файла:
    graph.mmd — текстовое описание графа на языке Mermaid;
    graph.svg — графическое изображение этого графа.

Для создания SVG используется библиотека mermaidx.

Пример использования:
    from src.visualization import save_graph

    graph = {
        "axios": ["follow-redirects", "form-data"],
        "form-data": ["asynckit"],
    }

    save_graph(graph, "axios.svg")
"""

from pathlib import Path

import mermaidx


class VisualizationError(Exception):
    """Исключение, возникающее при создании визуализации.

    Используется для передачи вызывающему коду понятного сообщения
    об ошибках сохранения Mermaid-описания или SVG-изображения.
    """


def _collect_packages(graph: dict) -> list[str]:
    """Возвращает отсортированный список всех пакетов графа.

    Включает как ключи словаря, так и пакеты, встречающиеся только
    в списках зависимостей, чтобы показать и пакеты без собственных
    зависимостей.

    Args:
        graph: Словарь зависимостей.

    Returns:
        Отсортированный список уникальных имён пакетов.
    """
    return sorted(
        set(graph)
        | {
            dependency
            for dependencies in graph.values()
            for dependency in dependencies
        }
    )


def _build_node_ids(packages: list[str]) -> dict[str, str]:
    """Сопоставляет каждому пакету уникальный идентификатор Mermaid.

    Args:
        packages: Отсортированный список имён пакетов.

    Returns:
        Словарь вида {имя пакета: node_N}.
    """
    return {package: f"node_{index}" for index, package in enumerate(packages)}


def _escape_package_label(package: str) -> str:
    """Экранирует специальные символы в подписи узла Mermaid."""
    return package.replace("&", "&amp;").replace('"', "#quot;")


def generate_mermaid(graph: dict) -> str:
    r"""Преобразует граф зависимостей в текстовое описание Mermaid.

    Определяет полный набор пакетов (включая встречающиеся только
    в списках зависимостей), назначает каждому уникальный
    идентификатор node_N, объявляет узлы и создаёт направленные связи
    от родительских пакетов к их зависимостям.

    Args:
        graph: Словарь {пакет: коллекция имён зависимостей}.

    Returns:
        Строка с Mermaid-описанием диаграммы (flowchart TD).

    Example:
        >>> generate_mermaid({"app": ["library"]})
        'flowchart TD\\n    node_0["app"]\\n...'

    Note:
        Пакеты и зависимости сортируются для предсказуемого результата.
    """
    lines = ["flowchart TD"]
    packages = _collect_packages(graph)
    node_ids = _build_node_ids(packages)

    for package in packages:
        label = _escape_package_label(package)
        lines.append(f'    {node_ids[package]}["{label}"]')

    for parent, dependencies in sorted(graph.items()):
        for dependency in sorted(dependencies):
            lines.append(f"    {node_ids[parent]} --> {node_ids[dependency]}")

    return "\n".join(lines) + "\n"


def _validate_output_path(output_path: str) -> Path:
    """Проверяет расширение выходного пути и возвращает объект Path.

    Args:
        output_path: Путь к результирующему SVG-файлу.

    Returns:
        Объект pathlib.Path с раскрытым домашним каталогом.

    Raises:
        VisualizationError: Если расширение файла не .svg.
    """
    svg_path = Path(output_path).expanduser()
    if svg_path.suffix.lower() != ".svg":
        raise VisualizationError("Выходной файл должен иметь расширение .svg.")
    return svg_path


def _write_mermaid_file(mermaid_text: str, svg_path: Path) -> Path:
    """Записывает Mermaid-описание рядом с целевым SVG-файлом.

    Args:
        mermaid_text: Текст Mermaid-диаграммы.
        svg_path: Путь к целевому SVG-файлу.

    Returns:
        Путь к созданному .mmd-файлу.
    """
    mermaid_path = svg_path.with_suffix(".mmd")
    mermaid_path.write_text(mermaid_text, encoding="utf-8")
    return mermaid_path


def _render_and_save_svg(mermaid_text: str, svg_path: Path) -> None:
    """Преобразует Mermaid-описание в SVG и сохраняет его на диск.

    Args:
        mermaid_text: Текст Mermaid-диаграммы.
        svg_path: Путь, по которому нужно сохранить SVG.

    Raises:
        VisualizationError: Если SVG-файл не появился после сохранения.
    """
    svg = mermaidx.render(mermaid_text)
    svg.save(str(svg_path.resolve()))

    if not svg_path.is_file():
        raise VisualizationError("SVG-файл не был создан.")


def _write_visualization(
    graph: dict,
    svg_path: Path,
) -> Path:
    """Создаёт каталог, пишет .mmd и .svg и возвращает путь к .mmd-файлу.

    Args:
        graph: Граф зависимостей.
        svg_path: Путь к целевому SVG-файлу.

    Returns:
        Путь к созданному .mmd-файлу.

    Raises:
        VisualizationError: Если визуализацию создать не удалось.
    """
    svg_path.parent.mkdir(parents=True, exist_ok=True)

    mermaid_text = generate_mermaid(graph)
    mermaid_path = _write_mermaid_file(mermaid_text, svg_path)
    _render_and_save_svg(mermaid_text, svg_path)
    return mermaid_path


def save_graph(graph: dict, output_path: str) -> Path:
    """Сохраняет Mermaid-описание графа и SVG-изображение.

    Проверяет расширение выходного пути, создаёт родительские каталоги
    при необходимости, записывает .mmd-файл и преобразует его в SVG
    при помощи библиотеки mermaidx.

    Args:
        graph: Граф зависимостей в виде словаря.
        output_path: Путь к результирующему SVG-файлу. Относительный
            путь интерпретируется от текущего каталога; тильда
            в начале пути раскрывается.

    Returns:
        Объект pathlib.Path с путём к сохранённому SVG-файлу.

    Raises:
        VisualizationError: При неподходящем расширении, ошибке
            создания визуализации или отсутствии SVG-файла.

    Side Effects:
        Создаёт каталог назначения, пишет .mmd и .svg,
        выводит пути к созданным файлам в консоль.
    """
    svg_path = _validate_output_path(output_path)

    try:
        mermaid_path = _write_visualization(graph, svg_path)
    except VisualizationError:
        raise
    except Exception as exc:
        raise VisualizationError(
            f"Не удалось создать визуализацию: {exc}"
        ) from exc

    print(f"Mermaid-описание сохранено: {mermaid_path}")
    print(f"Изображение графа сохранено: {svg_path}")
    return svg_path
