"""MCP client configuration helpers for distill-vault."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import os
import re
import shutil
import sys
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import tomlkit
from tomlkit.items import Table

from .config import looks_like_obsidian_vault


DEFAULT_CODEX_MCP_NAME = "distill"
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class MCPConfigError(Exception):
    """Raised when an MCP client configuration cannot be updated."""


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    server_name: str | None
    vault_root: str | None


@dataclass(frozen=True)
class InstallResult:
    config_path: Path
    server_name: str
    vault_path: Path
    backup_path: Path | None
    dry_run: bool
    verified: bool
    rendered_config: str


@dataclass(frozen=True)
class StatusResult:
    config_path: Path
    server_name: str
    installed: bool
    command: str | None
    args: list[str]
    env: dict[str, str]
    vault_path: Path | None
    vault_exists: bool
    vault_like: bool
    command_exists: bool
    verification: VerificationResult | None


Verifier = Callable[[str, list[str], Path, dict[str, str]], VerificationResult]


def resolve_codex_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "config.toml").resolve()
    return (Path.home() / ".codex" / "config.toml").resolve()


def resolve_install_vault(cli_vault: str | Path | None, context_vault: Path | None = None) -> Path:
    candidate = Path(cli_vault).expanduser() if cli_vault is not None else context_vault
    if candidate is None:
        raise MCPConfigError("Current directory does not look like a distill vault. Pass --vault /path/to/vault.")
    vault = Path(candidate).expanduser().resolve()
    if not vault.exists():
        raise MCPConfigError(f"Vault path does not exist: {vault}")
    if not looks_like_obsidian_vault(vault):
        raise MCPConfigError(f"Vault path does not look like a distill/Obsidian vault: {vault}")
    return vault


def install_codex_mcp_server(
    *,
    vault_path: Path,
    config_path: Path,
    name: str = DEFAULT_CODEX_MCP_NAME,
    force: bool = False,
    dry_run: bool = False,
    verify: bool = True,
    use_env: bool = False,
    verifier: Verifier | None = None,
) -> InstallResult:
    _validate_server_name(name)
    config_path = Path(config_path).expanduser().resolve()
    vault_path = Path(vault_path).expanduser().resolve()
    doc = _load_codex_config(config_path)
    servers = _ensure_mcp_servers_table(doc)
    if name in servers and not force:
        raise MCPConfigError(f"MCP server '{name}' already exists in {config_path}. Use --force to replace it.")

    if name in servers:
        del servers[name]
    command = sys.executable
    servers[name] = _build_distill_server_table(command=command, vault_path=vault_path, use_env=use_env)
    rendered = tomlkit.dumps(doc)

    if dry_run:
        return InstallResult(
            config_path=config_path,
            server_name=name,
            vault_path=vault_path,
            backup_path=None,
            dry_run=True,
            verified=False,
            rendered_config=rendered,
        )

    backup_path = _backup_existing_config(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(rendered, encoding="utf-8")
    verified = False
    try:
        if verify:
            server = servers[name]
            verification = (verifier or verify_codex_mcp_server)(
                str(server["command"]),
                list(server.get("args", [])),
                vault_path,
                {str(key): str(value) for key, value in dict(server.get("env", {})).items()},
            )
            if not verification.ok:
                raise MCPConfigError("MCP initialize verification failed")
            verified = True
    except Exception as exc:
        _rollback_config(config_path, backup_path)
        raise MCPConfigError(f"install failed; restored {config_path} after verification error: {exc}") from exc

    return InstallResult(
        config_path=config_path,
        server_name=name,
        vault_path=vault_path,
        backup_path=backup_path,
        dry_run=False,
        verified=verified,
        rendered_config=rendered,
    )


def get_codex_mcp_status(
    *,
    config_path: Path,
    name: str = DEFAULT_CODEX_MCP_NAME,
    verify: bool = False,
    verifier: Verifier | None = None,
) -> StatusResult:
    _validate_server_name(name)
    config_path = Path(config_path).expanduser().resolve()
    doc = _load_codex_config(config_path)
    servers = doc.get("mcp_servers")
    server = servers.get(name) if hasattr(servers, "get") else None
    if server is None:
        return StatusResult(
            config_path=config_path,
            server_name=name,
            installed=False,
            command=None,
            args=[],
            env={},
            vault_path=None,
            vault_exists=False,
            vault_like=False,
            command_exists=False,
            verification=None,
        )

    command = str(server.get("command")) if server.get("command") is not None else None
    args = [str(item) for item in server.get("args", [])]
    env = {str(key): str(value) for key, value in dict(server.get("env", {})).items()}
    vault = _extract_vault_path(args=args, env=env)
    command_exists = _command_exists(command)
    verification = None
    if verify and command and vault:
        verification = (verifier or verify_codex_mcp_server)(command, args, vault, env)
    return StatusResult(
        config_path=config_path,
        server_name=name,
        installed=True,
        command=command,
        args=args,
        env=env,
        vault_path=vault,
        vault_exists=bool(vault and vault.exists()),
        vault_like=bool(vault and vault.exists() and looks_like_obsidian_vault(vault)),
        command_exists=command_exists,
        verification=verification,
    )


def verify_codex_mcp_server(
    command: str,
    args: list[str],
    vault_path: Path,
    env: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> VerificationResult:
    try:
        return asyncio.run(
            asyncio.wait_for(
                _verify_codex_mcp_server(command, args, vault_path, env),
                timeout=timeout,
            )
        )
    except TimeoutError as exc:
        raise MCPConfigError("MCP server did not complete SDK verification before timeout") from exc
    except MCPConfigError:
        raise
    except Exception as exc:
        raise MCPConfigError(f"MCP SDK verification failed: {exc}") from exc


async def _verify_codex_mcp_server(
    command: str,
    args: list[str],
    vault_path: Path,
    env: dict[str, str] | None,
) -> VerificationResult:
    parameters = StdioServerParameters(
        command=command,
        args=args,
        env={**os.environ, **(env or {})},
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            server_name = initialized.serverInfo.name
            if server_name != "distill-vault-mcp":
                raise MCPConfigError(f"unexpected MCP server name: {server_name}")
            listed = await session.list_tools()
            if "vault_status" not in {tool.name for tool in listed.tools}:
                raise MCPConfigError("MCP tools/list did not include vault_status")
            status = await session.call_tool("vault_status", arguments={})
            if status.isError:
                raise MCPConfigError("MCP vault_status verification returned an error")
            structured_content = status.structuredContent or {}
            vault_root = structured_content.get("vault_root")
            if Path(str(vault_root)).resolve() != Path(vault_path).resolve():
                raise MCPConfigError(f"unexpected MCP vault_root: {vault_root}")
            return VerificationResult(ok=True, server_name=server_name, vault_root=vault_root)


def render_status(result: StatusResult) -> str:
    lines = [
        f"Config: {result.config_path}",
        f"Server: {result.server_name}",
        f"Installed: {'yes' if result.installed else 'no'}",
    ]
    if not result.installed:
        return "\n".join(lines)
    lines.extend(
        [
            f"Command: {result.command}",
            f"Command exists: {'yes' if result.command_exists else 'no'}",
            f"Args: {json.dumps(result.args, ensure_ascii=False)}",
            f"Vault: {result.vault_path or '-'}",
            f"Vault exists: {'yes' if result.vault_exists else 'no'}",
            f"Vault-like: {'yes' if result.vault_like else 'no'}",
        ]
    )
    if result.env:
        lines.append(f"Env: {json.dumps(result.env, ensure_ascii=False)}")
    if result.verification is not None:
        lines.append(f"Live verification: {'ok' if result.verification.ok else 'failed'}")
    return "\n".join(lines)


def _validate_server_name(name: str) -> None:
    if not _SERVER_NAME_RE.match(name):
        raise MCPConfigError("MCP server name must match [A-Za-z0-9_-]+")


def _load_codex_config(config_path: Path) -> Any:
    if not config_path.exists():
        return tomlkit.document()
    try:
        return tomlkit.parse(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MCPConfigError(f"Failed to parse TOML config {config_path}: {exc}") from exc


def _ensure_mcp_servers_table(doc: Any) -> Table:
    if "mcp_servers" not in doc:
        doc["mcp_servers"] = tomlkit.table()
    servers = doc["mcp_servers"]
    if not isinstance(servers, Table):
        raise MCPConfigError("'mcp_servers' must be a TOML table")
    return servers


def _build_distill_server_table(*, command: str, vault_path: Path, use_env: bool) -> Table:
    table = tomlkit.table()
    table["type"] = "stdio"
    table["command"] = command
    if use_env:
        table["args"] = ["-m", "distill.mcp_server"]
        env = tomlkit.inline_table()
        env["DISTILL_VAULT"] = str(vault_path)
        table["env"] = env
    else:
        table["args"] = ["-m", "distill.mcp_server", "--vault", str(vault_path)]
    return table


def _backup_existing_config(config_path: Path) -> Path | None:
    if not config_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = config_path.with_name(f"{config_path.name}.bak-{stamp}")
    shutil.copy2(config_path, backup_path)
    return backup_path


def _rollback_config(config_path: Path, backup_path: Path | None) -> None:
    if backup_path is not None and backup_path.exists():
        shutil.copy2(backup_path, config_path)
        return
    if config_path.exists():
        config_path.unlink()


def _extract_vault_path(*, args: list[str], env: dict[str, str]) -> Path | None:
    if "--vault" in args:
        index = args.index("--vault")
        if index + 1 < len(args):
            return Path(args[index + 1]).expanduser().resolve()
    if "DISTILL_VAULT" in env:
        return Path(env["DISTILL_VAULT"]).expanduser().resolve()
    return None


def _command_exists(command: str | None) -> bool:
    if not command:
        return False
    if Path(command).is_absolute():
        return Path(command).exists()
    return shutil.which(command) is not None
