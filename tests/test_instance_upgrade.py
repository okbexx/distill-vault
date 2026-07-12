import json
from pathlib import Path
from typing import get_type_hints

from click.testing import CliRunner

import distill.instance_upgrade as instance_upgrade
from distill.capabilities import collect_capabilities
from distill.cli import cli
from distill.mcp_tools import DistillMCPTools


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")



def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "项目").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    _write(
        tmp_path / "知识" / "项目" / "激光雷达.md",
        "---\ntype: project\ntitle: 激光雷达\nstatus: active\n---\n# 激光雷达\n",
    )
    _write(
        tmp_path / "知识" / "来源" / "2026-05-12-碎碎念.md",
        "---\ntype: source\ntitle: 2026-05-12 碎碎念\nstatus: linked\n---\n[[激光雷达]]\n",
    )
    return tmp_path



def _make_outdated_runtime_docs(vault: Path) -> None:
    _write(
        vault / "系统" / "技能" / "vault-distill-ops.md",
        "---\ntype: skill_spec\ntitle: vault-distill-ops\nstatus: active\n---\nUse distill status, distill lint, and distill run for every small update.\n",
    )
    _write(
        vault / "AGENTS.md",
        "Use distill status and distill run.\n",
    )



def test_public_instance_upgrade_exports_are_explicit():
    assert instance_upgrade.__all__ == [
        "DoctorPayload",
        "UpgradePlanPayload",
        "doctor_instance",
        "build_upgrade_plan",
        "render_doctor_markdown",
        "render_upgrade_plan_markdown",
    ]



def test_instance_upgrade_typed_dict_contracts_are_explicit():
    assert instance_upgrade.DoctorPayload.__required_keys__ == {
        "engine_version",
        "runtime_stage",
        "has_checkpoint",
        "install_mode",
        "editable_source_path",
        "adoption_status",
        "capability_gaps",
        "recommended_actions",
        "warnings",
        "legacy_runtime_docs",
    }
    assert instance_upgrade.UpgradePlanPayload.__required_keys__ == {
        "action",
        "status",
        "target",
        "summary",
        "steps",
        "warnings",
    }



def test_instance_upgrade_public_functions_use_typed_contracts():
    assert get_type_hints(instance_upgrade.doctor_instance)["return"] is instance_upgrade.DoctorPayload
    assert get_type_hints(instance_upgrade.build_upgrade_plan)["return"] is instance_upgrade.UpgradePlanPayload
    assert get_type_hints(instance_upgrade.render_doctor_markdown)["payload"] is instance_upgrade.DoctorPayload
    assert get_type_hints(instance_upgrade.render_upgrade_plan_markdown)["payload"] is instance_upgrade.UpgradePlanPayload
    assert get_type_hints(DistillMCPTools.instance_doctor)["return"] is instance_upgrade.DoctorPayload
    assert get_type_hints(DistillMCPTools.instance_upgrade_plan)["return"] is instance_upgrade.UpgradePlanPayload

    doctor_hints = get_type_hints(cli.commands["doctor"].callback)
    assert doctor_hints["instance_upgrade"] is bool
    assert doctor_hints["fmt"] is str
    assert doctor_hints["return"] is type(None)

    upgrade_plan_hints = get_type_hints(cli.commands["upgrade-plan"].callback)
    assert upgrade_plan_hints["fmt"] is str
    assert upgrade_plan_hints["return"] is type(None)



def test_doctor_instance_detects_legacy_runtime_docs_and_recommends_adoption(tmp_path):
    vault = _make_vault(tmp_path)
    _make_outdated_runtime_docs(vault)

    payload = instance_upgrade.doctor_instance(vault)

    assert payload["engine_version"] == collect_capabilities()["engine_version"]
    assert payload["runtime_stage"] in {"preflight", "needs_attention", "trusted_runtime"}
    assert payload["install_mode"] in {"editable", "installed", "source_tree"}
    assert payload["adoption_status"] == "upgrade_recommended"
    assert payload["legacy_runtime_docs"]
    assert any("route" in gap for gap in payload["capability_gaps"])
    assert any("upgrade-plan" in action or "capabilities" in action or "route" in action for action in payload["recommended_actions"])


def test_doctor_instance_detects_configured_engine_authority_drift(tmp_path):
    vault = _make_vault(tmp_path)
    _write(
        vault / "distill.yaml",
        "runtime:\n  engine_version: 999.0.0\n  editable_source_path: /tmp/wrong-distill\n",
    )

    payload = instance_upgrade.doctor_instance(vault)

    assert payload["adoption_status"] == "upgrade_recommended"
    assert any("Configured engine version" in item for item in payload["capability_gaps"])
    assert any("Configured editable source" in item for item in payload["capability_gaps"])
    assert any("configured Distill engine" in item for item in payload["recommended_actions"])



def test_build_upgrade_plan_returns_machine_contract(tmp_path):
    vault = _make_vault(tmp_path)
    _make_outdated_runtime_docs(vault)

    payload = instance_upgrade.build_upgrade_plan(vault)

    assert payload["action"] == "instance_runtime_upgrade"
    assert payload["status"] in {"planned", "not_needed"}
    assert payload["target"] == str(vault)
    assert payload["summary"]
    assert payload["steps"]
    assert isinstance(payload["warnings"], list)



def test_cli_doctor_instance_upgrade_json_matches_shared_builder(tmp_path):
    vault = _make_vault(tmp_path)
    _make_outdated_runtime_docs(vault)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "doctor", "--instance-upgrade", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == instance_upgrade.doctor_instance(vault)



def test_cli_upgrade_plan_json_matches_shared_builder(tmp_path):
    vault = _make_vault(tmp_path)
    _make_outdated_runtime_docs(vault)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "upgrade-plan", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == instance_upgrade.build_upgrade_plan(vault)



def test_mcp_instance_doctor_and_upgrade_plan_match_shared_builders(tmp_path):
    vault = _make_vault(tmp_path)
    _make_outdated_runtime_docs(vault)
    tools = DistillMCPTools(vault)

    assert tools.instance_doctor() == instance_upgrade.doctor_instance(vault)
    assert tools.instance_upgrade_plan() == instance_upgrade.build_upgrade_plan(vault)



def test_instance_tools_are_registered(tmp_path):
    vault = _make_vault(tmp_path)
    tools = DistillMCPTools(vault)

    names = [schema["name"] for schema in tools.list_tools()]

    assert "instance_doctor" in names
    assert "instance_upgrade_plan" in names
