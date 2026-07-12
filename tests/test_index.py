import json
from pathlib import Path
import tempfile

from distill.index import VaultIndex


def _make_vault(tmp_path: Path):
    """Create a minimal vault structure."""
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


class TestVaultIndex:
    def test_scan_empty_vault(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            idx = VaultIndex(vault)
            idx.scan()
            assert idx.stats["total_objects"] == 0

    def test_scan_finds_objects(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "test.md", "---\ntype: concept\ntitle: Test\n---\n# Test")
            _write_md(vault / "知识" / "来源" / "src.md", "---\ntype: source\ntitle: Source\n---\n[[Test]]")
            idx = VaultIndex(vault)
            idx.scan()
            assert idx.stats["total_objects"] == 2
            assert idx.stats["total_wikilinks"] == 1
            assert len(idx.broken_links) == 0

    def test_path_wikilink_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\n---\n")
            _write_md(vault / "知识" / "来源" / "bar.md", "---\ntype: source\ntitle: Bar\n---\n[[知识/概念/foo]]")
            idx = VaultIndex(vault)
            idx.scan()
            assert len(idx.broken_links) == 0

    def test_alias_and_frontmatter_relations_are_indexed_consistently(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\n---\n")
            _write_md(vault / "输出" / "report.md", "---\ntype: output\ntitle: Report\nconcepts:\n  - \"[[Foo|核心概念]]\"\nconstraints:\n  - \"[[Latency Budget]]\"\n---\n[[Foo|显示名]]")
            _write_md(vault / "知识" / "概念" / "latency-budget.md", "---\ntype: concept\ntitle: Latency Budget\n---\n")

            idx = VaultIndex(vault)
            idx.scan()

            assert len(idx.broken_links) == 0
            assert idx.wikilinks["输出/report.md"] == ["Foo", "Foo", "Latency Budget"]
            assert sorted(idx.backlinks["知识/概念/foo.md"]) == ["输出/report.md"]
            assert sorted(idx.backlinks["知识/概念/latency-budget.md"]) == ["输出/report.md"]

    def test_broken_link_detection(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "bad.md", "---\ntype: source\ntitle: Bad\n---\n[[NonExistent]]")
            idx = VaultIndex(vault)
            idx.scan()
            assert len(idx.broken_links) == 1

    def test_existing_obsidian_base_is_valid_but_missing_base_is_broken(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            (vault / "浏览").mkdir()
            (vault / "浏览" / "项目证据.base").write_text("views: []\n", encoding="utf-8")
            _write_md(
                vault / "知识" / "来源" / "views.md",
                "---\ntype: source\ntitle: Views\n---\n![[浏览/项目证据.base]]\n[[浏览/缺失.base]]",
            )

            idx = VaultIndex(vault)
            idx.scan()

            assert idx.broken_links == [{"from": "知识/来源/views.md", "to": "浏览/缺失.base"}]

    def test_orphan_detection(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "lonely.md", "---\ntype: concept\ntitle: Lonely\n---\n")
            idx = VaultIndex(vault)
            idx.scan()
            assert len(idx.orphans) == 1

    def test_system_skill_docs_are_classified_as_system_docs_instead_of_true_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            (vault / "系统" / "技能").mkdir(parents=True)
            _write_md(vault / "系统" / "技能" / "maintain-project.md", "# maintain project\n")

            idx = VaultIndex(vault)
            idx.scan()

            assert idx.orphan_buckets["system_doc"] == ["系统/技能/maintain-project.md"]
            assert idx.orphan_buckets["true_orphan"] == []

    def test_save_index(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "x.md", "---\ntype: concept\ntitle: X\n---\n")
            idx = VaultIndex(vault)
            idx.scan()
            path = idx.save()
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["stats"]["total_objects"] == 1

    def test_save_index_uses_shared_auto_index_contract(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "x.md", "---\ntype: concept\ntitle: X\nstatus: active\n---\n")
            _write_md(vault / "知识" / "来源" / "src.md", "---\ntype: source\ntitle: Source\nstatus: linked\n---\n[[X]]")
            idx = VaultIndex(vault)
            idx.scan()

            path = idx.save()
            data = json.loads(path.read_text())

            assert data == idx.auto_index_payload()
            assert data["runtime_stage"] == "preflight"
            assert data["has_checkpoint"] is False
            assert "scan_roots" in data
            assert "vault_layout" in data
            assert "next_steps" in data
            assert "generated_at" not in data

    def test_auto_index_payload_is_json_safe_when_frontmatter_contains_yaml_date(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "知识" / "来源" / "dated.md",
                "---\ntype: source\ntitle: Dated\nstatus: linked\ndate: 2026-05-13\n---\n[[Missing?]]",
            )
            idx = VaultIndex(vault)
            idx.scan()

            payload = idx.auto_index_payload()
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            decoded = json.loads(encoded)

            assert decoded["objects"][0]["frontmatter"]["date"] == "2026-05-13"

    def test_report_includes_recommended_next_steps_for_clean_vault(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            (vault / ".distill").mkdir(parents=True)
            _write_md(vault / ".distill" / "checkpoint.json", "{}")
            _write_md(vault / "知识" / "概念" / "test.md", "---\ntype: concept\ntitle: Test\nstatus: active\n---\n# Test")
            _write_md(vault / "知识" / "来源" / "src.md", "---\ntype: source\ntitle: Source\nstatus: linked\n---\n[[Test]]")
            idx = VaultIndex(vault)
            idx.scan()
            report = idx.report()
            assert "[Recommended Next Steps]" in report
            assert "Refresh runtime artifacts while the vault is clean" in report
            assert "Verify with: `distill run`" in report

    def test_report_guides_first_run_for_existing_vault_without_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "test.md", "---\ntype: concept\ntitle: Test\nstatus: active\n---\n# Test")
            _write_md(vault / "知识" / "来源" / "src.md", "---\ntype: source\ntitle: Source\nstatus: linked\n---\n[[Test]]")
            idx = VaultIndex(vault)
            idx.scan()
            report = idx.report()
            assert "Complete the first distill run for this existing vault" in report
            assert "No pipeline checkpoint exists yet" in report
            assert "Verify with: `distill run`" in report
