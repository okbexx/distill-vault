"""Tests for the official MCP SDK server binding."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from distill.mcp_config import verify_codex_mcp_server
from distill.mcp_server import DistillMCPServer, SERVER_NAME


def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    (tmp_path / "知识" / "概念" / "example.md").write_text(
        "---\ntype: concept\ntitle: Example\nstatus: active\n---\n# Example\n",
        encoding="utf-8",
    )
    return tmp_path


def _parameters(vault: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "distill.mcp_server", "--vault", str(vault)],
    )


class TestMCPServerConstruction:
    def test_explicit_vault_root(self, tmp_path):
        vault = _make_vault(tmp_path)
        server = DistillMCPServer(vault_root=vault)
        assert server.vault_root == vault
        assert server.sdk_server.name == SERVER_NAME

    def test_env_var_vault_root(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path)
        monkeypatch.setenv("DISTILL_VAULT", str(vault))
        assert DistillMCPServer().vault_root == vault

    def test_missing_vault_root_raises(self, monkeypatch):
        monkeypatch.delenv("DISTILL_VAULT", raising=False)
        with pytest.raises(ValueError, match="Vault path is required"):
            DistillMCPServer()

    def test_nonexistent_vault_root_raises(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            DistillMCPServer(vault_root=tmp_path / "nope")


def test_official_sdk_lifecycle_and_validation(tmp_path):
    vault = _make_vault(tmp_path)

    async def run() -> None:
        async with stdio_client(_parameters(vault)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == SERVER_NAME

                listed = await session.list_tools()
                tools_by_name = {tool.name: tool for tool in listed.tools}
                names = set(tools_by_name)
                assert {"vault_status", "search", "object_context", "rename"} <= names
                assert tools_by_name["search"].inputSchema["properties"]["limit"]["default"] == 5
                assert tools_by_name["object_context"].inputSchema["properties"]["relation_limit"]["default"] == 12

                status = await session.call_tool("vault_status", arguments={})
                assert status.isError is False
                assert status.structuredContent["vault_root"] == str(vault)
                assert status.structuredContent["stats"]["total_objects"] == 1
                assert isinstance(json.loads(status.content[0].text), dict)

                invalid = await session.call_tool("search", arguments={})
                assert invalid.isError is True
                assert "Input validation error" in invalid.content[0].text

                unknown = await session.call_tool("not_a_tool", arguments={})
                assert unknown.isError is True

    asyncio.run(run())


def test_config_verifier_uses_sdk_client(tmp_path):
    vault = _make_vault(tmp_path)
    result = verify_codex_mcp_server(
        sys.executable,
        ["-m", "distill.mcp_server", "--vault", str(vault)],
        vault,
        timeout=10,
    )
    assert result.ok is True
    assert result.server_name == SERVER_NAME
    assert Path(result.vault_root) == vault
