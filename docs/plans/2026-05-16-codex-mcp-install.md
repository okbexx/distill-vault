# Codex MCP Install

Date: 2026-05-16

## Goal

Make a distill-managed vault available to Codex from any project directory through a first-class install command:

```bash
distill mcp install --to codex --vault /path/to/vault
```

The command installs the MCP runtime connection only. Skill routing remains a separate lifecycle so users can update MCP access without implicitly changing agent behavior.

## Decisions

- Codex is the first supported install target.
- The default MCP server name is `distill`; advanced users can pass `--name`.
- The server starts with the current Python interpreter as an absolute `command` and `-m distill.mcp_server` in `args`.
- The vault path is written in `args` by default. `--use-env` writes `DISTILL_VAULT` instead.
- If `--vault` is omitted, the current directory may be used only when it looks like a distill/Obsidian vault.
- Existing server entries are not overwritten unless `--force` is passed.
- Installs create a timestamped backup before writing.
- Install verifies the server by sending MCP `initialize` unless `--no-verify` is passed.
- Verification failure restores the previous config from backup and leaves the backup file for audit.
- `status` is read-only by default. It performs a live MCP check only with `--verify`.
- Codex config path resolution is `--config`, then `CODEX_HOME/config.toml`, then `~/.codex/config.toml`.
- TOML is read and written through `tomlkit` so comments and existing formatting are preserved where possible.

## Permission Model

Global knowledge access is read-friendly and write-conservative:

- Normal use should favor `search`, `vault_status`, `object_context`, `projection_route`, and `projection_plan`.
- Write-side tools such as `projection_apply` require explicit user intent.
- Skill files should not write vault markdown directly. Writes should go through distill CLI or MCP runtime surfaces.

## Initial Command Surface

```bash
distill mcp install --to codex [--vault PATH] [--name NAME] [--force] [--dry-run] [--no-verify] [--use-env] [--config PATH]
distill mcp status --to codex [--name NAME] [--verify] [--config PATH]
```

Deferred:

- `distill mcp uninstall --to codex`
- `distill mcp doctor --to codex`
- `distill mcp install --with-skill ...`

## Success Criteria

- `install` creates or updates `[mcp_servers.<name>]` in Codex config.
- `status` reports server presence, command, vault path, and vault validity.
- Dry-run never writes files.
- Existing entries require `--force`.
- Verification failure rolls back config.
- Tests cover new config creation, force replacement, dry-run, env mode, config path precedence, status parsing, and rollback.
