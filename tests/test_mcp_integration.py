"""End-to-end Distill tool calls through the official MCP SDK transport."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path
    _write_md(
        vault / "知识" / "概念" / "distributed-systems.md",
        "---\ntype: concept\ntitle: Distributed Systems\nstatus: active\n---\n"
        "# Distributed Systems\n[[Consensus]], [[CAP Theorem]], and [[Vector Clocks]].",
    )
    _write_md(
        vault / "知识" / "概念" / "consensus.md",
        "---\ntype: concept\ntitle: Consensus\nstatus: active\n---\n"
        "# Consensus\nRelated to [[Distributed Systems]].",
    )
    _write_md(
        vault / "知识" / "概念" / "cap-theorem.md",
        "---\ntype: concept\ntitle: CAP Theorem\nstatus: active\n---\n# CAP Theorem\n",
    )
    _write_md(
        vault / "知识" / "概念" / "vector-clocks.md",
        "---\ntype: concept\ntitle: Vector Clocks\nstatus: active\n---\n"
        "# Vector Clocks\nUsed in [[Distributed Systems]].",
    )
    _write_md(
        vault / "知识" / "来源" / "paper.md",
        "---\ntype: source\ntitle: Raft Paper\nstatus: linked\n---\n[[Consensus]] paper.",
    )
    _write_md(
        vault / "输出" / "report.md",
        "---\ntype: output\ntitle: Systems Report\nstatus: published\nconcepts: [Consensus]\n---\n",
    )
    (vault / "运维" / "索引").mkdir(parents=True)
    (vault / "运维" / "健康检查").mkdir(parents=True)
    return vault


def _parameters(vault: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "distill.mcp_server", "--vault", str(vault)],
    )


def test_query_analysis_lint_and_pipeline_over_sdk(tmp_path):
    vault = _make_vault(tmp_path)

    async def run() -> None:
        async with stdio_client(_parameters(vault)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                search = await session.call_tool("search", {"query": "Consensus"})
                assert search.isError is False
                assert search.structuredContent["total"] >= 1

                context = await session.call_tool("object_context", {"path": "Consensus"})
                assert context.isError is False
                assert context.structuredContent["object"]["title"] == "Consensus"
                assert context.structuredContent["outgoing"]

                impact = await session.call_tool(
                    "impact_upstream",
                    {"target": "Consensus", "max_depth": 2},
                )
                assert impact.isError is False
                assert isinstance(impact.structuredContent, dict)

                legacy = await session.call_tool(
                    "cypher_query",
                    {"query": "MATCH (n) RETURN count(n)"},
                )
                assert legacy.isError is False
                assert legacy.structuredContent["deprecated"] is True
                assert legacy.structuredContent["rows"][0][0] >= 6

                lint = await session.call_tool("lint_check", {})
                assert lint.isError is False
                assert "issue_count" in lint.structuredContent

                pipeline = await session.call_tool("pipeline_run", {})
                assert pipeline.isError is False
                assert list(pipeline.structuredContent["results"]) == [
                    "scan",
                    "parse",
                    "graph",
                    "analyze",
                    "promote",
                    "export",
                ]

    asyncio.run(run())


def test_rename_preview_and_apply_over_sdk(tmp_path):
    vault = _make_vault(tmp_path)

    async def run() -> None:
        async with stdio_client(_parameters(vault)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                preview = await session.call_tool(
                    "rename",
                    {"old_name": "Consensus", "new_name": "ConsensusProtocol"},
                )
                assert preview.isError is False
                assert preview.structuredContent["apply"] is False

                applied = await session.call_tool(
                    "rename",
                    {
                        "old_name": "Consensus",
                        "new_name": "ConsensusProtocol",
                        "apply": True,
                    },
                )
                assert applied.isError is False
                assert applied.structuredContent["total_changed"] >= 1

    asyncio.run(run())
    content = (vault / "知识" / "概念" / "consensus.md").read_text(encoding="utf-8")
    assert "title: ConsensusProtocol" in content
