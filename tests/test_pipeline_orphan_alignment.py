import tempfile
from pathlib import Path

from distill.phases import build_pipeline


def _write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_pipeline_orphan_semantics_match_index_for_system_docs():
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / "知识" / "来源").mkdir(parents=True)
        (vault / "系统" / "规范").mkdir(parents=True)
        (vault / "系统" / "运行时" / "codex").mkdir(parents=True)
        (vault / "输出" / "日志").mkdir(parents=True)

        _write_md(vault / "知识" / "来源" / "lonely.md", "---\ntype: source\ntitle: Lonely\nstatus: linked\n---\n")
        _write_md(vault / "系统" / "规范" / "对象类型.md", "# 对象类型")
        _write_md(vault / "系统" / "运行时" / "codex" / "AGENTS.md", "# AGENTS")
        _write_md(
            vault / "输出" / "日志" / "daily.md",
            "---\ntype: output\ntitle: Daily\noutput_type: log\n---\n",
        )

        dag = build_pipeline(vault)
        dag.run()

        orphans = {row[0] for row in dag.ctx.get("orphans", [])}
        assert orphans == {
            "知识/来源/lonely.md",
            "系统/规范/对象类型.md",
            "系统/运行时/codex/AGENTS.md",
            "输出/日志/daily.md",
        }

        buckets = dag.ctx.get("orphan_buckets", {})
        assert {row[0] for row in buckets.get("true_orphan", [])} == {"知识/来源/lonely.md"}
        assert {row[0] for row in buckets.get("system_doc", [])} == {
            "系统/规范/对象类型.md",
            "系统/运行时/codex/AGENTS.md",
        }
        assert {row[0] for row in buckets.get("timeline_archive", [])} == {"输出/日志/daily.md"}
