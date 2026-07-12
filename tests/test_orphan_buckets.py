from pathlib import Path

from distill.index import VaultIndex
from distill.vault_semantics import classify_orphan_path


def _write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_classify_orphan_path_system_docs():
    assert classify_orphan_path("系统/规范/对象类型.md") == "system_doc"
    assert classify_orphan_path("系统/运行时/codex/AGENTS.md") == "system_doc"
    assert classify_orphan_path("系统/技能/promote-knowledge.md") == "system_doc"
    assert classify_orphan_path("system/runtime/claude/CLAUDE.md") == "system_doc"
    assert classify_orphan_path("system/skills/promote-knowledge.md") == "system_doc"
    assert classify_orphan_path(
        "输出/日志/2026-07-11日报.md",
        {"type": "output", "output_type": "log"},
    ) == "timeline_archive"
    assert classify_orphan_path("notes/random.md") == "true_orphan"


def test_index_buckets_orphans_for_system_docs(tmp_path: Path):
    _write_md(tmp_path / "系统" / "规范" / "对象类型.md", "# 对象类型")
    _write_md(tmp_path / "系统" / "运行时" / "codex" / "AGENTS.md", "# AGENTS")
    _write_md(tmp_path / "系统" / "技能" / "promote-knowledge.md", "# skill")
    _write_md(tmp_path / "知识" / "来源" / "lonely.md", "---\ntype: source\ntitle: Lonely\nstatus: linked\n---\n")

    idx = VaultIndex(tmp_path)
    idx.scan()

    assert "知识/来源/lonely.md" in idx.orphan_buckets["true_orphan"]
    assert "系统/规范/对象类型.md" in idx.orphan_buckets["system_doc"]
    assert "系统/运行时/codex/AGENTS.md" in idx.orphan_buckets["system_doc"]
    assert "系统/技能/promote-knowledge.md" in idx.orphan_buckets["system_doc"]
    assert idx.stats["true_orphans"] == 1
    assert idx.stats["system_docs"] == 3


def test_system_skill_orphans_do_not_downgrade_runtime_stage(tmp_path: Path):
    _write_md(tmp_path / ".distill" / "checkpoint.json", "{}")
    _write_md(tmp_path / "系统" / "技能" / "compose-output.md", "# skill")

    idx = VaultIndex(tmp_path)
    idx.scan()

    assert idx.stats["true_orphans"] == 0
    assert idx.stats["system_docs"] == 1
    assert idx.runtime_stage() == "trusted_runtime"


def test_timeline_archive_orphans_do_not_downgrade_runtime_stage(tmp_path: Path):
    _write_md(tmp_path / ".distill" / "checkpoint.json", "{}")
    _write_md(
        tmp_path / "输出" / "日志" / "2026-07-11日报.md",
        "---\ntype: output\ntitle: 2026-07-11 日报\noutput_type: log\n---\n",
    )

    idx = VaultIndex(tmp_path)
    idx.scan()

    assert idx.orphan_buckets["timeline_archive"] == ["输出/日志/2026-07-11日报.md"]
    assert idx.stats["true_orphans"] == 0
    assert idx.stats["timeline_archives"] == 1
    assert idx.runtime_stage() == "trusted_runtime"
