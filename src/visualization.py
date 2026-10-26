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
    # Первая строка задаёт тип диаграммы и направление сверху вниз.
    lines = ["flowchart TD"]

    # Собираем все пакеты: ключи графа и все найденные зависимости.
    # Это позволяет показать также пакеты без собственных зависимостей.
    packages = sorted(
        set(graph)
        | {
            dependency
            for dependencies in graph.values()
            for dependency in dependencies
        }
    )

    # Назначаем каждому пакету уникальный идентификатор Mermaid.
    # Индекс зависит от отсортированного списка пакетов.
    node_ids = {
        package: f"node_{index}" for index, package in enumerate(packages)
    }

    # Объявляем узлы и используем имя пакета как видимую подпись.
    for package in packages:
        # Экранируем специальные символы, чтобы они не нарушали
        # структуру Mermaid-описания.
        label = package.replace("&", "&amp;").replace('"', "#quot;")

        lines.append(f'    {node_ids[package]}["{label}"]')

    # Добавляем связи от пакета к каждой его зависимости.
    # Сортировка обеспечивает стабильный порядок рёбер в файле.
    for parent, dependencies in sorted(graph.items()):
        for dependency in sorted(dependencies):
            lines.append(f"    {node_ids[parent]} --> {node_ids[dependency]}")

    # Возвращаем готовый текст диаграммы с завершающим переводом строки.
    return "\n".join(lines) + "\n"


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
    # Создаём объект пути и раскрываем обозначение домашнего каталога.
    svg_path = Path(output_path).expanduser()

    # Проверяем расширение до начала сохранения.
    if svg_path.suffix.lower() != ".svg":
        raise VisualizationError("Выходной файл должен иметь расширение .svg.")

    try:
        # Создаём родительские каталоги, если их ещё нет.
        svg_path.parent.mkdir(parents=True, exist_ok=True)

        # Преобразуем граф в Mermaid и сохраняем текстовое представление.
        mermaid_text = generate_mermaid(graph)
        mermaid_path = svg_path.with_suffix(".mmd")

        mermaid_path.write_text(
            mermaid_text,
            encoding="utf-8",
        )

        # Преобразуем Mermaid-описание в объект SVG средствами mermaidx.
        svg = mermaidx.render(mermaid_text)

        # Сохраняем SVG по абсолютному пути.
        svg.save(str(svg_path.resolve()))

        # Дополнительно проверяем наличие выходного файла.
        if not svg_path.is_file():
            raise VisualizationError("SVG-файл не был создан.")

        print(f"Mermaid-описание сохранено: {mermaid_path}")
        print(f"Изображение графа сохранено: {svg_path}")

        return svg_path

    except VisualizationError:
        # Не оборачиваем повторно уже сформированную ошибку визуализации.
        raise

    except Exception as exc:
        # Преобразуем ошибку библиотеки или файловой системы в
        # исключение модуля, сохраняя исходную причину.
        raise VisualizationError(
            f"Не удалось создать визуализацию: {exc}"
        ) from exc
