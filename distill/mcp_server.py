"""Official MCP SDK server for distill-vault over stdio."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any, Optional

import mcp.server.stdio
import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import __version__
from .mcp_tools import DistillMCPTools


SERVER_NAME = "distill-vault-mcp"
SERVER_INSTRUCTIONS = (
    "Use tools/list to discover distill-vault capabilities. Prefer typed graph "
    "tools; cypher_query is a deprecated, limited read-only compatibility tool."
)


class DistillMCPServer:
    """Bind the Distill tool registry to the official MCP low-level server."""

    def __init__(self, vault_root: Optional[str | Path] = None):
        self.vault_root = self._resolve_vault_root(vault_root)
        self.tools = DistillMCPTools(self.vault_root)
        self.sdk_server = Server(
            SERVER_NAME,
            version=__version__,
            instructions=SERVER_INSTRUCTIONS,
        )
        self._register_handlers()

    @staticmethod
    def _resolve_vault_root(vault_root: Optional[str | Path]) -> Path:
        candidate = vault_root or os.environ.get("DISTILL_VAULT")
        if not candidate:
            raise ValueError("Vault path is required via DISTILL_VAULT or --vault")
        path = Path(candidate).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Vault path does not exist: {path}")
        return path

    def _register_handlers(self) -> None:
        @self.sdk_server.list_tools()
        async def list_tools() -> list[mcp_types.Tool]:
            return [
                mcp_types.Tool(
                    name=item["name"],
                    description=item["description"],
                    inputSchema=item["inputSchema"],
                )
                for item in self.tools.list_tools()
            ]

        @self.sdk_server.call_tool(validate_input=True)
        async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = self.tools.call_tool(name=name, arguments=arguments)
            if not isinstance(result, dict):
                raise TypeError(f"Tool '{name}' returned unsupported type: {type(result).__name__}")
            return result

    async def run_stdio(self) -> None:
        """Run the server with the SDK-owned stdio transport and lifecycle."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.sdk_server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=SERVER_NAME,
                    server_version=__version__,
                    capabilities=self.sdk_server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                    instructions=SERVER_INSTRUCTIONS,
                ),
            )

    def serve(self) -> None:
        asyncio.run(self.run_stdio())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="distill-vault MCP server")
    parser.add_argument("--vault", dest="vault", help="Path to vault root")
    args = parser.parse_args(argv)

    DistillMCPServer(vault_root=args.vault).serve()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
