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

    Сначала функция определяет полный набор пакетов, включая те,
    которые встречаются только в списках зависимостей и не имеют
    собственных записей в качестве ключей исходного словаря.
    Каждому пакету назначается уникальный идентификатор вида node_0,
    node_1 и так далее. Это позволяет отделить идентификатор узла
    от имени пакета.
    После объявления узлов создаются направленные связи от каждого
    родительского пакета к его зависимостям.

    Args:
        graph: Словарь, где ключи — имена пакетов, а значения —
            коллекции имён их непосредственных зависимостей.

    Returns:
        Строка с Mermaid-описанием диаграммы. Используется синтаксис
        flowchart TD, который располагает граф сверху вниз.

    Example:
        >>> generate_mermaid({"app": ["library"]})
        'flowchart TD\\n    node_0["app"]\\n...'

    Note:
        Пакеты и зависимости сортируются, чтобы результат был
        предсказуемым при одинаковом входном графе.
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


def save_graph(graph: dict, output_path: str) -> Path:
    """Сохраняет Mermaid-описание графа и SVG-изображение.

    Функция проверяет расширение выходного пути, создаёт родительские
    каталоги при необходимости, записывает Mermaid-описание в файл
    .mmd и преобразует его в SVG при помощи библиотеки mermaidx.

    Args:
        graph: Граф зависимостей в виде словаря.
        output_path: Путь к результирующему SVG-файлу. Если путь
            относительный, он интерпретируется относительно текущего
            рабочего каталога. Тильда в начале пути раскрывается.

    Returns:
        Объект pathlib.Path с путём к сохранённому SVG-файлу.

    Raises:
        VisualizationError: Если указано неподходящее расширение,
            не удалось создать визуализацию или SVG-файл не появился.
        OSError: Ошибки файловой системы оборачиваются в
            VisualizationError с сохранением исходного исключения.

    Side Effects:
        Создаёт каталог назначения при необходимости.
        Записывает файлы .mmd и .svg.
        Выводит пути к созданным файлам в консоль.
    """
    svg_path = _validate_output_path(output_path)

    try:
        svg_path.parent.mkdir(parents=True, exist_ok=True)

        mermaid_text = generate_mermaid(graph)
        mermaid_path = _write_mermaid_file(mermaid_text, svg_path)
        _render_and_save_svg(mermaid_text, svg_path)

        print(f"Mermaid-описание сохранено: {mermaid_path}")
        print(f"Изображение графа сохранено: {svg_path}")

        return svg_path

    except VisualizationError:
        raise

    except Exception as exc:
        raise VisualizationError(
            f"Не удалось создать визуализацию: {exc}"
        ) from exc
