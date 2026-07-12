import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from distill.cli import cli


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_flat_obsidian_vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    _write_md(
        tmp_path / "alpha.md",
        "---\ntype: concept\ntitle: Alpha\nstatus: active\n---\n[[Beta]]\n",
    )
    _write_md(
        tmp_path / "beta.md",
        "---\ntype: concept\ntitle: Beta\nstatus: active\n---\n",
    )
    return tmp_path


def test_status_explicit_vault_works_without_distill_yaml_in_obsidian_vault(tmp_path):
    vault = _make_flat_obsidian_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "status", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total_objects"] == 2
    assert payload["total_wikilinks"] == 1
    assert payload["runtime_stage"] == "preflight"
    assert payload["has_checkpoint"] is False
    assert payload["scan_roots"] == ["."]
    assert payload["vault_layout"]["knowledge_dirs"] == ["."]
    assert payload["next_steps"]


def test_status_auto_detects_obsidian_vault_from_cwd(tmp_path, monkeypatch):
    vault = _make_flat_obsidian_vault(tmp_path)
    runner = CliRunner()
    monkeypatch.chdir(vault)

    result = runner.invoke(cli, ["status", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total_objects"] == 2


def test_init_existing_preserves_readme_and_writes_inferred_config(tmp_path):
    vault = _make_flat_obsidian_vault(tmp_path)
    original_readme = "# My vault\n"
    (vault / "README.md").write_text(original_readme, encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(cli, ["init", str(vault), "--existing", "--lang", "en"])

    assert result.exit_code == 0
    assert (vault / "README.md").read_text(encoding="utf-8") == original_readme
    assert "distill status" in result.output
    assert "distill lint" in result.output
    assert "distill run" in result.output
    assert "distill health" in result.output
    assert "preflight gate" in result.output
    config = yaml.safe_load((vault / "distill.yaml").read_text(encoding="utf-8"))
    assert config["vault"]["knowledge_dirs"] == ["."]
    assert config["vault"]["ops_dirs"] == [".distill"]


def test_init_existing_mixed_layout_prefers_canonical_roots_and_keeps_status_stable(tmp_path):
    vault = tmp_path
    (vault / ".obsidian").mkdir()
    _write_md(
        vault / "知识" / "概念" / "foo.md",
        "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n",
    )
    _write_md(
        vault / "输出" / "report.md",
        "---\ntype: output\ntitle: Report\nstatus: draft\n---\n",
    )
    _write_md(vault / "系统" / "规范" / "guide.md", "# guide\n")
    _write_md(vault / "运维" / "日志" / "run.md", "# run\n")
    _write_md(vault / "docker" / "notes.md", "# unrelated\n")
    _write_md(vault / "兼容层" / "compat.md", "# unrelated\n")
    (vault / "README.md").write_text("# existing\n", encoding="utf-8")
    runner = CliRunner()

    before = runner.invoke(cli, ["--vault", str(vault), "status", "--format", "json"])
    assert before.exit_code == 0
    before_payload = json.loads(before.output)

    init_result = runner.invoke(cli, ["init", str(vault), "--existing", "--lang", "zh"])
    assert init_result.exit_code == 0

    config = yaml.safe_load((vault / "distill.yaml").read_text(encoding="utf-8"))
    assert config["vault"]["knowledge_dirs"] == ["知识"]
    assert config["vault"]["output_dirs"] == ["输出"]
    assert config["vault"]["ops_dirs"] == ["运维"]
    assert config["vault"]["system_dirs"] == ["系统"]

    after = runner.invoke(cli, ["--vault", str(vault), "status", "--format", "json"])
    assert after.exit_code == 0
    after_payload = json.loads(after.output)
    assert after_payload["total_objects"] == before_payload["total_objects"]
