import tempfile
from pathlib import Path

from distill.graph_index import GraphIndex
from distill.phases import build_pipeline


def _make_vault(tmp_path: Path):
    (tmp_path / "knowledge" / "constraint").mkdir(parents=True)
    (tmp_path / "knowledge" / "analysis").mkdir(parents=True)
    (tmp_path / "output").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


class TestEnglishRelationPrefixes:
    def test_graph_resolves_plain_string_constraint_via_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "knowledge" / "constraint" / "latency-budget.md", "---\ntype: constraint\ntitle: Latency Budget\nstatus: active\n---\n")
            _write_md(vault / "output" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconstraints:\n  - Latency Budget\n---\n")

            graph = GraphIndex(vault)
            stats = graph.build()
            assert stats["edges"] == 2
            edge_rows = graph.query("MATCH (a:Object)-[r:Links]->(b:Object) RETURN a.path, r.link_type, b.path")
            assert ["output/report.md", "wikilink", "knowledge/constraint/latency-budget.md"] in edge_rows
            assert ["output/report.md", "has_constraint", "knowledge/constraint/latency-budget.md"] in edge_rows

    def test_pipeline_resolves_plain_string_constraint_via_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "knowledge" / "constraint" / "latency-budget.md", "---\ntype: constraint\ntitle: Latency Budget\nstatus: active\n---\n")
            _write_md(vault / "output" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconstraints:\n  - Latency Budget\n---\n")

            dag = build_pipeline(vault)
            dag.run()

            assert dag.ctx.get("wikilinks", {})["output/report.md"] == ["Latency Budget"]
            assert dag.ctx.get("graph_stats", {})["edges"] == 2
