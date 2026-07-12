from pathlib import Path
import sys

from click.testing import CliRunner
import pytest
import tomlkit

from distill.cli import cli
from distill.mcp_config import (
    MCPConfigError,
    VerificationResult,
    get_codex_mcp_status,
    install_codex_mcp_server,
    resolve_codex_config_path,
    resolve_install_vault,
)


def _make_vault(path: Path) -> Path:
    (path / ".obsidian").mkdir(parents=True)
    (path / "知识" / "项目").mkdir(parents=True)
    return path


def _ok_verifier(command: str, args: list[str], vault: Path, env: dict[str, str]) -> VerificationResult:
    return VerificationResult(ok=True, server_name="distill-vault-mcp", vault_root=str(vault))


def test_install_creates_new_codex_config(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "codex" / "config.toml"

    result = install_codex_mcp_server(
        vault_path=vault,
        config_path=config,
        verify=False,
    )

    assert result.backup_path is None
    assert config.exists()
    doc = tomlkit.parse(config.read_text(encoding="utf-8"))
    server = doc["mcp_servers"]["distill"]
    assert server["type"] == "stdio"
    assert server["command"] == sys.executable
    assert list(server["args"]) == ["-m", "distill.mcp_server", "--vault", str(vault.resolve())]


def test_install_rejects_existing_server_without_force(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    config.write_text("[mcp_servers.distill]\ncommand = \"old\"\n", encoding="utf-8")

    with pytest.raises(MCPConfigError, match="Use --force"):
        install_codex_mcp_server(vault_path=vault, config_path=config, verify=False)

    assert "old" in config.read_text(encoding="utf-8")


def test_install_force_replaces_existing_server_and_preserves_others(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    config.write_text(
        "[mcp_servers.distill]\ncommand = \"old\"\nargs = [\"old\"]\n\n"
        "[mcp_servers.gitnexus]\ncommand = \"gitnexus\"\nargs = [\"mcp\"]\n",
        encoding="utf-8",
    )

    result = install_codex_mcp_server(
        vault_path=vault,
        config_path=config,
        force=True,
        verify=False,
    )

    assert result.backup_path is not None
    assert result.backup_path.exists()
    doc = tomlkit.parse(config.read_text(encoding="utf-8"))
    assert doc["mcp_servers"]["distill"]["command"] == sys.executable
    assert doc["mcp_servers"]["gitnexus"]["command"] == "gitnexus"


def test_install_dry_run_does_not_write(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"

    result = install_codex_mcp_server(
        vault_path=vault,
        config_path=config,
        dry_run=True,
    )

    assert not config.exists()
    assert "[mcp_servers.distill]" in result.rendered_config
    assert str(vault.resolve()) in result.rendered_config


def test_install_use_env_stores_vault_in_env(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"

    install_codex_mcp_server(
        vault_path=vault,
        config_path=config,
        use_env=True,
        verify=False,
    )

    doc = tomlkit.parse(config.read_text(encoding="utf-8"))
    server = doc["mcp_servers"]["distill"]
    assert list(server["args"]) == ["-m", "distill.mcp_server"]
    assert server["env"]["DISTILL_VAULT"] == str(vault.resolve())


def test_resolve_config_path_precedence(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit.toml"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert resolve_codex_config_path(explicit) == explicit.resolve()
    assert resolve_codex_config_path(None) == (codex_home / "config.toml").resolve()

    monkeypatch.delenv("CODEX_HOME")
    assert resolve_codex_config_path(None) == (tmp_path / "home" / ".codex" / "config.toml").resolve()


def test_resolve_install_vault_requires_vault_like_directory(tmp_path):
    with pytest.raises(MCPConfigError, match="does not look"):
        resolve_install_vault(tmp_path, context_vault=None)

    vault = _make_vault(tmp_path / "vault")
    assert resolve_install_vault(None, context_vault=vault) == vault.resolve()


def test_status_parses_arg_vault_path(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    install_codex_mcp_server(vault_path=vault, config_path=config, verify=False)

    status = get_codex_mcp_status(config_path=config)

    assert status.installed is True
    assert status.vault_path == vault.resolve()
    assert status.vault_exists is True
    assert status.vault_like is True
    assert status.command_exists is True


def test_status_parses_env_vault_path(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    install_codex_mcp_server(vault_path=vault, config_path=config, use_env=True, verify=False)

    status = get_codex_mcp_status(config_path=config)

    assert status.vault_path == vault.resolve()
    assert status.env["DISTILL_VAULT"] == str(vault.resolve())


def test_verify_failure_rolls_back_config(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    original = "[mcp_servers.distill]\ncommand = \"old\"\n"
    config.write_text(original, encoding="utf-8")

    def failing_verifier(command: str, args: list[str], vault_path: Path, env: dict[str, str]) -> VerificationResult:
        raise MCPConfigError("boom")

    with pytest.raises(MCPConfigError, match="restored"):
        install_codex_mcp_server(
            vault_path=vault,
            config_path=config,
            force=True,
            verify=True,
            verifier=failing_verifier,
        )

    assert config.read_text(encoding="utf-8") == original
    backups = list(tmp_path.glob("config.toml.bak-*"))
    assert len(backups) == 1


def test_use_env_verification_receives_env(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    seen = {}

    def verifier(command: str, args: list[str], vault_path: Path, env: dict[str, str]) -> VerificationResult:
        seen["args"] = args
        seen["env"] = env
        return VerificationResult(ok=True, server_name="distill-vault-mcp", vault_root=str(vault_path))

    install_codex_mcp_server(
        vault_path=vault,
        config_path=config,
        use_env=True,
        verify=True,
        verifier=verifier,
    )

    assert seen["args"] == ["-m", "distill.mcp_server"]
    assert seen["env"]["DISTILL_VAULT"] == str(vault.resolve())


def test_cli_mcp_install_dry_run(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "mcp",
            "install",
            "--to",
            "codex",
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "[mcp_servers.distill]" in result.output
    assert not config.exists()


def test_cli_mcp_status_reads_config(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    config = tmp_path / "config.toml"
    install_codex_mcp_server(vault_path=vault, config_path=config, verify=False)
    runner = CliRunner()

    result = runner.invoke(cli, ["mcp", "status", "--to", "codex", "--config", str(config)])

    assert result.exit_code == 0
    assert "Installed: yes" in result.output
    assert str(vault.resolve()) in result.output
