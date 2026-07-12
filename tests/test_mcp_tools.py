"""Tests for MCP tool registry and handler layer (mcp_tools.py).

Covers: tool registration, schema validation, call_tool dispatch, error handling,
and individual tool handler behavior with a real vault.
"""

import tempfile
from pathlib import Path

import pytest

from distill.mcp_tools import DistillMCPTools, MCPTool, MCPToolError
from distill.routing import route_intent, route_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    return tmp_path


def _write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_populated_vault(tmp_path: Path) -> Path:
    """Create a vault with several interlinked objects."""
    vault = _make_vault(tmp_path)
    (vault / "知识" / "项目").mkdir(parents=True)
    _write_md(
        vault / "知识" / "项目" / "激光雷达.md",
        "---\ntype: project\ntitle: 激光雷达\nstatus: active\n---\n# 激光雷达\n",
    )
    _write_md(
        vault / "知识" / "概念" / "python.md",
        "---\ntype: concept\ntitle: Python\nstatus: active\n---\n# Python\nA programming language.",
    )
    _write_md(
        vault / "知识" / "概念" / "rust.md",
        "---\ntype: concept\ntitle: Rust\nstatus: active\n---\n# Rust\n[[Python]] is also popular.",
    )
    _write_md(
        vault / "知识" / "来源" / "article.md",
        "---\ntype: source\ntitle: Article\nstatus: linked\n---\n[[Python]] and [[Rust]] comparison.",
    )
    _write_md(
        vault / "输出" / "report.md",
        "---\ntype: output\ntitle: Report\nstatus: published\nconcepts: [Python]\n---\n",
    )
    return vault


@pytest.fixture
def empty_vault(tmp_path):
    return _make_vault(tmp_path)


@pytest.fixture
def populated_vault(tmp_path):
    return _make_populated_vault(tmp_path)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_list_tools_returns_all_registered(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        schemas = tools.list_tools()
        assert len(schemas) >= 10
        names = [s["name"] for s in schemas]
        # Verify expected tools are present
        for expected in [
            "vault_status", "vault_staleness", "search", "cypher_query",
            "object_context", "list_objects", "impact_upstream", "impact_downstream",
            "detect_changes", "community_detect", "community_info", "rename",
            "lint_check", "lint_fix", "pipeline_run", "pipeline_status",
            "projection_route", "projection_plan", "projection_apply",
            "promotion_review", "promotion_apply",
        ]:
            assert expected in names, f"Missing tool: {expected}"

    def test_each_tool_has_required_schema_fields(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        for schema in tools.list_tools():
            assert "name" in schema
            assert "description" in schema
            assert "inputSchema" in schema
            assert schema["inputSchema"]["type"] == "object"

    def test_mcp_tool_as_schema(self):
        tool = MCPTool(
            name="test_tool",
            description="A test",
            input_schema={"type": "object", "properties": {}},
            handler=lambda: {},
        )
        schema = tool.as_schema()
        assert schema["name"] == "test_tool"
        assert "inputSchema" in schema


# ---------------------------------------------------------------------------
# call_tool dispatch & error handling
# ---------------------------------------------------------------------------

class TestCallToolDispatch:
    def test_unknown_tool_raises(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        with pytest.raises(MCPToolError, match="Unknown tool"):
            tools.call_tool("nonexistent")

    def test_invalid_arguments_raises(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        with pytest.raises(MCPToolError, match="Invalid arguments"):
            tools.call_tool("search", {"nonexistent_param": 42})

    def test_call_tool_passes_arguments(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.call_tool("search", {"query": "Python", "limit": 5})
        assert isinstance(result, dict)
        assert "results" in result

    def test_mcp_tool_error_is_exception(self):
        assert issubclass(MCPToolError, Exception)


# ---------------------------------------------------------------------------
# Discovery tools
# ---------------------------------------------------------------------------

class TestVaultStatus:
    def test_empty_vault_status(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        result = tools.vault_status()
        assert "vault_root" in result
        assert result["vault_root"] == str(empty_vault.resolve())
        assert "stats" in result
        assert "health" in result
        assert "next_steps" in result
        assert result["runtime_stage"] == "preflight"
        assert result["has_checkpoint"] is False
        assert result["scan_roots"]
        assert result["vault_layout"]["knowledge_dirs"]

    def test_populated_vault_has_objects(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.vault_status()
        assert result["stats"]["total_objects"] >= 4

    def test_health_classification_healthy(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.vault_status()
        health = result["health"]
        assert health["level"] in ("healthy", "warning", "critical")
        assert "reason" in health
        assert "signals" in health
        assert "broken_links" in health
        assert "orphan_objects" in health
        assert "true_orphans" in health
        assert "system_docs" in health

    def test_health_summary_ignores_system_doc_orphans_for_level(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        health = tools._health_summary({
            "broken_links": 0,
            "orphan_objects": 18,
            "true_orphans": 0,
            "system_docs": 18,
        })
        assert health["level"] == "healthy"
        assert health["reason"] == "clean_runtime"
        assert health["signals"]["system_docs"] == 18
        assert health["true_orphans"] == 0
        assert health["system_docs"] == 18


class TestVaultStaleness:
    def test_staleness_on_fresh_vault(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.vault_staleness()
        assert isinstance(result, dict)

    def test_staleness_on_fresh_vault_has_consistent_shape(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.vault_staleness()
        assert result == {
            "stale": True,
            "reason": "no_checkpoint",
            "added": 0,
            "removed": 0,
            "modified": 0,
            "total_changes": 0,
            "last_index_time": 0,
        }


class TestProjectionRoute:
    def test_projection_route_returns_same_plan_as_shared_planner(self, populated_vault, monkeypatch):
        monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
        tools = DistillMCPTools(populated_vault)

        result = tools.projection_route(intent="记录一下激光雷达今天进展，UAT已发布")
        expected = route_intent(populated_vault, "记录一下激光雷达今天进展，UAT已发布")

        assert result == expected
        assert result["operation"] == "fact_capture"
        assert result["write_paths"] == [
            "知识/来源/2026-05-12-碎碎念.md",
            "知识/项目/激光雷达.md",
        ]

    def test_projection_route_warns_when_project_is_missing(self, populated_vault, monkeypatch):
        monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
        tools = DistillMCPTools(populated_vault)

        result = tools.call_tool("projection_route", {"intent": "记录一下今天进展"})

        assert result["operation"] == "generic_update"
        assert result["warnings"]
        assert "action" not in result
        assert "status" not in result


class TestProjectionPlan:
    def test_projection_plan_returns_same_plan_as_shared_planner(self, populated_vault, monkeypatch):
        monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
        tools = DistillMCPTools(populated_vault)

        result = tools.call_tool("projection_plan", {"intent": "记录一下激光雷达今天进展，UAT已发布"})
        expected = route_plan(populated_vault, "记录一下激光雷达今天进展，UAT已发布")

        assert result == expected
        assert result["action"] == "knowledge_capture"
        assert result["status"] == "planned"
        assert result["recommended_commit_message"] == "知识库: 记录激光雷达成果"


class TestProjectionApply:
    def test_projection_apply_writes_source_and_project(self, populated_vault, monkeypatch):
        monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
        tools = DistillMCPTools(populated_vault)

        result = tools.call_tool("projection_apply", {"intent": "记录一下激光雷达今天进展，UAT已发布"})

        assert result["action"] == "knowledge_capture"
        assert result["status"] == "applied"
        assert result["operation"] == "fact_capture"
        assert result["touched_paths"] == [
            "知识/来源/2026-05-12-碎碎念.md",
            "知识/项目/激光雷达.md",
        ]
        assert result["recommended_commit_paths"] == result["touched_paths"]
        assert result["recommended_commit_message"] == "知识库: 记录激光雷达成果"
        assert "--skip-run" in result["recommended_commit_command"]
        source_text = (populated_vault / "知识" / "来源" / "2026-05-12-碎碎念.md").read_text(encoding="utf-8")
        project_text = (populated_vault / "知识" / "项目" / "激光雷达.md").read_text(encoding="utf-8")
        assert "UAT已发布" in source_text
        assert "summary:" not in project_text
        assert "- 2026-05-12: 记录一下激光雷达今天进展，UAT已发布" in project_text
        assert "current_focus:" not in project_text

    def test_projection_apply_raises_for_ambiguous_route(self, populated_vault, monkeypatch):
        monkeypatch.setattr("distill.routing._today_iso", lambda: "2026-05-12")
        tools = DistillMCPTools(populated_vault)

        with pytest.raises(MCPToolError, match="No matching project object found"):
            tools.call_tool("projection_apply", {"intent": "记录一下今天进展"})


class TestPromotionProposal:
    def test_review_and_apply_semantic_promotion(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        content = """---
id: concept-evidence-first
type: concept
title: Evidence First
status: active
lifecycle_stage: promoted
definition: Stable conclusions retain evidence.
source_basis:
  - "[[知识/来源/article]]"
related_projects: []
related_concepts: []
---
# Evidence First

Stable conclusions retain evidence.
"""
        arguments = {
            "source": "知识/来源/article.md",
            "target": "知识/概念/Evidence First.md",
            "content": content,
        }

        reviewed = tools.call_tool("promotion_review", arguments)
        assert reviewed["status"] == "ready"

        applied = tools.call_tool("promotion_apply", arguments)
        assert applied["status"] == "applied"
        assert (populated_vault / "知识" / "概念" / "Evidence First.md").exists()


# ---------------------------------------------------------------------------
# Query tools
# ---------------------------------------------------------------------------

class TestSearchTool:
    def test_search_returns_results(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.search(query="Python")
        assert "results" in result
        assert result["query"] == "Python"
        assert result["total"] >= 1

    def test_search_with_limit(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.search(query="Python", limit=1)
        assert result["limit"] == 1
        assert len(result["results"]) <= 1

    def test_search_modes(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        for mode in ("keyword", "semantic", "hybrid"):
            result = tools.search(query="Python", mode=mode)
            assert result["mode"] == mode

    def test_search_no_results(self, empty_vault):
        tools = DistillMCPTools(empty_vault)
        result = tools.search(query="nonexistent_xyz")
        assert result["total"] == 0


class TestCypherQuery:
    def test_simple_cypher(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.cypher_query(query="MATCH (n) RETURN count(n)")
        assert "rows" in result
        assert result["row_count"] == 1

    def test_cypher_with_rebuild(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.cypher_query(query="MATCH (n) RETURN count(n)", rebuild=True)
        assert result["row_count"] == 1


class TestListObjects:
    def test_list_all(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.list_objects()
        assert result["total"] >= 4
        assert len(result["items"]) >= 4

    def test_filter_by_type(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.list_objects(obj_type="concept")
        for item in result["items"]:
            assert item["type"] == "concept"

    def test_filter_by_status(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.list_objects(status="active")
        for item in result["items"]:
            assert item["status"] == "active"

    def test_pagination(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.list_objects(limit=2, offset=0)
        assert len(result["items"]) <= 2
        assert result["limit"] == 2
        assert result["offset"] == 0


class TestObjectContext:
    def test_object_context_by_path(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.object_context(path="知识/概念/python.md")
        assert "object" in result
        assert "incoming" in result
        assert "outgoing" in result
        assert "relation_counts" in result
        assert "truncated" in result
        assert "communities" in result

    def test_object_context_limits_relations_and_reports_truncation(self, populated_vault):
        tools = DistillMCPTools(populated_vault)

        result = tools.object_context(path="Python", relation_limit=1)

        assert len(result["incoming"]) == 1
        assert result["relation_counts"]["incoming"] > 1
        assert result["truncated"]["incoming"] is True

    def test_object_context_by_title(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.object_context(path="Python")
        assert result["object"]["title"] == "Python"

    def test_object_not_found_raises(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        with pytest.raises(MCPToolError, match="Object not found"):
            tools.object_context(path="Nonexistent")

    def test_rust_has_incoming_from_python(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.object_context(path="知识/概念/rust.md")
        # Rust -> Python is an outgoing link
        outgoing_paths = [link["path"] for link in result["outgoing"]]
        assert any("python" in p.lower() for p in outgoing_paths)


# ---------------------------------------------------------------------------
# Analysis tools
# ---------------------------------------------------------------------------

class TestImpactAnalysis:
    def test_impact_upstream(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.impact_upstream(target="知识/概念/python.md")
        assert isinstance(result, dict)

    def test_impact_downstream(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.impact_downstream(target="知识/概念/python.md")
        assert isinstance(result, dict)

    def test_impact_with_max_depth(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.impact_upstream(target="Python", max_depth=1)
        assert isinstance(result, dict)

    def test_impact_target_not_found_raises(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        with pytest.raises(MCPToolError, match="Object not found"):
            tools.impact_upstream(target="NonexistentThing")


class TestDetectChanges:
    def test_detect_changes_with_file(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.detect_changes(changed_files=["知识/概念/python.md"])
        assert isinstance(result, dict)

    def test_detect_changes_empty_list(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.detect_changes(changed_files=[])
        assert isinstance(result, dict)


class TestCommunityTools:
    def test_community_detect(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.community_detect(persist=False)
        assert isinstance(result, dict)

    def test_community_info_all(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        # Run detect first to ensure communities exist
        tools.community_detect(persist=True)
        result = tools.community_info()
        assert isinstance(result, dict)

    def test_community_info_not_found(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        # Ensure community data exists first
        tools.community_detect(persist=True)
        with pytest.raises(MCPToolError, match="Community not found"):
            tools.community_info(community_id="nonexistent-xyz")


# ---------------------------------------------------------------------------
# Action tools
# ---------------------------------------------------------------------------

class TestRenameTool:
    def test_rename_preview(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.rename(old_name="Python", new_name="PythonLang")
        assert result["old_name"] == "Python"
        assert result["new_name"] == "PythonLang"
        assert result["apply"] is False
        # Preview should NOT modify files
        content = (populated_vault / "知识" / "概念" / "python.md").read_text(encoding="utf-8")
        assert "title: Python\n" in content

    def test_rename_apply_modifies_files(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.rename(old_name="Python", new_name="PythonLang", apply=True)
        assert result["apply"] is True
        assert result["total_changed"] >= 1
        # Verify the title was changed
        content = (populated_vault / "知识" / "概念" / "python.md").read_text(encoding="utf-8")
        assert "title: PythonLang" in content

    def test_rename_nonexistent_title_raises(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        with pytest.raises(MCPToolError, match="Object title not found"):
            tools.rename(old_name="DoesNotExist", new_name="NewName")


class TestLintTools:
    def test_lint_check(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.lint_check()
        assert "issue_count" in result
        assert "issues" in result
        assert "next_steps" in result
        assert "runtime_stage" in result
        assert "scan_roots" in result
        assert "vault_layout" in result

    def test_lint_fix(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.lint_fix()
        assert "issue_count" in result
        assert "fix_report" in result
        assert "next_steps" in result
        assert "runtime_stage" in result
        assert "scan_roots" in result


class TestPipelineTools:
    def test_pipeline_run(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.pipeline_run()
        assert "results" in result
        assert "report" in result
        assert "worker_pool" in result
        assert result["worker_pool"]["requested_mode"] == "auto"
        expected_mode = "serial" if result["worker_pool"]["workers"] <= 1 else "thread"
        assert result["worker_pool"]["last_mode"] == expected_mode
        assert result["worker_pool"]["fallback_used"] is False
        assert result["worker_pool"]["fallback_reason"] is None
        assert "scan" in result["worker_pool"]["phases"]
        assert "parse" in result["worker_pool"]["phases"]
        assert result["worker_pool"]["phases"]["scan"]["last_mode"] == expected_mode
        assert result["worker_pool"]["phases"]["parse"]["last_mode"] == expected_mode

    def test_pipeline_run_uses_main_six_phase_pipeline(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.pipeline_run()
        assert list(result["results"].keys()) == [
            "scan",
            "parse",
            "graph",
            "analyze",
            "promote",
            "export",
        ]
        assert "✓ scan" in result["report"]
        assert "✓ export" in result["report"]

    def test_pipeline_run_reports_scanned_objects(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools.pipeline_run()
        assert result["results"]["scan"]["objects"] >= 4
        assert result["results"]["parse"]["objects"] >= 4

    def test_pipeline_status(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        # Run first to create checkpoint
        tools.pipeline_run()
        result = tools.pipeline_status()
        assert "checkpoint" in result
        assert "staleness" in result
        assert "report" in result
        assert "worker_pool" in result
        assert result["worker_pool"]["requested_mode"] == "auto"
        expected_mode = "serial" if result["worker_pool"]["workers"] <= 1 else "thread"
        assert result["worker_pool"]["last_mode"] == expected_mode
        assert result["worker_pool"]["fallback_used"] is False
        assert result["worker_pool"]["fallback_reason"] is None
        assert result["worker_pool"]["phases"]["scan"]["last_mode"] == expected_mode
        assert result["worker_pool"]["phases"]["parse"]["last_mode"] == expected_mode

    def test_pipeline_status_reports_checkpoint_summary(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        tools.pipeline_run()
        result = tools.pipeline_status()
        assert result["staleness"]["stale"] is False
        assert list(result["checkpoint"]["phases"].keys()) == [
            "analyze",
            "export",
            "graph",
            "parse",
            "promote",
            "scan",
        ]
        assert result["checkpoint"]["phases"]["scan"]["objects"] >= 4
        assert result["checkpoint"]["phases"]["export"]["objects"] == 2
        assert "scan" in result["report"]
        assert "promote" in result["report"]
        assert "export" in result["report"]

    def test_pipeline_status_uses_checkpoint_summary_when_no_live_run_state(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        tools.pipeline_run()
        result = tools.pipeline_status()

        assert "Pipeline Checkpoint Summary" in result["report"]
        assert "checkpoint" in result["report"]


# ---------------------------------------------------------------------------
# Path normalization & escaping helpers
# ---------------------------------------------------------------------------

class TestPathNormalization:
    def test_normalize_by_exact_path(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools._normalize_object_path("知识/概念/python.md", tools._make_index())
        assert result == "知识/概念/python.md"

    def test_normalize_by_title(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools._normalize_object_path("Python", tools._make_index())
        assert result == "知识/概念/python.md"

    def test_normalize_with_md_suffix(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools._normalize_object_path("知识/概念/python", tools._make_index())
        assert result == "知识/概念/python.md"

    def test_normalize_strict_not_found_raises(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        with pytest.raises(MCPToolError):
            tools._normalize_object_path("nonexistent", tools._make_index(), strict=True)

    def test_normalize_non_strict_returns_as_is(self, populated_vault):
        tools = DistillMCPTools(populated_vault)
        result = tools._normalize_object_path("nonexistent", tools._make_index(), strict=False)
        assert result == "nonexistent"
