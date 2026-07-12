import json
import tempfile
from pathlib import Path

from distill.health import HealthChecker
from distill.phases import build_pipeline
from distill.pipeline import PipelineDAG
from distill.worker_pool import WorkerPool


def _make_vault(tmp_path: Path):
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def _vault_markdown_files(vault: Path) -> list[str]:
    return sorted(
        p.relative_to(vault).as_posix()
        for p in vault.rglob("*.md")
        if ".distill" not in p.relative_to(vault).parts
    )


def _snapshot_outputs(vault: Path) -> dict[str, str]:
    return {
        "checkpoint": (vault / ".distill" / "checkpoint.json").read_text(encoding="utf-8"),
        "index": (vault / "运维" / "索引" / "auto-index.json").read_text(encoding="utf-8"),
        "health": (vault / "运维" / "健康检查" / "health-report.md").read_text(encoding="utf-8"),
    }


class TestPipeline:
    def test_full_pipeline_runs(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconcepts: [Foo]\n---\n")

            dag = build_pipeline(vault)
            results = dag.run()

            assert "scan" in results
            assert "parse" in results
            assert "graph" in results
            assert "analyze" in results
            assert "promote" in results
            assert "export" in results

            # Check graph stats
            stats = dag.ctx.get("graph_stats", {})
            assert stats["nodes"] == 3
            assert stats["edges"] >= 2  # Bar->Foo wikilink + Report->Foo concept

            # Check export files created
            assert (vault / "运维" / "索引" / "auto-index.json").exists()
            assert (vault / "运维" / "健康检查" / "health-report.md").exists()

    def test_pipeline_honors_instance_export_paths(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_md(
            vault / "知识" / "概念" / "foo.md",
            "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo",
        )
        config = {
            "vault": {
                "knowledge_dirs": ["知识"],
                "output_dirs": ["输出"],
                "ops_dirs": ["运维"],
                "system_dirs": [],
            },
            "exports": {
                "index_path": "运维/投影/index.json",
                "health_path": "运维/健康检查/健康报告.md",
            },
        }

        dag = build_pipeline(vault, config=config)
        dag.run()

        assert (vault / "运维" / "投影" / "index.json").exists()
        assert (vault / "运维" / "健康检查" / "健康报告.md").exists()
        assert not (vault / "运维" / "健康检查" / "health-report.md").exists()

    def test_pipeline_keeps_alias_and_frontmatter_relations_consistent(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n")
            _write_md(vault / "知识" / "概念" / "latency-budget.md", "---\ntype: concept\ntitle: Latency Budget\nstatus: active\n---\n")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconcepts:\n  - \"[[Foo|核心概念]]\"\nconstraints:\n  - \"[[Latency Budget]]\"\n---\n[[Foo|显示名]]")

            dag = build_pipeline(vault)
            dag.run()

            assert dag.ctx.get("wikilinks", {})["输出/report.md"] == ["Foo", "Foo", "Latency Budget"]
            # Duplicate body/frontmatter references collapse to one typed edge set.
            assert dag.ctx.get("graph_stats", {})["edges"] == 4
            health_report = (vault / "运维" / "健康检查" / "health-report.md").read_text(encoding="utf-8")
            assert "- Total objects: 3" in health_report
            assert "- Broken links: 0" in health_report

    def test_pipeline_detects_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "lonely.md", "---\ntype: concept\ntitle: Lonely\nstatus: draft\n---\n")

            dag = build_pipeline(vault)
            dag.run()

            orphans = dag.ctx.get("orphans", [])
            assert len(orphans) == 1
            assert orphans[0][0] == "知识/概念/lonely.md"
            buckets = dag.ctx.get("orphan_buckets", {})
            assert len(buckets.get("true_orphan", [])) == 1
            assert not buckets.get("system_doc", [])

    def test_pipeline_type_distribution(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "c1.md", "---\ntype: concept\ntitle: C1\nstatus: active\n---\n")
            _write_md(vault / "知识" / "概念" / "c2.md", "---\ntype: concept\ntitle: C2\nstatus: active\n---\n")
            _write_md(vault / "知识" / "来源" / "s1.md", "---\ntype: source\ntitle: S1\nstatus: linked\n---\n")

            dag = build_pipeline(vault)
            dag.run()

            type_dist = dag.ctx.get("type_distribution", [])
            types = {row[0]: row[1] for row in type_dist}
            assert types.get("concept") == 2
            assert types.get("source") == 1

    def test_empty_vault_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            dag = build_pipeline(vault)
            results = dag.run()
            assert dag.ctx.get("object_count") == 0
            assert dag.ctx.get("graph_stats", {}).get("nodes") == 0

    def test_pipeline_repeated_runs_produce_stable_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconcepts: [Foo]\n---\n")

            dag = build_pipeline(vault)
            dag.run()
            first = _snapshot_outputs(vault)
            expected_user_md_files = [path for path in _vault_markdown_files(vault) if not path.startswith("运维/")]

            dag = build_pipeline(vault)
            dag.run()
            second = _snapshot_outputs(vault)

            assert [path for path in _vault_markdown_files(vault) if not path.startswith("运维/")] == expected_user_md_files
            assert second == first

    def test_pipeline_run_writes_runtime_metadata_and_reports_clean_staleness(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")

            dag = build_pipeline(vault)
            dag.run()

            runtime_state = (vault / ".distill" / "runtime-state.json").read_text(encoding="utf-8")
            staleness = dag.check_staleness()

            assert '"timestamp"' in runtime_state
            assert staleness["stale"] is False
            assert staleness["total_changes"] == 0
            assert staleness["last_index_time"] > 0

    def test_staleness_without_checkpoint_returns_consistent_zero_counts(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))

            dag = build_pipeline(vault)
            staleness = dag.check_staleness()

            assert staleness == {
                "stale": True,
                "reason": "no_checkpoint",
                "added": 0,
                "removed": 0,
                "modified": 0,
                "total_changes": 0,
                "last_index_time": 0,
            }

    def test_pipeline_run_cleans_temporary_graph_csv_exports(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")

            dag = build_pipeline(vault)
            dag.run()

            assert not (vault / ".distill" / "nodes.csv").exists()
            assert not (vault / ".distill" / "edges.csv").exists()

    def test_staleness_reports_added_removed_and_modified_files(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")

            dag = build_pipeline(vault)
            dag.run()

            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo updated")
            (vault / "知识" / "来源" / "bar.md").unlink()
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: draft\n---\n")

            staleness = build_pipeline(vault).check_staleness()

            assert staleness["stale"] is True
            assert staleness["added"] == 1
            assert staleness["removed"] == 1
            assert staleness["modified"] == 1
            assert staleness["total_changes"] == 3

    def test_incremental_run_skips_unchanged_downstream_phases(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            parse_calls = {"count": 0}
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")

            def make_dag():
                dag = PipelineDAG(vault)

                @dag.register("scan")
                def scan(ctx):
                    from distill.pipeline import compute_file_hashes

                    ctx.set("file_hashes", compute_file_hashes(vault, config=ctx.config))
                    dag.phases["scan"].objects_processed = 1

                @dag.register("parse", deps=["scan"])
                def parse(ctx):
                    parse_calls["count"] += 1
                    dag.phases["parse"].objects_processed = 1

                return dag

            make_dag().run()
            second = make_dag()
            results = second.run(incremental=True)

            assert parse_calls["count"] == 1
            assert results["parse"] == {"objects": 1, "errors": []}

    def test_incremental_report_marks_cached_phases_as_complete(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")

            def make_dag():
                dag = PipelineDAG(vault)

                @dag.register("scan")
                def scan(ctx):
                    from distill.pipeline import compute_file_hashes

                    ctx.set("file_hashes", compute_file_hashes(vault, config=ctx.config))
                    dag.phases["scan"].objects_processed = 1

                @dag.register("parse", deps=["scan"])
                def parse(ctx):
                    dag.phases["parse"].objects_processed = 1

                return dag

            make_dag().run()
            second = make_dag()
            second.run(incremental=True)
            report = second.report()

            assert "○ parse" not in report
            assert "↺ parse" in report
            assert "cached" in report

    def test_checkpoint_persists_all_six_phases_including_export(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconcepts: [Foo]\n---\n")

            dag = build_pipeline(vault)
            dag.run()

            checkpoint = dag._load_checkpoint()

            assert list(checkpoint["phases"].keys()) == [
                "analyze",
                "export",
                "graph",
                "parse",
                "promote",
                "scan",
            ]
            assert checkpoint["phases"]["export"]["objects"] == 2

    def test_checkpoint_persists_worker_pool_summary(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")

            dag = build_pipeline(vault, worker_pool=WorkerPool(mode="serial", workers=1))
            dag.run()

            checkpoint = dag._load_checkpoint()

            assert checkpoint["worker_pool"]["requested_mode"] == "serial"
            assert checkpoint["worker_pool"]["fallback_used"] is False
            assert checkpoint["worker_pool"]["fallback_reason"] is None
            assert checkpoint["worker_pool"]["last_mode"] == "serial"
            assert checkpoint["worker_pool"]["phases"]["scan"]["last_mode"] == "serial"
            assert checkpoint["worker_pool"]["phases"]["parse"]["last_mode"] == "serial"

    def test_exported_health_report_matches_health_checker_contract(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconcepts: [Foo]\n---\n")

            dag = build_pipeline(vault)
            dag.run()

            checker = HealthChecker(vault)
            checker.scan()
            expected = checker.report()
            exported = (vault / "运维" / "健康检查" / "health-report.md").read_text(encoding="utf-8")

            assert exported == expected
            assert "- Runtime stage: trusted_runtime" in exported
            assert "## Vault Layout" in exported

    def test_exported_auto_index_matches_shared_index_contract(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nstatus: published\nconcepts: [Foo]\n---\n")

            dag = build_pipeline(vault)
            dag.run()

            exported = json.loads((vault / "运维" / "索引" / "auto-index.json").read_text(encoding="utf-8"))
            checker = HealthChecker(vault)
            checker.scan()
            expected = checker.index.auto_index_payload()

            assert exported == expected
            assert exported["runtime_stage"] == "trusted_runtime"
            assert exported["has_checkpoint"] is True
            assert "generated_at" not in exported
            assert "graph_edges" not in exported.get("stats", {})

    def test_report_from_snapshot_uses_pipeline_execution_order(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            dag = build_pipeline(vault)
            dag._topological_sort()

            report = dag.report_from_snapshot({
                "scan": {"objects": 1, "errors": []},
                "parse": {"objects": 1, "errors": []},
                "graph": {"objects": 1, "errors": []},
                "analyze": {"objects": 1, "errors": []},
                "promote": {"objects": 0, "errors": []},
                "export": {"objects": 2, "errors": []},
            })

            assert report.index("scan") < report.index("parse") < report.index("graph")
            assert report.index("graph") < report.index("analyze") < report.index("promote")
            assert report.index("promote") < report.index("export")
            assert "Total: checkpoint | 6 objects | 0 errors" in report
