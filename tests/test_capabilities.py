import json
from pathlib import Path
from typing import get_type_hints

from click.testing import CliRunner

import distill.capabilities as capabilities
from distill.cli import cli
from distill.mcp_tools import DistillMCPTools



def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    (tmp_path / "知识" / "概念" / "core.md").write_text(
        "---\ntype: concept\ntitle: core\nstatus: active\n---\n# core\n",
        encoding="utf-8",
    )
    return tmp_path


def test_public_capabilities_exports_are_explicit():
    assert capabilities.__all__ == [
        "CapabilityPayload",
        "collect_capabilities",
        "render_capabilities_markdown",
    ]


def test_capability_payload_required_keys_are_explicit():
    assert capabilities.CapabilityPayload.__required_keys__ == {
        "engine_version",
        "module_path",
        "executable_path",
        "python_path",
        "install_mode",
        "editable_source_path",
        "supported_commands",
        "supported_runtime_surfaces",
        "status_fields",
        "worker_pool_modes",
    }


def test_public_capabilities_functions_use_typed_contracts():
    assert get_type_hints(capabilities.collect_capabilities)["return"] is capabilities.CapabilityPayload
    assert get_type_hints(capabilities.render_capabilities_markdown)["payload"] is capabilities.CapabilityPayload
    assert get_type_hints(DistillMCPTools.runtime_capabilities)["return"] is capabilities.CapabilityPayload

    cli_hints = get_type_hints(cli.commands["capabilities"].callback)
    assert cli_hints["fmt"] is str
    assert cli_hints["return"] is type(None)


def test_collect_capabilities_reports_runtime_support():
    payload = capabilities.collect_capabilities()

    assert payload["engine_version"]
    assert payload["module_path"].endswith("distill/__init__.py")
    assert payload["executable_path"]
    assert payload["python_path"]
    assert payload["install_mode"] in {"editable", "installed", "source_tree"}
    assert "route" in payload["supported_commands"]
    assert "plan" in payload["supported_commands"]
    assert "capture" in payload["supported_commands"]
    assert "apply" in payload["supported_commands"]
    assert "projection_route" in payload["supported_runtime_surfaces"]
    assert "projection_plan" in payload["supported_runtime_surfaces"]
    assert "projection_apply" in payload["supported_runtime_surfaces"]
    assert "promotion_review" in payload["supported_runtime_surfaces"]
    assert "promotion_apply" in payload["supported_runtime_surfaces"]
    assert "runtime_stage" in payload["status_fields"]
    assert "vault_layout" in payload["status_fields"]
    assert payload["worker_pool_modes"] == ["auto", "process", "thread", "serial"]



def test_cli_capabilities_json_matches_shared_builder(tmp_path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "capabilities", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == capabilities.collect_capabilities()



def test_mcp_runtime_capabilities_matches_shared_builder(tmp_path):
    vault = _make_vault(tmp_path)
    tools = DistillMCPTools(vault)

    result = tools.runtime_capabilities()

    assert result == capabilities.collect_capabilities()



def test_runtime_capabilities_tool_is_registered(tmp_path):
    vault = _make_vault(tmp_path)
    tools = DistillMCPTools(vault)

    names = [schema["name"] for schema in tools.list_tools()]

    assert "runtime_capabilities" in names


def test_readme_and_instance_upgrade_docs_reference_capabilities_surface():
    repo_root = Path(__file__).resolve().parents[1]
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    docs_text = (repo_root / "docs" / "instance-upgrade-contract.md").read_text(encoding="utf-8")

    assert "distill capabilities --format json" in readme_text
    assert "distill doctor --instance-upgrade --format json" in readme_text
    assert "distill upgrade-plan --format json" in readme_text
    assert "runtime_capabilities" in docs_text
    assert "instance_doctor" in docs_text
    assert "instance_upgrade_plan" in docs_text
