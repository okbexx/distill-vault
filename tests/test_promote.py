import tempfile
import json
from pathlib import Path

from click.testing import CliRunner

from distill.cli import cli
from distill.promote import PromotionPipeline, apply_promotion, review_promotion


def _make_vault(tmp_path: Path):
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "知识" / "决策").mkdir(parents=True)
    (tmp_path / "知识" / "项目").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


class TestPromotionPipeline:
    def test_no_actions_on_empty_vault(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            pipe = PromotionPipeline(vault)
            pipe.scan()
            actions = pipe.plan()
            assert actions == []

    def test_extract_concept_from_article(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "article.md",
                     "---\ntype: source\ntitle: Article\nsource_type: article\nstatus: linked\n---\n# 框架\n")
            pipe = PromotionPipeline(vault)
            pipe.scan()
            actions = pipe.plan()
            assert any(a["type"] == "extract-concept" for a in actions)

    def test_skip_daily_logs(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "日报.md",
                     "---\ntype: source\ntitle: 日报\nsource_type: daily\nstatus: linked\n---\n# 框架\n")
            pipe = PromotionPipeline(vault)
            pipe.scan()
            actions = pipe.plan()
            assert not any(a["type"] == "extract-concept" for a in actions)
            assert any(a["type"] == "promote-to-output" for a in actions)

    def test_apply_extract_concept(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(vault / "知识" / "来源" / "article.md",
                     "---\ntype: source\ntitle: Article\nsource_type: article\nstatus: linked\n---\n# 框架\n")
            pipe = PromotionPipeline(vault)
            pipe.scan()
            actions = pipe.plan()
            concept_actions = [a for a in actions if a["type"] == "extract-concept"]
            assert len(concept_actions) == 1
            pipe.apply(concept_actions)
            assert (vault / "知识" / "概念" / "article.md").exists()

    def test_auto_plan_only_returns_explicitly_safe_actions(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(Path(td))
            _write_md(
                vault / "知识" / "来源" / "article.md",
                "---\ntype: source\ntitle: Article\nsource_type: article\nstatus: linked\n---\n# 决定采用一个框架\n",
            )
            pipe = PromotionPipeline(vault)
            pipe.scan()

            actions = pipe.plan(auto=True)

            assert all(action["auto_safe"] is True for action in actions)
            assert not any(action["type"].startswith("extract-") for action in actions)


def _concept_proposal() -> str:
    return """---
id: concept-evidence-first
type: concept
title: Evidence First
status: active
lifecycle_stage: promoted
definition: Stable conclusions should retain inspectable evidence.
source_basis:
  - "[[知识/来源/article]]"
related_projects: []
related_concepts: []
---
# Evidence First

Stable conclusions should retain inspectable evidence.
"""


def test_semantic_promotion_review_and_apply_updates_source_backlink(tmp_path):
    vault = _make_vault(tmp_path)
    _write_md(
        vault / "知识" / "来源" / "article.md",
        "---\ntype: source\ntitle: Article\nsource_type: article\nstatus: linked\n---\nEvidence.\n",
    )

    review = review_promotion(
        vault,
        source="知识/来源/article.md",
        target="知识/概念/Evidence First.md",
        content=_concept_proposal(),
    )

    assert review["status"] == "ready"
    assert review["requires_confirmation"] is True
    assert review["touched_paths"] == ["知识/来源/article.md", "知识/概念/Evidence First.md"]

    applied = apply_promotion(
        vault,
        source="知识/来源/article.md",
        target="知识/概念/Evidence First.md",
        content=_concept_proposal(),
    )

    assert applied["status"] == "applied"
    assert (vault / "知识" / "概念" / "Evidence First.md").exists()
    source = (vault / "知识" / "来源" / "article.md").read_text(encoding="utf-8")
    assert "[[知识/概念/Evidence First]]" in source


def test_semantic_promotion_review_blocks_duplicate_title(tmp_path):
    vault = _make_vault(tmp_path)
    _write_md(
        vault / "知识" / "来源" / "article.md",
        "---\ntype: source\ntitle: Article\nsource_type: article\nstatus: linked\n---\nEvidence.\n",
    )
    _write_md(
        vault / "知识" / "概念" / "existing.md",
        "---\nid: concept-existing\ntype: concept\ntitle: Evidence First\nstatus: active\n---\nExisting.\n",
    )

    review = review_promotion(
        vault,
        source="知识/来源/article.md",
        target="知识/概念/Evidence First.md",
        content=_concept_proposal(),
    )

    assert review["status"] == "blocked"
    assert review["duplicate_paths"] == ["知识/概念/existing.md"]


def test_cli_semantic_promotion_reviews_then_applies(tmp_path):
    vault = _make_vault(tmp_path)
    _write_md(
        vault / "知识" / "来源" / "article.md",
        "---\ntype: source\ntitle: Article\nsource_type: article\nstatus: linked\n---\nEvidence.\n",
    )
    runner = CliRunner()
    base_args = [
        "--vault",
        str(vault),
        "promote",
        "--source",
        "知识/来源/article.md",
        "--target",
        "知识/概念/Evidence First.md",
        "--format",
        "json",
    ]

    reviewed = runner.invoke(cli, base_args, input=_concept_proposal())
    assert reviewed.exit_code == 0, reviewed.output
    assert json.loads(reviewed.output)["status"] == "ready"
    assert not (vault / "知识" / "概念" / "Evidence First.md").exists()

    applied = runner.invoke(cli, [*base_args, "--apply-proposal"], input=_concept_proposal())
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "applied"
    assert (vault / "知识" / "概念" / "Evidence First.md").exists()
