"""Real filesystem and Git contracts for lightweight recording."""
import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from distill.cli import cli
from distill.commit import DistillCommit
from distill.init_cmd import init_vault
from distill.mcp_tools import DistillMCPTools, MCPToolError


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    init_vault(str(root), lang="en", with_examples=False)
    import yaml
    config_path = root / "distill.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["schema"] = {"path": "schema.json", "include_globs": ["knowledge/*.md"]}
    config_path.write_text(yaml.safe_dump(config))
    (root / "schema.json").write_text(json.dumps({"type": "object", "properties": {"title": {"type": "string"}}}))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    for args in [("init",), ("config", "user.name", "Test"), ("config", "user.email", "test@example.invalid")]:
        subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return root


def note(vault, name, body="hello", title="Test"):
    path = vault / "knowledge" / name
    path.write_text(f"---\ntype: concept\ntitle: {title}\nstatus: active\n---\n{body}\n")
    return path.relative_to(vault).as_posix()


def test_cli_source_only_preserves_arbitrary_text_and_attachment(vault, tmp_path):
    text = "  也许，明天？\r\n\n[[not-a-fact]]\n  "
    attachment = tmp_path / "image.bin"
    attachment.write_bytes(b"\x00\xfforiginal")
    result = CliRunner().invoke(cli, ["--vault", str(vault), "record", text, "--attachment", str(attachment), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["operation"] == "source_only"
    assert (vault / payload["raw_path"]).read_bytes() == text.encode()
    assert (vault / payload["attachment_paths"][0]).read_bytes() == attachment.read_bytes()
    assert payload["recommended_commit_paths"] == payload["touched_paths"]
    committed = DistillCommit(vault).commit("raw evidence", paths=payload["touched_paths"], skip_run=True)
    assert committed["success"], committed
    assert not list((vault / "knowledge/project").glob("*.md"))


def test_mcp_source_only_preserves_repeated_text(vault):
    tools = DistillMCPTools(vault)
    a = tools.call_tool("source_record", {"text": "a random thought"})
    b = tools.call_tool("source_record", {"text": "a random thought"})
    assert a["source_path"] != b["source_path"]
    assert (vault / a["raw_path"]).read_bytes() == b"a random thought"
    with pytest.raises(MCPToolError):
        tools.call_tool("source_record", {"text": "  \n"})


def test_source_only_rejects_escaping_directory_without_writing(vault, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    source = vault / "knowledge/source"
    if source.exists():
        source.rmdir()
    source.symlink_to(outside, target_is_directory=True)
    with pytest.raises(MCPToolError):
        DistillMCPTools(vault).call_tool("source_record", {"text": "anything"})
    assert list(outside.iterdir()) == []


def test_source_only_same_attachment_names_do_not_overwrite(vault, tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    (a / "same.bin").write_bytes(b"a")
    (b / "same.bin").write_bytes(b"b")
    result = DistillMCPTools(vault).call_tool("source_record", {"text": "?", "attachments": [str(a / "same.bin"), str(b / "same.bin")]})
    assert [(vault / p).read_bytes() for p in result["attachment_paths"]] == [b"a", b"b"]


def test_scoped_commit_ignores_old_schema_and_links_but_full_blocks(vault):
    note(vault, "old.md", "[[missing]]", title="[]")
    good = note(vault, "good.md")
    result = DistillCommit(vault).commit("local", paths=[good], skip_run=True)
    assert result["success"], result
    names = subprocess.run(["git", "show", "--pretty=", "--name-only", "HEAD"], cwd=vault, capture_output=True, text=True, check=True).stdout.splitlines()
    assert names == [good]
    assert not DistillCommit(vault).commit("full", skip_run=True)["success"]


@pytest.mark.parametrize("body,title", [("[[missing]]", "Good"), ("hello", "[]")])
def test_scoped_commit_blocks_selected_errors_after_many_old_errors(vault, body, title):
    for i in range(60):
        note(vault, f"a{i:03}.md", f"[[old-missing-{i}]]")
    bad = note(vault, "zz.md", body, title)
    result = DistillCommit(vault).commit("bad", paths=[bad], skip_run=True)
    assert not result["success"]
    assert any(issue["file"] == bad for issue in result["lint_issues"]), result


def test_raw_inbox_is_informational_but_stable_orphan_is_not(vault):
    from distill.lint import VaultLinter
    raw = note(vault, "raw.md")
    (vault / raw).write_text("---\ntitle: Raw\ntype: source\nstatus: raw\nlifecycle_stage: raw\n---\nanything")
    stable = note(vault, "stable.md")
    linter = VaultLinter(vault)
    linter.scan()
    issues = linter.lint()
    assert next(i for i in issues if i.get("file") == raw and i["rule"] == "orphan-object")["severity"] == "info"
    assert next(i for i in issues if i.get("file") == stable and i["rule"] == "orphan-object")["severity"] == "warning"
    assert raw not in linter.index.orphan_buckets["true_orphan"]


def test_record_uses_custom_knowledge_root(vault):
    import yaml
    config_path = vault / "distill.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["vault"]["knowledge_dirs"] = ["收件箱", "项目", "访问资料"]
    config["capture"] = {"source_dir": "收件箱"}
    config_path.write_text(yaml.safe_dump(config))
    result = DistillMCPTools(vault).call_tool("source_record", {"text": "随便记下"})
    assert result["source_path"].startswith("收件箱/")


def test_record_is_searchable_through_cli(vault):
    result = DistillMCPTools(vault).call_tool("source_record", {"text": "violet-zephyr-otter a fleeting thought"})
    output = CliRunner().invoke(cli, ["--vault", str(vault), "search", "violet-zephyr-otter"])
    assert output.exit_code == 0, output.output
    assert result["source_path"] in output.output


@pytest.mark.parametrize("value", ["", "/tmp/outside", "../outside", ":(glob)**", "knowledge/*.md"])
def test_scoped_commit_rejects_nonliteral_paths(vault, value):
    result = DistillCommit(vault).commit("unsafe", paths=[value], skip_run=True)
    assert not result["success"], result


def test_scoped_commit_rejects_deleting_referenced_target(vault):
    target = note(vault, "target.md", title="Target")
    note(vault, "referrer.md", "[[Target]]")
    assert DistillCommit(vault).commit("initial", skip_run=True, skip_lint=True)["success"]
    (vault / target).unlink()
    result = DistillCommit(vault).commit("delete", paths=[target], skip_run=True)
    assert not result["success"], result
    assert "delet" in str(result).lower()


def test_attachment_only_and_bad_attachment_leave_no_partial_record(vault, tmp_path):
    tools = DistillMCPTools(vault)
    attachment = tmp_path / "only.bin"
    attachment.write_bytes(b"only")
    payload = tools.call_tool("source_record", {"text": "", "attachments": [str(attachment)]})
    assert (vault / payload["attachment_paths"][0]).read_bytes() == b"only"
    before = set(vault.rglob("*"))
    with pytest.raises(MCPToolError):
        tools.call_tool("source_record", {"text": "some text", "attachments": [str(tmp_path / "missing")]})
    assert set(vault.rglob("*")) == before


def test_scoped_commit_does_not_commit_unrelated_staged_file(vault):
    selected = note(vault, "selected.md")
    other = note(vault, "other.md", "[[broken]]")
    subprocess.run(["git", "add", "--", other], cwd=vault, check=True)
    result = DistillCommit(vault).commit("selected", paths=[selected], skip_run=True)
    assert result["success"], result
    names = subprocess.run(["git", "show", "--pretty=", "--name-only", "HEAD"], cwd=vault, capture_output=True, text=True, check=True).stdout.splitlines()
    assert names == [selected]


def test_scoped_symlink_escape_is_rejected(vault, tmp_path):
    (vault / "escape").symlink_to(tmp_path, target_is_directory=True)
    result = DistillCommit(vault).commit("unsafe", paths=["escape/outside.md"], skip_run=True)
    assert not result["success"], result


def test_scoped_links_resolve_outside_selection(vault):
    note(vault, "target.md", title="Target")
    selected = note(vault, "selected.md", "[[Target]]")
    result = DistillCommit(vault).commit("linked", paths=[selected], skip_run=True)
    assert result["success"], result
