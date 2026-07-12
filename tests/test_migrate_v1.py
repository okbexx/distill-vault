from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from distill.cli import cli
from distill.migrate import migrate_vault


def _write_vault_contract(vault: Path) -> None:
    (vault / "系统" / "规范").mkdir(parents=True)
    (vault / "distill.yaml").write_text(
        """vault:
  knowledge_dirs: [知识]
  output_dirs: [输出]
  ops_dirs: [运维]
  system_dirs: [系统]
schema:
  path: 系统/规范/object.schema.json
  include_globs:
    - 知识/**/*.md
    - 输出/**/*.md
""",
        encoding="utf-8",
    )
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["id", "type", "title", "status", "lifecycle_stage"],
        "properties": {
            "id": {"type": "string"},
            "type": {"enum": ["source", "output", "project", "concept", "decision", "constraint"]},
            "title": {"type": "string"},
            "status": {"type": "string"},
            "lifecycle_stage": {"type": "string"},
        },
    }
    (vault / "系统" / "规范" / "object.schema.json").write_text(
        json.dumps(schema),
        encoding="utf-8",
    )


def _make_legacy_vault(tmp_path: Path) -> Path:
    vault = tmp_path
    _write_vault_contract(vault)
    source = vault / "知识" / "来源" / "2026-07-10-碎碎念.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\ntype: source\ntitle: 今日记录\nstatus: linked\n---\n原文保持不变。\n",
        encoding="utf-8",
    )
    log = vault / "输出" / "日志" / "2026-07-10日报.md"
    log.parent.mkdir(parents=True)
    log.write_text(
        "---\ntype: log\ntitle: 2026-07-10 日报\ndate: 2026-07-10\n---\n正文保持不变。\n",
        encoding="utf-8",
    )
    project = vault / "知识" / "项目" / "demo.md"
    project.parent.mkdir(parents=True)
    project.write_text(
        "---\nid: project-demo\ntype: project\ntitle: Demo\nstatus: active\n"
        "goal: keep this\ngoal:\noutputs:\n  - '[[输出/日志/2026-07-10日报]]'\n"
        "  - '[[输出/日志/2026-07-10日报]]'\n---\n# Demo\n",
        encoding="utf-8",
    )
    return vault


def test_migration_is_previewed_applied_and_idempotent(tmp_path):
    vault = _make_legacy_vault(tmp_path)
    source_before = (vault / "知识" / "来源" / "2026-07-10-碎碎念.md").read_text(encoding="utf-8")

    preview = migrate_vault(vault, target_version=1)
    assert preview["apply"] is False
    assert preview["files_changed"] == 3
    assert preview["validation_errors"] == []
    assert (vault / "知识" / "来源" / "2026-07-10-碎碎念.md").read_text(encoding="utf-8") == source_before

    applied = migrate_vault(vault, target_version=1, apply=True)
    assert applied["files_changed"] == 3
    source = (vault / "知识" / "来源" / "2026-07-10-碎碎念.md").read_text(encoding="utf-8")
    assert "id: source-2026-07-10-碎碎念" in source
    assert "source_type: conversation" in source
    assert source.endswith("原文保持不变。\n")

    log = (vault / "输出" / "日志" / "2026-07-10日报.md").read_text(encoding="utf-8")
    assert "type: output" in log
    assert "output_type: log" in log
    assert "status: completed" in log

    project = (vault / "知识" / "项目" / "demo.md").read_text(encoding="utf-8")
    assert project.count("goal:") == 1
    assert "goal: keep this" in project
    assert project.count("[[输出/日志/2026-07-10日报]]") == 1

    second = migrate_vault(vault, target_version=1)
    assert second["files_changed"] == 0
    assert second["changes"] == []


def test_migrate_cli_defaults_to_preview(tmp_path):
    vault = _make_legacy_vault(tmp_path)
    result = CliRunner().invoke(cli, ["--vault", str(vault), "migrate", "--to", "1"])
    assert result.exit_code == 0
    assert "Migration v1 (preview)" in result.output
    assert "changed: 3" in result.output


def test_v2_migrates_project_into_knowledge_dossier(tmp_path):
    vault = _make_legacy_vault(tmp_path)
    project = vault / "知识" / "项目" / "demo.md"
    project.write_text(
        "---\nid: project-demo\ntype: project\ntitle: Demo\nstatus: active\n"
        "goal: Preserve completed work\ncurrent_focus: Released the first version.\n"
        "next_step:\n  - Ship another version\n"
        "sources:\n  - 知识/来源/2026-07-10-碎碎念\n"
        "outputs:\n  - '[[输出/日志/2026-07-10日报]]'\n"
        "  - '[[输出/报告/验收报告]]'\n"
        "decisions: []\nconstraints: []\nconcepts: []\nentities: []\n"
        "lifecycle_stage: maintained\n---\n# Demo\n\n## 状态摘要\n- Released.\n"
        "\n## 下一步\n- Ship another version.\n\n## 证据\n- Source.\n",
        encoding="utf-8",
    )

    preview = migrate_vault(vault, target_version=2)
    assert preview["files_changed"] >= 1

    migrate_vault(vault, target_version=2, apply=True)
    migrated = project.read_text(encoding="utf-8")
    assert "summary: Released the first version." in migrated
    assert "current_focus:" not in migrated
    assert "next_step:" not in migrated
    assert "\noutputs:" not in migrated
    assert "key_outputs:" in migrated
    assert "[[输出/报告/验收报告]]" in migrated
    assert "[[输出/日志/2026-07-10日报]]" not in migrated
    assert "[[知识/来源/2026-07-10-碎碎念]]" in migrated
    assert "## 已完成成果" in migrated
    assert "## 下一步" not in migrated
    assert "Ship another version." not in migrated
    assert "## 证据" in migrated
    assert "![[浏览/项目证据.base]]" in migrated

    second = migrate_vault(vault, target_version=2)
    assert second["files_changed"] == 0


def test_migration_preserves_list_items_containing_colons(tmp_path):
    vault = _make_legacy_vault(tmp_path)
    project = vault / "知识" / "项目" / "demo.md"
    project.write_text(
        "---\nid: project-demo\ntype: project\ntitle: Demo\nstatus: active\n"
        "goal: Preserve links\nsummary: Released.\n"
        "sources: []\ndecisions: []\nconstraints: []\nconcepts: []\nentities: []\n"
        "key_outputs:\n- 'site: https://example.com/'\n- 'repo: owner/project'\n"
        "lifecycle_stage: maintained\n---\n# Demo\n",
        encoding="utf-8",
    )
    migrate_vault(vault, target_version=2, apply=True)
    migrated = project.read_text(encoding="utf-8")

    assert "site: https://example.com/" in migrated
    assert "repo: owner/project" in migrated


def test_v2_compacts_oversized_completed_outcomes(tmp_path):
    vault = _make_legacy_vault(tmp_path)
    project = vault / "知识" / "项目" / "demo.md"
    project.write_text(
        "---\nid: project-demo\ntype: project\ntitle: Demo\nstatus: active\n"
        "goal: Preserve conclusions\nsummary: Released and verified.\n"
        "sources: []\ndecisions: []\nconstraints: []\nconcepts: []\nentities: []\n"
        "key_outputs: []\nlifecycle_stage: maintained\n---\n# Demo\n\n"
        "## 已完成成果\n" + ("- verbose historical detail\n" * 250) + "\n## 证据\n- Source.\n",
        encoding="utf-8",
    )

    migrate_vault(vault, target_version=2, apply=True)
    migrated = project.read_text(encoding="utf-8")

    assert "Released and verified." in migrated
    assert "verbose historical detail" not in migrated
    assert "## 证据" in migrated


def test_v3_adds_human_facing_project_and_knowledge_presentations(tmp_path):
    vault = _make_legacy_vault(tmp_path)
    project = vault / "知识" / "项目" / "demo.md"
    project.write_text(
        "---\nid: project-demo\ntype: project\ntitle: Demo\nstatus: active\n"
        "goal: Preserve outcomes\nsummary: Released and verified.\n"
        "sources: []\ndecisions: []\nconstraints: []\n"
        "concepts:\n  - '[[知识/概念/evidence-first]]'\nentities: []\n"
        "key_outputs: []\nlifecycle_stage: maintained\n---\n# Demo\n\nExisting detail.\n",
        encoding="utf-8",
    )
    concept = vault / "知识" / "概念" / "evidence-first.md"
    concept.parent.mkdir(parents=True)
    concept.write_text(
        "---\nid: concept-evidence-first\ntype: concept\ntitle: Evidence First\n"
        "status: active\nlifecycle_stage: maintained\n"
        "definition: Stable conclusions retain evidence.\n"
        "source_basis: []\nrelated_projects: []\nrelated_concepts: []\n"
        "---\n# Evidence First\n\nExisting explanation.\n",
        encoding="utf-8",
    )
    source = vault / "知识" / "来源" / "2026-07-10-碎碎念.md"
    source.write_text(source.read_text(encoding="utf-8") + "\n[[知识/概念/evidence-first]]\n", encoding="utf-8")
    report = vault / "输出" / "报告" / "guide.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "---\nid: output-guide\ntype: output\ntitle: Guide\nstatus: published\n"
        "lifecycle_stage: maintained\noutput_type: report\ncreated_at: 2026-07-10\n"
        "audience: internal\nproject: []\nderived_from: []\n"
        "concepts:\n  - '[[知识/概念/evidence-first]]'\n---\n# Guide\n",
        encoding="utf-8",
    )

    migrate_vault(vault, target_version=3, apply=True)

    project_text = project.read_text(encoding="utf-8")
    assert "presentation: project-handbook-v1" in project_text
    assert "## 资产与系统地图" in project_text
    assert "## 如何使用或运行" in project_text
    assert "Existing detail." in project_text

    concept_text = concept.read_text(encoding="utf-8")
    assert "presentation: knowledge-compounding-v1" in concept_text
    assert "## 知识生命周期" in concept_text
    assert "| 复利 |" in concept_text
    assert "related_projects:" in concept_text
    assert "[[知识/项目/demo]]" in concept_text
    assert "related_outputs:" in concept_text
    assert "[[输出/报告/guide]]" in concept_text
    assert "feedback_candidates:" in concept_text
    assert "[[知识/来源/2026-07-10-碎碎念]]" in concept_text
    assert "Existing explanation." in concept_text

    second = migrate_vault(vault, target_version=3)
    assert second["files_changed"] == 0
