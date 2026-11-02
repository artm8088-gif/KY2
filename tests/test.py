"""Общие тесты проекта dependency-visualizer."""

import json

import pytest
from src.cli import parse_args
from src.errors import ValidationError
from src.graph import (
    build_dependency_graph,
    get_load_order,
    read_test_repository,
)
from src.visualization import (
    VisualizationError,
    generate_mermaid,
    save_graph,
)


def write_repo(tmp_path, data):
    """Записывает тестовый репозиторий в JSON-файл и возвращает его путь.

    Args:
        tmp_path: Каталог pytest для временных файлов.
        data: Python-объект, который нужно сериализовать в JSON.

    Returns:
        Строковый путь к созданному файлу repo.json.
    """
    path = tmp_path / "repo.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_cli_default_options():
    """Проверяет значения по умолчанию для опций CLI."""
    config = parse_args(
        [
            "--package",
            "axios",
            "--repo",
            "https://registry.npmjs.org",
        ]
    )

    assert config.package_name == "axios"
    assert config.repo == "https://registry.npmjs.org"
    assert config.test_mode is False
    assert config.output_file == "graph.svg"
    assert config.ascii_tree is False
    assert config.load_order is False
    assert config.compare_npm is False


def test_cli_all_options(tmp_path):
    """Проверяет разбор CLI при передаче всех опций одновременно."""
    repo = write_repo(tmp_path, {"A": {"dependencies": {}}})

    config = parse_args(
        [
            "--package",
            "A",
            "--repo",
            repo,
            "--test-mode",
            "--output",
            "result.svg",
            "--ascii-tree",
            "--load-order",
            "--compare-npm",
        ]
    )

    assert config.package_name == "A"
    assert config.test_mode is True
    assert config.output_file == "result.svg"
    assert config.ascii_tree is True
    assert config.load_order is True
    assert config.compare_npm is True


@pytest.mark.parametrize("package", ["", "   ", " axios"])
def test_invalid_package(package):
    """Проверяет, что некорректное имя пакета отклоняется."""
    with pytest.raises(ValidationError):
        parse_args(
            [
                "--package",
                package,
                "--repo",
                "https://registry.npmjs.org",
            ]
        )


@pytest.mark.parametrize(
    "repo",
    ["", "   ", "ftp://example.com", "not-a-url"],
)
def test_invalid_repo_url(repo):
    """Проверяет, что некорректный URL репозитория отклоняется."""
    with pytest.raises(ValidationError):
        parse_args(["--package", "axios", "--repo", repo])


def test_missing_test_repo(tmp_path):
    """Проверяет ошибку при отсутствующем файле тестового репозитория."""
    with pytest.raises(ValidationError, match="не найден"):
        parse_args(
            [
                "--package",
                "A",
                "--repo",
                str(tmp_path / "missing.json"),
                "--test-mode",
            ]
        )


def test_repo_directory_is_invalid(tmp_path):
    """Проверяет ошибку, когда вместо файла репозитория передана директория."""
    with pytest.raises(ValidationError, match="не является файлом"):
        parse_args(
            [
                "--package",
                "A",
                "--repo",
                str(tmp_path),
                "--test-mode",
            ]
        )


@pytest.mark.parametrize("output", ["", "   "])
def test_invalid_output(output):
    """Проверяет, что пустой путь к выходному файлу отклоняется."""
    with pytest.raises(ValidationError):
        parse_args(
            [
                "--package",
                "axios",
                "--repo",
                "https://registry.npmjs.org",
                "--output",
                output,
            ]
        )


def test_output_directory_is_invalid(tmp_path):
    """Проверяет ошибку, когда вместо файла вывода передана директория."""
    with pytest.raises(ValidationError, match="директорию"):
        parse_args(
            [
                "--package",
                "axios",
                "--repo",
                "https://registry.npmjs.org",
                "--output",
                str(tmp_path),
            ]
        )


def test_read_valid_repo(tmp_path):
    """Проверяет успешное чтение корректного тестового репозитория."""
    repo = write_repo(
        tmp_path,
        {
            "A": {"dependencies": {"B": "1.0"}},
            "B": {"dependencies": {}},
        },
    )

    data = read_test_repository(repo)

    assert "A" in data
    assert data["A"]["dependencies"] == {"B": "1.0"}


@pytest.mark.parametrize(
    "data",
    [
        ["not", "an", "object"],
        {"a": {"dependencies": {}}},
        {"A": {"dependencies": []}},
        {"A": {"dependencies": {"B": []}}},
    ],
)
def test_invalid_repo_structure(tmp_path, data):
    """Проверяет, что некорректная структура репозитория отклоняется."""
    repo = write_repo(tmp_path, data)

    with pytest.raises(ValidationError):
        read_test_repository(repo)


def test_invalid_json(tmp_path):
    """Проверяет, что файл с некорректным JSON отклоняется."""
    path = tmp_path / "broken.json"
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValidationError, match="JSON"):
        read_test_repository(str(path))


def test_build_graph_bfs(tmp_path):
    """Проверяет построение полного транзитивного графа через BFS."""
    repo = write_repo(
        tmp_path,
        {
            "A": {"dependencies": {"B": "1.0", "C": "1.0"}},
            "B": {"dependencies": {"D": "1.0"}},
            "C": {"dependencies": {"D": "1.0"}},
            "D": {"dependencies": {}},
        },
    )

    graph = build_dependency_graph("A", repo, test_mode=True)

    assert set(graph) == {"A", "B", "C", "D"}
    assert graph["A"] == {"B": "1.0", "C": "1.0"}
    assert graph["B"] == {"D": "1.0"}
    assert graph["C"] == {"D": "1.0"}
    assert graph["D"] == {}


def test_build_graph_cycle(tmp_path):
    """Проверяет, что BFS корректно обходит циклические зависимости."""
    repo = write_repo(
        tmp_path,
        {
            "A": {"dependencies": {"B": "1"}},
            "B": {"dependencies": {"C": "1"}},
            "C": {"dependencies": {"A": "1"}},
        },
    )

    graph = build_dependency_graph("A", repo, test_mode=True)

    assert set(graph) == {"A", "B", "C"}
    assert graph["C"] == {"A": "1"}


def test_build_graph_missing_package(tmp_path):
    """Проверяет ошибку, если пакет отсутствует в тестовом репозитории."""
    repo = write_repo(
        tmp_path,
        {
            "A": {"dependencies": {"B": "1"}},
        },
    )

    with pytest.raises(ValidationError, match="отсутствует"):
        build_dependency_graph("A", repo, test_mode=True)


def test_load_order_dependencies_first():
    """Проверяет, что зависимости идут в порядке загрузки раньше зависимых."""
    graph = {
        "A": {"B": "1", "C": "1"},
        "B": {"D": "1"},
        "C": {},
        "D": {},
    }

    order = get_load_order(graph)
    positions = {name: index for index, name in enumerate(order)}

    assert set(order) == set(graph)
    assert positions["B"] < positions["A"]
    assert positions["C"] < positions["A"]
    assert positions["D"] < positions["B"]


def test_load_order_cycle():
    """Проверяет, что циклический граф приводит к ValidationError."""
    graph = {
        "A": {"B": "1"},
        "B": {"A": "1"},
    }

    with pytest.raises(ValidationError, match="циклические"):
        get_load_order(graph)


def test_generate_mermaid_nodes_and_edges():
    """Проверяет наличие узлов и связей в сгенерированном Mermaid-описании."""
    graph = {
        "A": ["B"],
        "B": ["C"],
        "C": [],
    }

    result = generate_mermaid(graph)

    assert result.startswith("flowchart TD")
    assert '["A"]' in result
    assert '["B"]' in result
    assert '["C"]' in result
    assert "-->" in result


def test_mermaid_is_deterministic():
    """Проверяет, что Mermaid-описание не зависит от порядка ключей графа."""
    graph1 = {"B": ["C"], "A": ["B"]}
    graph2 = {"A": ["B"], "B": ["C"]}

    assert generate_mermaid(graph1) == generate_mermaid(graph2)


def test_save_graph(tmp_path, monkeypatch):
    """Проверяет сохранение .mmd и .svg без реального вызова mermaidx."""
    from src import visualization

    class FakeDiagram:
        def save(self, path):
            """Пишет заглушку SVG в указанный файл."""
            with open(path, "w", encoding="utf-8") as file:
                file.write("<svg></svg>")

    monkeypatch.setattr(
        visualization.mermaidx,
        "render",
        lambda text: FakeDiagram(),
    )

    output = tmp_path / "graph.svg"
    result = save_graph({"A": ["B"], "B": []}, str(output))

    assert result == output
    assert output.is_file()
    assert output.with_suffix(".mmd").is_file()


def test_save_graph_wrong_extension(tmp_path):
    """Проверяет ошибку при неподходящем расширении выходного файла."""
    with pytest.raises(VisualizationError, match="расширение"):
        save_graph({"A": []}, str(tmp_path / "graph.png"))
