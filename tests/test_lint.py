import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from distill.cli import cli
from distill.lint import VaultLinter


def _make_vault(tmp_path: Path):
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "系统" / "规范").mkdir(parents=True)
    (tmp_path / "运维" / "日志").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestVaultLinter:
    def test_presentation_contract_requires_complete_heading_set(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            path = vault / "知识" / "概念" / "foo.md"
            _write_md(
                path,
                "---\ntype: concept\ntitle: Foo\nstatus: active\n"
                "presentation: knowledge-compounding-v1\n---\n# Foo\n\n## 一句话结论\nFoo.\n",
            )
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert any(i["rule"] == "incomplete-presentation-contract" for i in issues)

            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n### 知识生命周期\n\n### 适用与复用\n\n### 证据与演化\n",
                encoding="utf-8",
            )
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert any(i["rule"] == "incomplete-presentation-contract" for i in issues)

            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n## 知识生命周期\n\n## 适用与复用\n\n## 证据与演化\n",
                encoding="utf-8",
            )
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert not any(i["rule"] == "incomplete-presentation-contract" for i in issues)

    def test_no_issues_on_clean_vault(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo")
            _write_md(vault / "知识" / "来源" / "ref.md", "---\ntype: source\ntitle: Ref\nstatus: linked\n---\n[[Foo]]")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert not any(i["severity"] == "error" for i in issues)
            assert not any(i["rule"] == "broken-wikilink" for i in issues)
            assert not any(i["rule"] == "missing-frontmatter" for i in issues)
            assert not any(i["rule"] == "unknown-type" for i in issues)

    def test_detects_broken_link(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "bad.md", "---\ntype: source\ntitle: Bad\nstatus: linked\n---\n[[Missing]]")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert any(i["rule"] == "broken-wikilink" for i in issues)

    def test_detects_unknown_type(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "weird.md", "---\ntype: weird\ntitle: Weird\nstatus: active\n---\n")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert any(i["rule"] == "unknown-type" for i in issues)

    def test_skill_spec_is_a_known_system_type(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "系统" / "技能" / "ops.md", "---\ntype: skill_spec\ntitle: Ops\nstatus: active\n---\n")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            assert not any(i["rule"] == "unknown-type" for i in issues)

    def test_fix_frontmatter_types(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "cn.md", "---\ntype: 来源\ntitle: CN\nstatus: linked\n---\n")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint(fix=True)
            assert not any(i["rule"] == "unknown-type" for i in issues)

    def test_fix_non_md_wikilinks(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "img.md", "---\ntype: source\ntitle: Img\nstatus: linked\n---\n[[assets/pic.jpg]]")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint(fix=True)
            content = (vault / "知识" / "来源" / "img.md").read_text()
            assert "assets/pic.jpg" in content
            assert "[[assets/pic.jpg]]" not in content

    def test_fix_obsidian_pseudo_links(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "知识" / "来源" / "links.md",
                "---\ntype: source\ntitle: Links\nstatus: linked\noutputs:\n  - \"GitHub: okbexx/distill-vault\"\n---\n[[站点: https://okbexx.github.io/]]\n[[输出/报告/demo.html]]",
            )
            linter = VaultLinter(vault)
            linter.scan()
            linter.lint(fix=True)
            content = (vault / "知识" / "来源" / "links.md").read_text()
            assert "[[站点: https://okbexx.github.io/]]" not in content
            assert "站点: https://okbexx.github.io/" in content
            assert "[[输出/报告/demo.html]]" not in content
            assert "输出/报告/demo.html" in content

    def test_system_doc_orphans_are_info_not_warning(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "系统" / "规范" / "guide.md", "# system doc")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            orphan_issue = next(i for i in issues if i["file"] == "系统/规范/guide.md" and i["rule"] == "orphan-object")
            assert orphan_issue["severity"] == "info"
            assert orphan_issue["orphan_bucket"] == "system_doc"
            assert orphan_issue["message"] == "System doc (informational): 系统/规范/guide.md"

    def test_timeline_archive_orphans_are_info_not_warning(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "输出" / "daily.md",
                "---\ntype: output\ntitle: Daily\noutput_type: daily\n---\n",
            )
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            orphan_issue = next(i for i in issues if i["file"] == "输出/daily.md" and i["rule"] == "orphan-object")
            assert orphan_issue["severity"] == "info"
            assert orphan_issue["orphan_bucket"] == "timeline_archive"
            assert orphan_issue["message"] == "Timeline archive (informational): 输出/daily.md"

            result = CliRunner().invoke(cli, ["--vault", str(vault), "lint", "--format", "json"])
            payload = json.loads(result.output)
            assert not any("true orphan" in step["title"].lower() for step in payload["next_steps"])

    def test_strict_cli_does_not_fail_on_info_only_findings(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "系统" / "规范" / "guide.md", "# system doc")
            result = CliRunner().invoke(cli, ["--vault", str(vault), "lint", "--strict"])
            assert result.exit_code == 0
            assert "[INFO]" in result.output

    def test_strict_json_cli_returns_failure_for_warning(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "知识" / "概念" / "weird.md",
                "---\ntype: weird\ntitle: Weird\nstatus: active\n---\n",
            )
            result = CliRunner().invoke(
                cli,
                ["--vault", str(vault), "lint", "--strict", "--format", "json"],
            )
            assert result.exit_code == 1
            assert json.loads(result.output)["issue_count"] >= 1

    def test_frontmatter_required_only_for_object_paths_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "概念" / "foo.md", "# no frontmatter")
            _write_md(vault / "系统" / "规范" / "guide.md", "# system doc")
            _write_md(vault / "运维" / "日志" / "ops.md", "# ops doc")
            _write_md(vault / "输出" / "artifact.md", "# generated output")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            frontmatter_files = {i["file"] for i in issues if i["rule"] == "incomplete-frontmatter"}
            assert "知识/概念/foo.md" in frontmatter_files
            assert "系统/规范/guide.md" not in frontmatter_files
            assert "运维/日志/ops.md" not in frontmatter_files
            assert "输出/artifact.md" not in frontmatter_files

    def test_frontmatter_required_globs_can_include_system_docs(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "distill.yaml",
                "lint:\n  frontmatter_required_globs:\n    - '知识/**/*.md'\n    - '系统/规范/*.md'\n",
            )
            _write_md(vault / "系统" / "规范" / "guide.md", "# system doc")
            linter = VaultLinter(vault)
            linter.scan()
            issues = linter.lint()
            frontmatter_files = {i["file"] for i in issues if i["rule"] == "incomplete-frontmatter"}
            assert "系统/规范/guide.md" in frontmatter_files

    def test_lint_cli_includes_recommended_next_steps(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "bad.md", "---\ntype: source\ntitle: Bad\nstatus: linked\n---\n[[Missing]]")
            _write_md(vault / "知识" / "概念" / "weird.md", "---\ntype: weird\ntitle: Weird\nstatus: active\n---\n")
            runner = CliRunner()
            result = runner.invoke(cli, ["--vault", str(vault), "lint"])
            assert result.exit_code == 1
            assert "## Recommended Next Steps" in result.output
            assert "Resolve broken wikilinks before anything else" in result.output
            assert "Run the safe auto-fix pass for metadata issues" in result.output
            assert "Verify with: `distill lint --fix`" in result.output

    def test_lint_cli_marks_existing_vault_preflight_before_first_run(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "bad.md", "---\ntype: source\ntitle: Bad\nstatus: linked\n---\n[[Missing]]")
            runner = CliRunner()
            result = runner.invoke(cli, ["--vault", str(vault), "lint"])
            assert result.exit_code == 1
            assert "Finish structural preflight before the first pipeline run" in result.output
            assert "No pipeline checkpoint exists yet" in result.output
            assert "Verify with: `distill lint`" in result.output

    def test_lint_json_exposes_runtime_surface_and_issue_count(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "bad.md", "---\ntype: source\ntitle: Bad\nstatus: linked\n---\n[[Missing]]")
            runner = CliRunner()
            result = runner.invoke(cli, ["--vault", str(vault), "lint", "--format", "json"])

            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["issue_count"] >= 1
            assert payload["runtime_stage"] == "preflight"
            assert payload["has_checkpoint"] is False
            assert payload["scan_roots"]
            assert payload["vault_layout"]["knowledge_dirs"]
            assert payload["next_steps"]
