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

# ---------- Вспомогательная функция ----------


def write_repo(tmp_path, data):
    path = tmp_path / "repo.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ---------- CLI и валидация ----------


def test_cli_default_options():
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
    with pytest.raises(ValidationError):
        parse_args(["--package", "axios", "--repo", repo])


def test_missing_test_repo(tmp_path):
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


# ---------- Чтение тестового репозитория ----------


def test_read_valid_repo(tmp_path):
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
    repo = write_repo(tmp_path, data)

    with pytest.raises(ValidationError):
        read_test_repository(repo)


def test_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValidationError, match="JSON"):
        read_test_repository(str(path))


# ---------- Построение графа BFS ----------


def test_build_graph_bfs(tmp_path):
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
    repo = write_repo(
        tmp_path,
        {
            "A": {"dependencies": {"B": "1"}},
        },
    )

    with pytest.raises(ValidationError, match="отсутствует"):
        build_dependency_graph("A", repo, test_mode=True)


# ---------- Порядок загрузки ----------


def test_load_order_dependencies_first():
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
    graph = {
        "A": {"B": "1"},
        "B": {"A": "1"},
    }

    with pytest.raises(ValidationError, match="циклические"):
        get_load_order(graph)


# ---------- Mermaid и SVG ----------


def test_generate_mermaid_nodes_and_edges():
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
    graph1 = {"B": ["C"], "A": ["B"]}
    graph2 = {"A": ["B"], "B": ["C"]}

    assert generate_mermaid(graph1) == generate_mermaid(graph2)


def test_save_graph(tmp_path, monkeypatch):
    from src import visualization

    class FakeDiagram:
        def save(self, path):
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
    with pytest.raises(VisualizationError, match="расширение"):
        save_graph({"A": []}, str(tmp_path / "graph.png"))
