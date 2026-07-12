import json
from pathlib import Path
import tempfile

import pytest

from distill.vault_semantics import (
    FRONTMATTER_RELATION_FIELDS,
    build_lookup_indexes,
    extract_frontmatter_links,
    extract_wikilinks,
    normalize_wikilink_target,
    resolve_existing_vault_asset,
    resolve_link_target,
)


def test_extract_wikilinks_normalizes_aliases():
    text = "See [[Foo|别名]] and [[知识/概念/bar]]."

    assert extract_wikilinks(text) == ["Foo", "知识/概念/bar"]


def test_extract_frontmatter_links_supports_nested_lists_and_known_relation_fields():
    metadata = {
        "concepts": ["[[Foo]]", ["[[Bar|显示名]]"]],
        "constraints": "[[Latency Budget]]",
        "ignored": ["[[Nope]]"],
    }

    assert extract_frontmatter_links(metadata, include_plain_strings=True) == ["Foo", "Bar", "Latency Budget"]


def test_plain_relation_extraction_ignores_operational_labels_and_prose():
    metadata = {
        "outputs": ["源码: /tmp/repo", "npm: @scope/package", "知识/项目/Demo"],
        "decisions": ["2026-07-10：暂缓发布，等待明确恢复。", "Ship Decision"],
    }
    assert extract_frontmatter_links(metadata, include_plain_strings=True) == [
        "知识/项目/Demo",
        "Ship Decision",
    ]
    assert "constraints" in FRONTMATTER_RELATION_FIELDS
    assert "key_outputs" in FRONTMATTER_RELATION_FIELDS


def test_resolve_link_target_prefers_title_then_path_then_prefix_and_filename():
    objects = [
        {"path": "知识/概念/foo.md", "title": "Foo"},
        {"path": "knowledge/concepts/latency-budget.md", "title": "Latency Budget"},
    ]
    path_index, title_index, filename_index = build_lookup_indexes(objects)

    assert resolve_link_target("Foo", path_index=path_index, title_index=title_index, relation_prefixes=[], filename_index=filename_index) == "知识/概念/foo.md"
    assert resolve_link_target("知识/概念/foo", path_index=path_index, title_index=title_index, relation_prefixes=[], filename_index=filename_index) == "知识/概念/foo.md"
    assert resolve_link_target("latency-budget", path_index=path_index, title_index=title_index, relation_prefixes=["knowledge/concepts"], filename_index=filename_index) == "knowledge/concepts/latency-budget.md"


def test_resolve_link_target_returns_none_for_unknown_target():
    path_index, title_index, filename_index = build_lookup_indexes([])

    assert resolve_link_target("Missing", path_index=path_index, title_index=title_index, relation_prefixes=[], filename_index=filename_index) is None


def test_resolve_existing_vault_asset_only_accepts_existing_base_files(tmp_path: Path):
    base = tmp_path / "浏览" / "项目证据.base"
    base.parent.mkdir(parents=True)
    base.write_text("views: []\n", encoding="utf-8")

    assert resolve_existing_vault_asset("浏览/项目证据.base", tmp_path) == "浏览/项目证据.base"
    assert resolve_existing_vault_asset("浏览/缺失.base", tmp_path) is None
    assert resolve_existing_vault_asset("../项目证据.base", tmp_path) is None
    assert resolve_existing_vault_asset("浏览/普通.md", tmp_path) is None
