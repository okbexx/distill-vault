import tempfile
from pathlib import Path

from distill.graph_index import GraphIndex


def _make_vault(tmp_path: Path):
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "决策").mkdir(parents=True)
    (tmp_path / "知识" / "项目").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


class TestGraphIndex:
    def test_graph_build_indexes_project_key_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "输出" / "report.md",
                "---\ntype: output\ntitle: Report\nstatus: published\n---\n",
            )
            _write_md(
                vault / "知识" / "项目" / "demo.md",
                "---\ntype: project\ntitle: Demo\nstatus: active\nkey_outputs:\n  - \"[[输出/report]]\"\n---\n",
            )

            graph = GraphIndex(vault)
            graph.build()
            edge_rows = graph.query("MATCH (a:Object)-[r:Links]->(b:Object) RETURN a.path, r.link_type, b.path")

            assert ["知识/项目/demo.md", "has_key_output", "输出/report.md"] in edge_rows

    def test_graph_build_uses_shared_frontmatter_edge_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n")
            _write_md(vault / "知识" / "决策" / "ship-it.md", "---\ntype: decision\ntitle: Ship It\nstatus: active\n---\n")
            _write_md(
                vault / "输出" / "report.md",
                "---\ntype: output\ntitle: Report\nstatus: published\nconcepts:\n  - \"[[Foo|核心概念]]\"\ndecisions:\n  - \"[[Ship It]]\"\n---\n[[Foo]]",
            )

            graph = GraphIndex(vault)
            stats = graph.build()

            assert stats["nodes"] == 3
            assert stats["edges"] == 4

            edge_rows = graph.query("MATCH (a:Object)-[r:Links]->(b:Object) RETURN a.path, r.link_type, b.path")
            assert ["输出/report.md", "has_concept", "知识/概念/foo.md"] in edge_rows
            assert ["输出/report.md", "has_decision", "知识/决策/ship-it.md"] in edge_rows
            assert ["输出/report.md", "wikilink", "知识/概念/foo.md"] in edge_rows
