from pathlib import Path

from distill.config import get_scan_dirs, load_config
from distill.index import VaultIndex
from distill.promote import PromotionPipeline


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_get_scan_dirs_prunes_nested_dirs(tmp_path):
    (tmp_path / "输出").mkdir()
    (tmp_path / "运维").mkdir()
    (tmp_path / "系统").mkdir()
    (tmp_path / "distill.yaml").write_text(
        "vault:\n  knowledge_dirs:\n    - .\n  output_dirs:\n    - 输出\n  ops_dirs:\n    - 运维\n  system_dirs:\n    - 系统\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)
    scan_dirs = get_scan_dirs(config, tmp_path)

    assert scan_dirs == [tmp_path]


def test_vault_index_does_not_double_count_when_root_and_output_overlap(tmp_path):
    _write_md(
        tmp_path / "idea.md",
        "---\ntype: concept\ntitle: Idea\nstatus: active\n---\n",
    )
    _write_md(
        tmp_path / "输出" / "report.md",
        "---\ntype: output\ntitle: Report\nstatus: draft\n---\n",
    )
    (tmp_path / "运维").mkdir()
    (tmp_path / "distill.yaml").write_text(
        "vault:\n  knowledge_dirs:\n    - .\n  output_dirs:\n    - 输出\n  ops_dirs:\n    - 运维\n  system_dirs: []\n",
        encoding="utf-8",
    )

    idx = VaultIndex(tmp_path)
    idx.scan()

    assert idx.stats["total_objects"] == 2


def test_promotion_pipeline_falls_back_when_directory_lists_are_empty(tmp_path):
    _write_md(
        tmp_path / "知识" / "来源" / "source.md",
        "---\ntype: source\ntitle: Source\nstatus: linked\nsource_type: article\n---\n这是一个概念定义与方法说明。\n",
    )
    (tmp_path / "distill.yaml").write_text(
        "vault:\n  knowledge_dirs: []\n  output_dirs: []\n  ops_dirs:\n    - .distill\n  system_dirs: []\n",
        encoding="utf-8",
    )

    pipe = PromotionPipeline(tmp_path)
    pipe.scan()
    actions = pipe.plan()

    assert actions
    assert actions[0]["target"].startswith("知识/")
