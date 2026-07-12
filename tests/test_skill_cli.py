"""Tests for skill spec scaffolding, discovery, rendering, export, install, verify, doctor, and reconcile flows."""

from pathlib import Path
import json

import frontmatter
from click.testing import CliRunner

from distill.cli import cli
from distill.init_cmd import init_vault
from distill.skill_specs import get_skill_spec, render_skill


def test_init_zh_creates_canonical_skill_area(tmp_path):
    target = tmp_path / "vault-zh"
    init_vault(str(target), lang="zh", with_examples=False)

    skill_dir = target / "系统" / "技能"
    assert skill_dir.is_dir()
    assert (skill_dir / "README.md").exists()
    sample = skill_dir / "vault-distill-ops.md"
    assert sample.exists()

    post = frontmatter.load(sample)
    assert post["type"] == "skill_spec"
    assert post["status"] == "active"
    assert post["name"] == "vault-distill-ops"
    assert "triggers" in post.metadata
    assert "workflow" in post.content.lower() or "工作流" in post.content


def test_init_en_creates_canonical_skill_area(tmp_path):
    target = tmp_path / "vault-en"
    init_vault(str(target), lang="en", with_examples=False)

    skill_dir = target / "system" / "skills"
    assert skill_dir.is_dir()
    assert (skill_dir / "README.md").exists()
    sample = skill_dir / "vault-distill-ops.md"
    assert sample.exists()

    post = frontmatter.load(sample)
    assert post["type"] == "skill_spec"
    assert post["name"] == "vault-distill-ops"
    assert "verification_checklist" in post.metadata


def test_skill_list_discovers_specs(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["--vault", str(target), "skill", "list"])

    assert result.exit_code == 0
    assert "vault-distill-ops" in result.output


def test_skill_export_to_hermes_writes_skill_md(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    out_dir = tmp_path / "exports"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "export",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--output-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    skill_file = out_dir / "hermes" / "vault-distill-ops" / "SKILL.md"
    assert skill_file.exists()
    text = skill_file.read_text(encoding="utf-8")
    assert "name: vault-distill-ops" in text
    assert "description:" in text
    assert "When to Use" in text or "适用场景" in text


def test_skill_export_to_all_writes_all_platform_layouts(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="zh", with_examples=False)
    out_dir = tmp_path / "exports"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "export",
            "vault-distill-ops",
            "--to",
            "all",
            "--output-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    assert (out_dir / "hermes" / "vault-distill-ops" / "SKILL.md").exists()
    assert (out_dir / "codex" / "vault-distill-ops" / "SKILL.md").exists()
    assert (out_dir / "claude" / "vault-distill-ops" / "SKILL.md").exists()


def test_skill_export_stdout_shows_rendered_content(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "export",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--stdout",
        ],
    )

    assert result.exit_code == 0
    assert "vault-distill-ops" in result.output
    assert "description:" in result.output


def test_rendered_skill_includes_platform_notes(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    spec = get_skill_spec(target, "vault-distill-ops")

    rendered = render_skill(spec, "hermes")

    assert "Platform Notes" in rendered
    assert "~/.hermes/skills/<name>/SKILL.md" in rendered


def test_skill_export_missing_skill_returns_clean_error(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "export",
            "missing-skill",
            "--to",
            "hermes",
        ],
    )

    assert result.exit_code != 0
    assert "missing-skill" in result.output


def test_skill_install_to_home_writes_hermes_default_location(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    init_vault(str(target), lang="en", with_examples=False)
    monkeypatch.setenv("HOME", str(fake_home))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "hermes",
        ],
    )

    assert result.exit_code == 0
    installed = fake_home / ".hermes" / "skills" / "vault-distill-ops" / "SKILL.md"
    assert installed.exists()
    assert "installed:" in result.output


def test_skill_install_supports_explicit_target_dir(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "custom-codex-skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "codex",
            "--target-dir",
            str(install_root),
        ],
    )

    assert result.exit_code == 0
    installed = install_root / "vault-distill-ops" / "SKILL.md"
    assert installed.exists()


def test_skill_install_all_writes_to_all_platforms(tmp_path, monkeypatch):
    """install --to all creates SKILL.md in hermes, codex, and claude dirs."""
    target = tmp_path / "vault"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    init_vault(str(target), lang="en", with_examples=False)
    monkeypatch.setenv("HOME", str(fake_home))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault", str(target),
            "skill", "install",
            "vault-distill-ops",
            "--to", "all",
        ],
    )

    assert result.exit_code == 0
    for platform in ("hermes", "codex", "claude"):
        skill_dir = fake_home / {
            "hermes": ".hermes/skills",
            "codex": ".codex/skills",
            "claude": ".claude/skills",
        }[platform] / "vault-distill-ops" / "SKILL.md"
        assert skill_dir.exists(), f"{platform} SKILL.md not created by install --to all"


def test_skill_install_wraps_filesystem_errors(tmp_path):
    target = tmp_path / "vault"
    fake_file = tmp_path / "not-a-dir"
    fake_file.write_text("x", encoding="utf-8")
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(fake_file),
        ],
    )

    assert result.exit_code != 0
    assert "failed to install skill" in result.output.lower()


def test_skill_verify_passes_for_installed_hermes_skill(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    init_vault(str(target), lang="en", with_examples=False)
    monkeypatch.setenv("HOME", str(fake_home))

    runner = CliRunner()
    install_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "hermes",
        ],
    )
    assert install_result.exit_code == 0

    verify_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "hermes",
        ],
    )

    assert verify_result.exit_code == 0
    assert "verified:" in verify_result.output.lower()
    assert "matches rendered output" in verify_result.output.lower()


def test_skill_verify_detects_missing_installation(tmp_path):
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "codex",
            "--target-dir",
            str(tmp_path / "missing-root"),
        ],
    )

    assert result.exit_code != 0
    assert "artifact missing" in result.output.lower()


def test_skill_verify_detects_content_drift(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    install_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(install_root),
        ],
    )
    assert install_result.exit_code == 0

    installed = install_root / "vault-distill-ops" / "SKILL.md"
    installed.write_text(installed.read_text(encoding="utf-8") + "\nmanual drift\n", encoding="utf-8")

    verify_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(install_root),
        ],
    )

    assert verify_result.exit_code != 0
    assert "drift" in verify_result.output.lower()
    assert "does not match rendered output" in verify_result.output.lower()


def test_skill_verify_supports_output_dir_layout(tmp_path):
    target = tmp_path / "vault"
    export_root = tmp_path / "exports"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    export_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "export",
            "vault-distill-ops",
            "--to",
            "codex",
            "--output-dir",
            str(export_root),
        ],
    )
    assert export_result.exit_code == 0

    verify_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "codex",
            "--target-dir",
            str(export_root / "codex"),
        ],
    )

    assert verify_result.exit_code == 0
    assert "verified:" in verify_result.output.lower()


def test_skill_verify_all_reports_multiple_targets(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    init_vault(str(target), lang="en", with_examples=False)
    monkeypatch.setenv("HOME", str(fake_home))

    runner = CliRunner()
    for platform in ("hermes", "codex"):
        install_result = runner.invoke(
            cli,
            [
                "--vault",
                str(target),
                "skill",
                "install",
                "vault-distill-ops",
                "--to",
                platform,
            ],
        )
        assert install_result.exit_code == 0

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "all",
        ],
    )

    assert result.exit_code != 0
    assert "hermes" in result.output.lower()
    assert "codex" in result.output.lower()
    assert "claude" in result.output.lower()
    assert "artifact missing" in result.output.lower()


def test_skill_doctor_summarizes_target_health(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "skills"
    export_root = tmp_path / "exports"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    install_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--target-dir",
            str(install_root / "hermes"),
        ],
    )
    assert install_result.exit_code == 0

    export_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "export",
            "vault-distill-ops",
            "--to",
            "codex",
            "--output-dir",
            str(export_root),
        ],
    )
    assert export_result.exit_code == 0

    drifted = export_root / "codex" / "vault-distill-ops" / "SKILL.md"
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "doctor",
            "vault-distill-ops",
            "--hermes-dir",
            str(install_root / "hermes"),
            "--codex-dir",
            str(export_root / "codex"),
            "--claude-dir",
            str(install_root / "claude"),
        ],
    )

    assert result.exit_code != 0
    assert "hermes" in result.output.lower()
    assert "ok" in result.output.lower()
    assert "codex" in result.output.lower()
    assert "drift" in result.output.lower()
    assert "claude" in result.output.lower()
    assert "missing" in result.output.lower()


def test_skill_verify_json_reports_machine_readable_state(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    install_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--target-dir",
            str(install_root),
        ],
    )
    assert install_result.exit_code == 0

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--target-dir",
            str(install_root),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["skill"] == "vault-distill-ops"
    assert payload["target"] == "hermes"
    assert payload["status"] == "ok"
    assert payload["exists"] is True
    assert payload["matches"] is True
    assert payload["path"].endswith("vault-distill-ops/SKILL.md")
    assert payload["expected_sha256"]
    assert payload["actual_sha256"] == payload["expected_sha256"]


def test_skill_verify_all_json_uses_verify_specific_envelope(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    init_vault(str(target), lang="en", with_examples=False)
    monkeypatch.setenv("HOME", str(fake_home))

    runner = CliRunner()
    for platform in ("hermes", "codex"):
        assert runner.invoke(
            cli,
            [
                "--vault",
                str(target),
                "skill",
                "install",
                "vault-distill-ops",
                "--to",
                platform,
            ],
        ).exit_code == 0

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "all",
            "--format",
            "json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["skill"] == "vault-distill-ops"
    assert payload["mode"] == "verify"
    assert "results" in payload
    assert "summary" not in payload
    statuses = {item["target"]: item["status"] for item in payload["results"]}
    assert statuses == {"hermes": "ok", "codex": "ok", "claude": "missing"}


def test_skill_doctor_json_reports_all_targets(tmp_path):
    target = tmp_path / "vault"
    hermes_root = tmp_path / "hermes-skills"
    codex_root = tmp_path / "codex-skills"
    claude_root = tmp_path / "claude-skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    assert runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--target-dir",
            str(hermes_root),
        ],
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "codex",
            "--target-dir",
            str(codex_root),
        ],
    ).exit_code == 0

    codex_skill = codex_root / "vault-distill-ops" / "SKILL.md"
    codex_skill.write_text(codex_skill.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "doctor",
            "vault-distill-ops",
            "--hermes-dir",
            str(hermes_root),
            "--codex-dir",
            str(codex_root),
            "--claude-dir",
            str(claude_root),
            "--format",
            "json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["skill"] == "vault-distill-ops"
    assert payload["summary"] == {"ok": 1, "drift": 1, "missing": 1}
    by_target = {item["target"]: item for item in payload["targets"]}
    assert by_target["hermes"]["status"] == "ok"
    assert by_target["codex"]["status"] == "drift"
    assert by_target["claude"]["status"] == "missing"


def test_skill_reconcile_copies_canonical_render_to_drifted_target(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    assert runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "install",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(install_root),
        ],
    ).exit_code == 0

    installed = install_root / "vault-distill-ops" / "SKILL.md"
    installed.write_text(installed.read_text(encoding="utf-8") + "\nmanual drift\n", encoding="utf-8")

    dry_run = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "reconcile",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(install_root),
            "--dry-run",
        ],
    )
    assert dry_run.exit_code == 0
    assert "would update" in dry_run.output.lower()
    assert installed.read_text(encoding="utf-8").endswith("manual drift\n")

    apply_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "reconcile",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(install_root),
        ],
    )
    assert apply_result.exit_code == 0
    assert "updated:" in apply_result.output.lower()

    verify_result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "verify",
            "vault-distill-ops",
            "--to",
            "claude",
            "--target-dir",
            str(install_root),
        ],
    )
    assert verify_result.exit_code == 0


def test_skill_reconcile_json_reports_state_machine(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "reconcile",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--target-dir",
            str(install_root),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["skill"] == "vault-distill-ops"
    assert payload["target"] == "hermes"
    assert payload["before"]["status"] == "missing"
    assert payload["action"] == "installed"
    assert payload["after"]["status"] == "ok"
    assert payload["changed"] is True


def test_skill_reconcile_dry_run_json_uses_desired_after_not_fake_observed_after(tmp_path):
    target = tmp_path / "vault"
    install_root = tmp_path / "skills"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault",
            str(target),
            "skill",
            "reconcile",
            "vault-distill-ops",
            "--to",
            "hermes",
            "--target-dir",
            str(install_root),
            "--dry-run",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "install"
    assert payload["changed"] is False
    assert payload["before"]["status"] == "missing"
    assert "after" not in payload
    assert payload["desired_after"]["status"] == "ok"
