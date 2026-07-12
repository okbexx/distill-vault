import inspect
import frontmatter
from typing import get_type_hints
from pathlib import Path

from click.testing import CliRunner

import distill.cli as cli_mod
import distill.routing as routing
from distill.cli import cli
from distill.mcp_tools import DistillMCPTools
from distill.routing import (
    build_apply_payload,
    build_route_payload,
    capture_progress_update,
    render_apply_markdown,
    render_plan_markdown,
    render_route_markdown,
    route_intent,
    route_plan,
)


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_zh_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "项目").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    _write_md(
        tmp_path / "知识" / "项目" / "激光雷达.md",
        "---\ntype: project\ntitle: 激光雷达\nstatus: active\n---\n# 激光雷达\n",
    )
    _write_md(
        tmp_path / "知识" / "来源" / "2026-05-12-碎碎念.md",
        "---\ntype: source\ntitle: 2026-05-12 碎碎念\nstatus: linked\n---\n",
    )
    return tmp_path


def _extract_bullet_fields(markdown: str, heading: str) -> list[str]:
    lines = markdown.splitlines()
    fields: list[str] = []
    capture = False
    for raw in lines:
        line = raw.strip()
        if line == heading:
            capture = True
            continue
        if not capture:
            continue
        if line.startswith("## ") or line.startswith("### "):
            break
        if line.startswith("- `") and line.endswith("`"):
            fields.append(line[3:-1])
    return fields


def test_public_runtime_surface_exports_are_explicit():
    assert routing.__all__ == [
        "CaptureResult",
        "PlanPayload",
        "RoutePayload",
        "ApplyPayload",
        "build_plan_payload",
        "build_route_payload",
        "build_apply_payload",
        "render_route_markdown",
        "render_plan_markdown",
        "render_apply_markdown",
        "route_intent",
        "route_plan",
        "capture_progress_update",
    ]


def test_public_runtime_surface_typed_dict_contracts_are_explicit():
    assert routing.PlanPayload.__required_keys__ == {
        "action",
        "status",
        "intent",
        "operation",
        "confidence",
        "target_project",
        "read_paths",
        "write_paths",
        "optional_paths",
        "skip_steps",
        "recommended_commit_paths",
        "recommended_commit_message",
        "recommended_commit_command",
        "why",
        "warnings",
    }
    assert routing.RoutePayload.__required_keys__ == {
        "intent",
        "operation",
        "confidence",
        "target_project",
        "read_paths",
        "write_paths",
        "optional_paths",
        "skip_steps",
        "recommended_commit_paths",
        "recommended_commit_message",
        "recommended_commit_command",
        "why",
        "warnings",
    }
    assert routing.ApplyPayload.__required_keys__ == {
        "action",
        "status",
        "operation",
        "source_path",
        "project_path",
        "touched_paths",
        "recommended_commit_paths",
        "recommended_commit_message",
        "recommended_commit_command",
    }


def test_public_runtime_surface_functions_use_typed_contracts():
    assert get_type_hints(routing.build_plan_payload)["return"] is routing.PlanPayload
    assert get_type_hints(routing.build_route_payload)["plan"] is routing.PlanPayload
    assert get_type_hints(routing.build_route_payload)["return"] is routing.RoutePayload
    assert get_type_hints(routing.build_apply_payload)["result"] is routing.CaptureResult
    assert get_type_hints(routing.build_apply_payload)["return"] is routing.ApplyPayload
    assert get_type_hints(routing.render_route_markdown)["payload"] is routing.RoutePayload
    assert get_type_hints(routing.render_plan_markdown)["payload"] is routing.PlanPayload
    assert get_type_hints(routing.render_apply_markdown)["payload"] is routing.ApplyPayload
    assert get_type_hints(routing.route_intent)["return"] is routing.RoutePayload
    assert get_type_hints(routing.route_plan)["return"] is routing.PlanPayload


def test_cli_and_mcp_handlers_expose_runtime_contract_annotations():
    route_hints = get_type_hints(cli_mod.route.callback)
    assert route_hints["intent"] is str
    assert route_hints["fmt"] is str
    assert route_hints["return"] is type(None)

    plan_hints = get_type_hints(cli_mod.plan_command.callback)
    assert plan_hints["intent"] is str
    assert plan_hints["fmt"] is str
    assert plan_hints["return"] is type(None)

    capture_hints = get_type_hints(cli_mod.capture.callback)
    assert capture_hints["intent"] is str
    assert capture_hints["fmt"] is str
    assert capture_hints["return"] is type(None)

    apply_hints = get_type_hints(cli_mod.apply.callback)
    assert apply_hints["intent"] is str
    assert apply_hints["fmt"] is str
    assert apply_hints["return"] is type(None)

    assert get_type_hints(DistillMCPTools.projection_route)["return"] is routing.RoutePayload
    assert get_type_hints(DistillMCPTools.projection_plan)["return"] is routing.PlanPayload
    assert get_type_hints(DistillMCPTools.projection_apply)["return"] is routing.ApplyPayload


def test_runtime_surface_contract_docs_match_typed_payload_snapshots():
    repo_root = Path(__file__).resolve().parents[1]
    docs_text = (repo_root / "docs" / "runtime-surface-contract.md").read_text(encoding="utf-8")
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")

    compact_fields = _extract_bullet_fields(docs_text, "Stable compact-route fields:")
    assert compact_fields == [
        "intent",
        "operation",
        "confidence",
        "target_project",
        "read_paths",
        "write_paths",
        "optional_paths",
        "skip_steps",
        "recommended_commit_paths",
        "recommended_commit_message",
        "recommended_commit_command",
        "why",
        "warnings",
    ]
    assert set(compact_fields) == routing.RoutePayload.__required_keys__

    full_plan_fields = _extract_bullet_fields(docs_text, "Stable full-plan fields:")
    assert full_plan_fields == [
        "action",
        "status",
        "intent",
        "operation",
        "confidence",
        "target_project",
        "read_paths",
        "write_paths",
        "optional_paths",
        "skip_steps",
        "recommended_commit_paths",
        "recommended_commit_message",
        "recommended_commit_command",
        "why",
        "warnings",
    ]
    assert set(full_plan_fields) == routing.PlanPayload.__required_keys__

    applied_fields = _extract_bullet_fields(docs_text, "Stable applied-result fields:")
    assert applied_fields == [
        "action",
        "status",
        "operation",
        "source_path",
        "project_path",
        "touched_paths",
        "recommended_commit_paths",
        "recommended_commit_message",
        "recommended_commit_command",
    ]
    assert set(applied_fields) == routing.ApplyPayload.__required_keys__

    assert "## Shared Runtime Surface Contract" in readme_text
    assert "build_route_payload(plan)" in readme_text
    assert "build_plan_payload(...)" in readme_text
    assert "build_apply_payload(result)" in readme_text


def test_public_runtime_surface_functions_have_contract_docstrings():
    for name in [
        "build_plan_payload",
        "build_route_payload",
        "build_apply_payload",
        "render_route_markdown",
        "render_plan_markdown",
        "render_apply_markdown",
        "route_intent",
        "route_plan",
        "capture_progress_update",
    ]:
        doc = inspect.getdoc(getattr(routing, name))
        assert doc, f"missing docstring for {name}"

    route_doc = inspect.getdoc(routing.build_route_payload)
    assert "compact route" in route_doc.lower()
    assert "action" in route_doc
    assert "status" in route_doc
    assert "does not include" in route_doc.lower()

    plan_doc = inspect.getdoc(routing.build_plan_payload)
    assert "full plan" in plan_doc.lower()
    assert "recommended_commit_message" in plan_doc
    assert "recommended_commit_command" in plan_doc

    apply_doc = inspect.getdoc(routing.build_apply_payload)
    assert "applied result" in apply_doc.lower()
    assert "touched_paths" in apply_doc
    assert "recommended_commit_paths" in apply_doc


def test_route_fact_capture_returns_minimal_file_surface(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    plan = route_plan(vault, "记录一下激光雷达已完成 UAT 发布并通过验证")

    assert plan["action"] == "knowledge_capture"
    assert plan["status"] == "planned"
    assert plan["operation"] == "fact_capture"
    assert plan["confidence"] == "high"
    assert plan["target_project"] == "激光雷达"
    assert plan["read_paths"] == [
        "知识/项目/激光雷达.md",
        "知识/来源/2026-05-12-碎碎念.md",
    ]
    assert plan["write_paths"] == [
        "知识/来源/2026-05-12-碎碎念.md",
        "知识/项目/激光雷达.md",
    ]
    assert plan["skip_steps"] == [
        "distill run",
        "repo-wide lint",
        "repo-wide index maintenance",
    ]
    assert plan["recommended_commit_paths"] == [
        "知识/来源/2026-05-12-碎碎念.md",
        "知识/项目/激光雷达.md",
    ]
    assert plan["recommended_commit_message"] == "知识库: 记录激光雷达成果"
    assert "distill commit" in plan["recommended_commit_command"]
    assert "--skip-run" in plan["recommended_commit_command"]


def test_build_route_payload_matches_compact_route_surface(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    plan = route_plan(vault, "记录一下激光雷达今天进展，UAT已发布")
    compact = build_route_payload(plan)

    assert compact == route_intent(vault, "记录一下激光雷达今天进展，UAT已发布")
    assert "action" not in compact
    assert "status" not in compact


def test_route_cli_json_is_machine_readable(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "route", "记录一下激光雷达今天进展", "--format", "json"],
    )

    assert result.exit_code == 0
    assert result.output.lstrip().startswith("{")
    assert '"operation": "fact_capture"' in result.output
    assert '"read_paths": [' in result.output
    assert '"action":' not in result.output
    assert '"status":' not in result.output


def test_plan_cli_json_is_machine_readable(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "plan", "记录一下激光雷达今天进展", "--format", "json"],
    )

    assert result.exit_code == 0
    assert result.output.lstrip().startswith("{")
    assert '"action": "knowledge_capture"' in result.output
    assert '"status": "planned"' in result.output
    assert '"operation": "fact_capture"' in result.output


def test_render_route_markdown_matches_current_cli_surface(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    route_payload = route_intent(vault, "记录一下激光雷达今天进展，UAT已发布")

    assert render_route_markdown(route_payload) == (
        "Operation: fact_capture\n"
        "Confidence: high\n"
        "Target project: 激光雷达\n"
        "Read paths:\n"
        "  - 知识/项目/激光雷达.md\n"
        "  - 知识/来源/2026-05-12-碎碎念.md\n"
        "Write paths:\n"
        "  - 知识/来源/2026-05-12-碎碎念.md\n"
        "  - 知识/项目/激光雷达.md\n"
        "Skip steps:\n"
        "  - distill run\n"
        "  - repo-wide lint\n"
        "  - repo-wide index maintenance\n"
        "Recommended commit:\n"
        '  distill commit "知识库: 记录激光雷达成果" --paths 知识/来源/2026-05-12-碎碎念.md --paths 知识/项目/激光雷达.md --skip-run'
    )


def test_route_cli_markdown_matches_shared_renderer(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "route", "记录一下激光雷达今天进展，UAT已发布"],
    )

    expected = render_route_markdown(route_intent(vault, "记录一下激光雷达今天进展，UAT已发布"))
    assert result.exit_code == 0
    assert result.output == expected + "\n"


def test_render_plan_markdown_matches_current_cli_surface(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    plan = route_plan(vault, "记录一下激光雷达今天进展，UAT已发布")

    assert render_plan_markdown(plan) == (
        "Action: knowledge_capture\n"
        "Status: planned\n"
        "Operation: fact_capture\n"
        "Confidence: high\n"
        "Target project: 激光雷达\n"
        "Read paths:\n"
        "  - 知识/项目/激光雷达.md\n"
        "  - 知识/来源/2026-05-12-碎碎念.md\n"
        "Write paths:\n"
        "  - 知识/来源/2026-05-12-碎碎念.md\n"
        "  - 知识/项目/激光雷达.md\n"
        "Skip steps:\n"
        "  - distill run\n"
        "  - repo-wide lint\n"
        "  - repo-wide index maintenance\n"
        "Recommended commit:\n"
        '  distill commit "知识库: 记录激光雷达成果" --paths 知识/来源/2026-05-12-碎碎念.md --paths 知识/项目/激光雷达.md --skip-run'
    )


def test_plan_cli_markdown_matches_shared_renderer(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "plan", "记录一下激光雷达今天进展，UAT已发布"],
    )

    expected = render_plan_markdown(route_plan(vault, "记录一下激光雷达今天进展，UAT已发布"))
    assert result.exit_code == 0
    assert result.output == expected + "\n"


def test_route_generic_update_warns_when_project_is_missing(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    plan = route_plan(vault, "记录一下今天的进展")

    assert plan["action"] == "generic_update"
    assert plan["status"] == "needs_disambiguation"
    assert plan["operation"] == "generic_update"
    assert plan["warnings"]
    assert "No matching project object found" in plan["warnings"][0]


def test_capture_progress_update_appends_source_and_refreshes_project_dossier(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    project_path = vault / "知识" / "项目" / "激光雷达.md"
    project_text = project_path.read_text(encoding="utf-8")
    project_path.write_text(
        project_text.replace(
            "status: active\n",
            "status: active\nsummary: 长期项目摘要\n",
            1,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    result = capture_progress_update(vault, "记录一下激光雷达已完成 UAT 发布并通过验证")

    assert result.action == "knowledge_capture"
    assert result.status == "applied"
    assert result.touched_paths == [
        "知识/来源/2026-05-12-碎碎念.md",
        "知识/项目/激光雷达.md",
    ]
    assert result.recommended_commit_paths == result.touched_paths
    assert result.recommended_commit_message == "知识库: 记录激光雷达成果"
    assert "--skip-run" in result.recommended_commit_command
    source_text = (vault / "知识" / "来源" / "2026-05-12-碎碎念.md").read_text(encoding="utf-8")
    project_text = (vault / "知识" / "项目" / "激光雷达.md").read_text(encoding="utf-8")
    source_post = frontmatter.load(vault / "知识" / "来源" / "2026-05-12-碎碎念.md")
    assert "- 记录一下激光雷达已完成 UAT 发布并通过验证" in source_text
    assert source_post.metadata == {
        "id": "source-2026-05-12-碎碎念",
        "type": "source",
        "title": "2026-05-12 碎碎念",
        "source_type": "conversation",
        "created_at": "2026-05-12",
        "source_url": None,
        "author": None,
        "reliability": "high",
        "status": "linked",
        "projects": ["[[知识/项目/激光雷达]]"],
        "concepts": [],
        "entities": [],
        "outputs": [],
        "lifecycle_stage": "linked",
    }
    assert source_text.endswith("\n")
    assert "updated: '2026-05-12'" in project_text
    assert "summary: 长期项目摘要" in project_text
    assert "summary: 记录一下激光雷达已完成 UAT 发布并通过验证" not in project_text
    assert "current_focus:" not in project_text
    assert "next_step:" not in project_text
    assert "[[知识/来源/2026-05-12-碎碎念]]" in project_text
    assert project_text.endswith("\n")


def test_capture_progress_update_preserves_existing_project_body(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    _write_md(
        vault / "知识" / "项目" / "激光雷达.md",
        "---\ntype: project\ntitle: 激光雷达\nstatus: active\n---\n# 激光雷达\n\n已有正文\n",
    )
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    capture_progress_update(vault, "记录一下激光雷达今天进展，UAT已发布")

    project_text = (vault / "知识" / "项目" / "激光雷达.md").read_text(encoding="utf-8")
    assert "已有正文" in project_text
    assert "## 已验证事实" in project_text
    assert "- 2026-05-12: 记录一下激光雷达今天进展，UAT已发布" in project_text


def test_build_apply_payload_matches_capture_result_surface(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    result = capture_progress_update(vault, "记录一下激光雷达已完成 UAT 发布并通过验证")
    payload = build_apply_payload(result)

    assert payload == {
        "action": "knowledge_capture",
        "status": "applied",
        "operation": "fact_capture",
        "source_path": "知识/来源/2026-05-12-碎碎念.md",
        "project_path": "知识/项目/激光雷达.md",
        "touched_paths": [
            "知识/来源/2026-05-12-碎碎念.md",
            "知识/项目/激光雷达.md",
        ],
        "recommended_commit_paths": [
            "知识/来源/2026-05-12-碎碎念.md",
            "知识/项目/激光雷达.md",
        ],
        "recommended_commit_message": "知识库: 记录激光雷达成果",
        "recommended_commit_command": 'distill commit "知识库: 记录激光雷达成果" --paths 知识/来源/2026-05-12-碎碎念.md --paths 知识/项目/激光雷达.md --skip-run',
    }


def test_capture_cli_json_is_machine_readable_and_writes_files(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(vault),
            "capture",
            "记录一下激光雷达已完成 UAT 发布并通过验证",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("{")
    assert '"action": "knowledge_capture"' in result.output
    assert '"status": "applied"' in result.output
    assert '"recommended_commit_message": "知识库: 记录激光雷达成果"' in result.output
    source_text = (vault / "知识" / "来源" / "2026-05-12-碎碎念.md").read_text(encoding="utf-8")
    assert "UAT 发布并通过验证" in source_text


def test_render_apply_markdown_matches_current_cli_surface(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")

    result = capture_progress_update(vault, "记录一下激光雷达已完成 UAT 发布并通过验证")
    payload = build_apply_payload(result)

    assert render_apply_markdown(payload, verb="Captured") == (
        "✓ Captured\n"
        "Source: 知识/来源/2026-05-12-碎碎念.md\n"
        "Project: 知识/项目/激光雷达.md\n"
        "Touched paths:\n"
        "  - 知识/来源/2026-05-12-碎碎念.md\n"
        "  - 知识/项目/激光雷达.md"
    )
    assert render_apply_markdown(payload, verb="Applied").splitlines()[0] == "✓ Applied"


def test_capture_cli_markdown_matches_shared_renderer(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    expected_vault = _make_zh_vault(tmp_path / "expected-capture")
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "capture", "记录一下激光雷达已完成 UAT 发布并通过验证"],
    )

    payload = build_apply_payload(
        capture_progress_update(expected_vault, "记录一下激光雷达已完成 UAT 发布并通过验证")
    )
    expected = render_apply_markdown(payload, verb="Captured")
    assert result.exit_code == 0
    assert result.output == expected + "\n"


def test_apply_cli_json_is_machine_readable_and_writes_files(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(vault),
            "apply",
            "记录一下激光雷达已完成 UAT 发布并通过验证",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("{")
    assert '"action": "knowledge_capture"' in result.output
    assert '"status": "applied"' in result.output
    assert '"recommended_commit_paths": [' in result.output
    project_text = (vault / "知识" / "项目" / "激光雷达.md").read_text(encoding="utf-8")
    assert "summary:" not in project_text
    assert "- 2026-05-12: 记录一下激光雷达已完成 UAT 发布并通过验证" in project_text


def test_apply_cli_markdown_matches_shared_renderer(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    expected_vault = _make_zh_vault(tmp_path / "expected-apply")
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "apply", "记录一下激光雷达已完成 UAT 发布并通过验证"],
    )

    payload = build_apply_payload(
        capture_progress_update(expected_vault, "记录一下激光雷达已完成 UAT 发布并通过验证")
    )
    expected = render_apply_markdown(payload, verb="Applied")
    assert result.exit_code == 0
    assert result.output == expected + "\n"


def test_route_rejects_schedule_language_for_project_dossier(tmp_path):
    vault = _make_zh_vault(tmp_path)

    plan = route_plan(vault, "激光雷达已完成 UAT 发布，下一步准备生产上线")

    assert plan["status"] == "needs_disambiguation"
    assert plan["operation"] == "fact_capture"
    assert plan["write_paths"] == []
    assert "completed facts" in plan["warnings"][0]


def test_capture_cli_fails_for_ambiguous_generic_update(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "capture", "记录一下今天的进展"],
    )

    assert result.exit_code != 0
    assert "Capture failed:" in result.output
    assert "No matching project object found" in result.output


def test_apply_cli_fails_for_ambiguous_generic_update(tmp_path, monkeypatch):
    vault = _make_zh_vault(tmp_path)
    monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "apply", "记录一下今天的进展"],
    )

    assert result.exit_code != 0
    assert "Apply failed:" in result.output
    assert "No matching project object found" in result.output
