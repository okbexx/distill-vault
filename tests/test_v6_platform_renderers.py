"""v6 tests: platform-differentiated renderers, install --to all, reconcile --to all."""

from pathlib import Path
import json

import frontmatter
from click.testing import CliRunner

from distill.cli import cli
from distill.init_cmd import init_vault
from distill.skill_specs import get_skill_spec, render_skill, SUPPORTED_SKILL_TARGETS


# ── Platform renderer differentiation ─────────────────────────────


def test_hermes_render_includes_yaml_frontmatter(tmp_path):
    """Hermes SKILL.md must start with YAML frontmatter (--- ... ---)."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    spec = get_skill_spec(target, "vault-distill-ops")
    rendered = render_skill(spec, "hermes")
    assert rendered.startswith("---\n")
    assert "\n---\n" in rendered
    post = frontmatter.loads(rendered)
    assert post.metadata["name"] == "vault-distill-ops"


def test_codex_render_has_no_frontmatter(tmp_path):
    """Codex skill should NOT have YAML frontmatter — plain instruction markdown."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    spec = get_skill_spec(target, "vault-distill-ops")
    rendered = render_skill(spec, "codex")
    assert not rendered.startswith("---\n")
    assert "# " in rendered  # has a heading


def test_claude_render_uses_at_comment_metadata(tmp_path):
    """Claude skill uses @-style metadata comments, not YAML frontmatter."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    spec = get_skill_spec(target, "vault-distill-ops")
    rendered = render_skill(spec, "claude")
    assert not rendered.startswith("---\n")
    assert "@name" in rendered
    assert "@description" in rendered


def test_platform_renders_are_structurally_different(tmp_path):
    """All three platform renders must differ from each other."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    spec = get_skill_spec(target, "vault-distill-ops")
    renders = {p: render_skill(spec, p) for p in SUPPORTED_SKILL_TARGETS}
    texts = list(renders.values())
    assert texts[0] != texts[1], "hermes and codex renders must differ"
    assert texts[0] != texts[2], "hermes and claude renders must differ"
    assert texts[1] != texts[2], "codex and claude renders must differ"


def test_all_platforms_still_include_triggers(tmp_path):
    """Regardless of format, each render must contain the trigger content."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)
    spec = get_skill_spec(target, "vault-distill-ops")
    for platform in SUPPORTED_SKILL_TARGETS:
        rendered = render_skill(spec, platform)
        # At least one trigger keyword should appear
        assert "vault" in rendered.lower(), f"{platform} render missing vault reference"


# ── install --to all ──────────────────────────────────────────────


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
    assert result.exit_code == 0, result.output

    for platform in SUPPORTED_SKILL_TARGETS:
        skill_file = fake_home / {
            "hermes": ".hermes/skills",
            "codex": ".codex/skills",
            "claude": ".claude/skills",
        }[platform] / "vault-distill-ops" / "SKILL.md"
        assert skill_file.exists(), f"{platform} SKILL.md not created"


def test_skill_install_all_rejects_target_dir(tmp_path):
    """install --to all should reject --target-dir (ambiguous destination)."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault", str(target),
            "skill", "install",
            "vault-distill-ops",
            "--to", "all",
            "--target-dir", str(tmp_path / "custom"),
        ],
    )
    assert result.exit_code != 0


# ── reconcile --to all ────────────────────────────────────────────


def test_skill_reconcile_all_installs_to_all_platforms(tmp_path, monkeypatch):
    """reconcile --to all installs missing skills across all platforms."""
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
            "skill", "reconcile",
            "vault-distill-ops",
            "--to", "all",
        ],
    )
    assert result.exit_code == 0, result.output

    for platform in SUPPORTED_SKILL_TARGETS:
        skill_file = fake_home / {
            "hermes": ".hermes/skills",
            "codex": ".codex/skills",
            "claude": ".claude/skills",
        }[platform] / "vault-distill-ops" / "SKILL.md"
        assert skill_file.exists(), f"{platform} SKILL.md not reconciled"


def test_skill_reconcile_all_json_returns_per_target_results(tmp_path, monkeypatch):
    """reconcile --to all --format json returns combined results."""
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
            "skill", "reconcile",
            "vault-distill-ops",
            "--to", "all",
            "--format", "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["skill"] == "vault-distill-ops"
    assert "results" in payload
    assert len(payload["results"]) == 3
    targets = {r["target"] for r in payload["results"]}
    assert targets == {"hermes", "codex", "claude"}


def test_skill_reconcile_all_dry_run_does_not_write(tmp_path, monkeypatch):
    """reconcile --to all --dry-run should not create any files."""
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
            "skill", "reconcile",
            "vault-distill-ops",
            "--to", "all",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output

    # None of the three should exist after dry-run
    for platform in SUPPORTED_SKILL_TARGETS:
        skill_file = fake_home / {
            "hermes": ".hermes/skills",
            "codex": ".codex/skills",
            "claude": ".claude/skills",
        }[platform] / "vault-distill-ops" / "SKILL.md"
        assert not skill_file.exists(), f"{platform} SKILL.md should not exist after dry-run"


def test_skill_reconcile_all_rejects_target_dir(tmp_path):
    """reconcile --to all should reject --target-dir (ambiguous destination)."""
    target = tmp_path / "vault"
    init_vault(str(target), lang="en", with_examples=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--vault", str(target),
            "skill", "reconcile",
            "vault-distill-ops",
            "--to", "all",
            "--target-dir", str(tmp_path / "custom"),
        ],
    )
    assert result.exit_code != 0


# ── Backward compatibility ────────────────────────────────────────


def test_existing_verify_all_still_works(tmp_path, monkeypatch):
    """Ensure verify --to all still passes after renderer changes."""
    target = tmp_path / "vault"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    init_vault(str(target), lang="en", with_examples=False)
    monkeypatch.setenv("HOME", str(fake_home))

    runner = CliRunner()
    # Install all first
    runner.invoke(
        cli,
        ["--vault", str(target), "skill", "install",
         "vault-distill-ops", "--to", "all"],
    )
    result = runner.invoke(
        cli,
        ["--vault", str(target), "skill", "verify",
         "vault-distill-ops", "--to", "all"],
    )
    assert result.exit_code == 0, result.output
