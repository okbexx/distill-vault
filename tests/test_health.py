import json
import tempfile
from pathlib import Path

from distill.health import HealthChecker


def _make_vault(tmp_path: Path):
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestHealthChecker:
    def test_report_includes_recommended_next_steps_for_broken_links_and_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "lonely.md", "---\ntype: concept\ntitle: Lonely\nstatus: active\n---\n")
            _write_md(vault / "知识" / "来源" / "bad.md", "---\ntype: source\ntitle: Bad\nstatus: linked\n---\n[[Missing]]")
            checker = HealthChecker(vault)
            checker.scan()
            report = checker.report()
            assert "## Recommended Next Steps" in report
            assert "Resolve broken links before trusting graph-derived output" in report
            assert "Verify with: `distill lint`" in report
            assert "Add at least one incoming or outgoing link for `知识/概念/lonely.md`" in report
            assert "Verify with: `distill status`" in report

    def test_json_report_exposes_runtime_stage_layout_and_next_steps(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "lonely.md", "---\ntype: concept\ntitle: Lonely\nstatus: active\n---\n")
            checker = HealthChecker(vault)
            checker.scan()
            payload = json.loads(checker.report(fmt="json"))
            assert payload["runtime_stage"] == "preflight"
            assert payload["has_checkpoint"] is False
            assert payload["vault_layout"]["knowledge_dirs"]
            assert payload["scan_roots"]
            assert payload["next_steps"]

    def test_markdown_report_exposes_runtime_stage_layout_and_system_doc_signals(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            (vault / ".distill").mkdir()
            _write_md(vault / ".distill" / "checkpoint.json", "{}")
            _write_md(vault / "系统" / "技能" / "compose-output.md", "# skill\n")
            checker = HealthChecker(vault)
            checker.scan()
            report = checker.report()

            assert "- Runtime stage: trusted_runtime" in report
            assert "- True orphans: 0" in report
            assert "- System docs: 1" in report
            assert "## Vault Layout" in report
            assert "- system_dirs: ['系统', 'system']" in report
