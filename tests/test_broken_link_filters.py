from pathlib import Path

from distill.index import VaultIndex
from distill.vault_semantics import should_ignore_broken_link


def _write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_should_ignore_broken_link_for_pseudo_and_compat_targets():
    assert should_ignore_broken_link("GitHub: okbexx/distill-vault") is True
    assert should_ignore_broken_link("站点: https://okbexx.github.io/") is True
    assert should_ignore_broken_link("报告: ~/tech-knockout/reports/") is True
    assert should_ignore_broken_link("横评: ~/tech-knockout/comparisons/") is True
    assert should_ignore_broken_link("学习卡片: ~/build-your-own-x-learning/day-01") is True
    assert should_ignore_broken_link("兼容层/日报/2026-04/2026-04-07") is True
    assert should_ignore_broken_link("输出/报告/demo.html") is True
    assert should_ignore_broken_link("assets/cover.png") is True
    assert should_ignore_broken_link("真实缺失对象") is False


def test_index_skips_pseudo_and_compat_broken_links(tmp_path: Path):
    _write_md(
        tmp_path / "知识" / "项目" / "demo.md",
        """---
type: project
title: Demo
status: active
outputs:
  - \"GitHub: okbexx/distill-vault\"
  - \"站点: https://okbexx.github.io/\"
  - \"报告: ~/tech-knockout/reports/\"
  - \"横评: ~/tech-knockout/comparisons/\"
  - \"学习卡片: ~/build-your-own-x-learning/day-01\"
---
[[兼容层/日报/2026-04/2026-04-07]]
[[Missing]]
""",
    )

    idx = VaultIndex(tmp_path)
    idx.scan()

    assert {item["to"] for item in idx.broken_links} == {"Missing"}
