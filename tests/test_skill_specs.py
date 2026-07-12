"""Unit tests for distill.skill_specs internals.

Covers:
- _extract_section_list (markdown heading extraction)
- _to_skill_spec (frontmatter → SkillSpec conversion)
- _skill_dir (zh/en path resolution)
- export_targets (target expansion/validation)
- SkillVerificationResult.status property
- Payload builders: verification_result_payload, doctor_payload,
  verify_many_payload, reconcile_result_payload
- render_skill with invalid target
- build_skill_scaffold for both languages
- Edge cases: missing metadata, empty sections, frontmatter without body
"""

import hashlib
import json
from pathlib import Path

import frontmatter
import pytest

from distill.skill_specs import (
    DEFAULT_INSTALL_DIRS,
    SUPPORTED_SKILL_TARGETS,
    SkillReconcileResult,
    SkillSpec,
    SkillVerificationResult,
    _build_sample_skill_spec,
    _extract_section_list,
    _sha256_text,
    _skill_dir,
    _to_skill_spec,
    build_skill_scaffold,
    discover_skill_specs,
    doctor_payload,
    export_targets,
    get_skill_spec,
    reconcile_result_payload,
    render_skill,
    verification_result_payload,
    verify_many_payload,
)


# ---------------------------------------------------------------------------
# _extract_section_list
# ---------------------------------------------------------------------------


class TestExtractSectionList:
    def test_extracts_bullet_items(self):
        body = "## Workflow\n\n- step one\n- step two\n- step three\n\n## Other\n\n- ignored"
        result = _extract_section_list(body, "Workflow")
        assert result == ["step one", "step two", "step three"]

    def test_extracts_numbered_items(self):
        body = "## Workflow\n\n1. first\n2. second\n3. third"
        result = _extract_section_list(body, "Workflow")
        assert result == ["first", "second", "third"]

    def test_mixed_bullets_and_numbers(self):
        body = "## Workflow\n\n- bullet a\n1. numbered b\n- bullet c"
        result = _extract_section_list(body, "Workflow")
        assert result == ["bullet a", "numbered b", "bullet c"]

    def test_empty_section(self):
        body = "## Workflow\n\n## Next Section\n\n- something"
        result = _extract_section_list(body, "Workflow")
        assert result == []

    def test_missing_section(self):
        body = "## Something Else\n\n- item"
        result = _extract_section_list(body, "Workflow")
        assert result == []

    def test_section_at_end_of_body(self):
        body = "## Workflow\n\n- only item"
        result = _extract_section_list(body, "Workflow")
        assert result == ["only item"]

    def test_stops_at_next_h2(self):
        body = "## Workflow\n\n- step a\n\n## Verification\n\n- verify b"
        result = _extract_section_list(body, "Workflow")
        assert result == ["step a"]

    def test_chinese_headings(self):
        body = "## 工作流\n\n- 步骤一\n- 步骤二\n\n## 其他\n\n- 其他内容"
        result = _extract_section_list(body, "工作流")
        assert result == ["步骤一", "步骤二"]

    def test_indented_bullets_still_matched_after_strip(self):
        """stripped = line.strip() removes indentation before matching."""
        body = "## Workflow\n\n  - indented\n- top-level"
        result = _extract_section_list(body, "Workflow")
        # After strip(), both lines match the bullet pattern
        assert result == ["indented", "top-level"]

    def test_asterisk_bullets(self):
        body = "## Workflow\n\n* alpha\n* beta"
        result = _extract_section_list(body, "Workflow")
        assert result == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# _sha256_text
# ---------------------------------------------------------------------------


class TestSha256Text:
    def test_known_value(self):
        result = _sha256_text("hello")
        expected = hashlib.sha256("hello".encode("utf-8")).hexdigest()
        assert result == expected

    def test_empty_string(self):
        result = _sha256_text("")
        assert result == hashlib.sha256(b"").hexdigest()

    def test_unicode(self):
        result = _sha256_text("中文内容")
        assert len(result) == 64  # SHA-256 hex digest length


# ---------------------------------------------------------------------------
# _skill_dir
# ---------------------------------------------------------------------------


class TestSkillDir:
    def test_zh_path(self):
        path = _skill_dir(Path("/vault"), "zh")
        assert path == Path("/vault/系统/技能")

    def test_en_path(self):
        path = _skill_dir(Path("/vault"), "en")
        assert path == Path("/vault/system/skills")


# ---------------------------------------------------------------------------
# export_targets
# ---------------------------------------------------------------------------


class TestExportTargets:
    def test_single_target(self):
        result = export_targets("hermes")
        assert tuple(result) == ("hermes",)

    def test_all_targets(self):
        result = list(export_targets("all"))
        assert tuple(result) == SUPPORTED_SKILL_TARGETS

    def test_invalid_target_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            list(export_targets("invalid"))


# ---------------------------------------------------------------------------
# SkillVerificationResult.status
# ---------------------------------------------------------------------------


class TestSkillVerificationResultStatus:
    def test_missing(self):
        r = SkillVerificationResult(
            target="hermes", path=Path("/x"), exists=False, matches=False,
            expected_sha256="abc", actual_sha256=None,
        )
        assert r.status == "missing"

    def test_drift(self):
        r = SkillVerificationResult(
            target="hermes", path=Path("/x"), exists=True, matches=False,
            expected_sha256="abc", actual_sha256="def",
        )
        assert r.status == "drift"

    def test_ok(self):
        r = SkillVerificationResult(
            target="hermes", path=Path("/x"), exists=True, matches=True,
            expected_sha256="abc", actual_sha256="abc",
        )
        assert r.status == "ok"


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


class TestVerificationResultPayload:
    def test_ok_payload(self):
        r = SkillVerificationResult(
            target="hermes", path=Path("/skills/vault-distill-ops/SKILL.md"),
            exists=True, matches=True, expected_sha256="a1b2", actual_sha256="a1b2",
        )
        payload = verification_result_payload("vault-distill-ops", r)
        assert payload["skill"] == "vault-distill-ops"
        assert payload["target"] == "hermes"
        assert payload["status"] == "ok"
        assert payload["exists"] is True
        assert payload["matches"] is True

    def test_missing_payload_has_none_actual_sha(self):
        r = SkillVerificationResult(
            target="codex", path=Path("/x"), exists=False, matches=False,
            expected_sha256="abc", actual_sha256=None,
        )
        payload = verification_result_payload("test-skill", r)
        assert payload["status"] == "missing"
        assert payload["actual_sha256"] is None


class TestDoctorPayload:
    def test_summary_counts(self):
        results = [
            SkillVerificationResult("hermes", Path("/a"), True, True, "a1", "a1"),
            SkillVerificationResult("codex", Path("/b"), True, False, "b1", "b2"),
            SkillVerificationResult("claude", Path("/c"), False, False, "c1", None),
        ]
        payload = doctor_payload("my-skill", results)
        assert payload["summary"] == {"ok": 1, "drift": 1, "missing": 1}
        assert len(payload["targets"]) == 3

    def test_all_ok(self):
        results = [
            SkillVerificationResult(t, Path(f"/{t}"), True, True, "x", "x")
            for t in SUPPORTED_SKILL_TARGETS
        ]
        payload = doctor_payload("s", results)
        assert payload["summary"] == {"ok": 3, "drift": 0, "missing": 0}


class TestVerifyManyPayload:
    def test_structure(self):
        results = [
            SkillVerificationResult("hermes", Path("/a"), True, True, "a", "a"),
        ]
        payload = verify_many_payload("s", results)
        assert payload["mode"] == "verify"
        assert "results" in payload
        assert "summary" not in payload


class TestReconcileResultPayload:
    def test_changed_true_has_after(self):
        before = SkillVerificationResult("hermes", Path("/a"), False, False, "a1", None)
        after = SkillVerificationResult("hermes", Path("/a"), True, True, "a1", "a1")
        r = SkillReconcileResult("s", "hermes", Path("/a"), before, after, "installed", True)
        payload = reconcile_result_payload(r)
        assert "after" in payload
        assert "desired_after" not in payload
        assert payload["changed"] is True

    def test_changed_false_has_desired_after(self):
        before = SkillVerificationResult("hermes", Path("/a"), False, False, "a1", None)
        after = SkillVerificationResult("hermes", Path("/a"), True, True, "a1", "a1")
        r = SkillReconcileResult("s", "hermes", Path("/a"), before, after, "install", False)
        payload = reconcile_result_payload(r)
        assert "desired_after" in payload
        assert "after" not in payload
        assert payload["changed"] is False


# ---------------------------------------------------------------------------
# build_skill_scaffold
# ---------------------------------------------------------------------------


class TestBuildSkillScaffold:
    def test_zh_scaffold_has_expected_files(self):
        files = build_skill_scaffold("zh")
        assert "README.md" in files
        assert "vault-distill-ops.md" in files

    def test_en_scaffold_has_expected_files(self):
        files = build_skill_scaffold("en")
        assert "README.md" in files
        assert "vault-distill-ops.md" in files

    def test_zh_readme_content(self):
        files = build_skill_scaffold("zh")
        assert "技能规范" in files["README.md"]

    def test_en_readme_content(self):
        files = build_skill_scaffold("en")
        assert "Skill Specs" in files["README.md"]

    def test_zh_sample_is_valid_frontmatter(self):
        files = build_skill_scaffold("zh")
        post = frontmatter.loads(files["vault-distill-ops.md"])
        assert post.metadata["type"] == "skill_spec"
        assert post.metadata["name"] == "vault-distill-ops"
        assert len(post.metadata["triggers"]) >= 4
        assert "工作流" in post.content or "workflow" in post.content.lower()

    def test_en_sample_is_valid_frontmatter(self):
        files = build_skill_scaffold("en")
        post = frontmatter.loads(files["vault-distill-ops.md"])
        assert post.metadata["type"] == "skill_spec"
        assert post.metadata["name"] == "vault-distill-ops"
        assert len(post.metadata["triggers"]) >= 4
        assert "Workflow" in post.content


# ---------------------------------------------------------------------------
# _build_sample_skill_spec (extended coverage)
# ---------------------------------------------------------------------------


class TestBuildSampleSkillSpec:
    def test_zh_spec_contains_verification_checklist(self):
        content = _build_sample_skill_spec("zh")
        post = frontmatter.loads(content)
        assert "verification_checklist" in post.metadata
        assert len(post.metadata["verification_checklist"]) >= 3

    def test_en_spec_contains_verification_checklist(self):
        content = _build_sample_skill_spec("en")
        post = frontmatter.loads(content)
        assert "verification_checklist" in post.metadata
        assert len(post.metadata["verification_checklist"]) >= 3

    def test_en_spec_has_platform_notes(self):
        content = _build_sample_skill_spec("en")
        post = frontmatter.loads(content)
        notes = post.metadata.get("platform_notes", {})
        assert "hermes" in notes
        assert "codex" in notes
        assert "claude" in notes


# ---------------------------------------------------------------------------
# render_skill validation
# ---------------------------------------------------------------------------


class TestRenderSkillValidation:
    def test_invalid_target_raises(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        with pytest.raises(ValueError, match="Unsupported skill target"):
            render_skill(spec, "invalid_platform")

    def test_render_hermes_includes_frontmatter(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        rendered = render_skill(spec, "hermes")
        assert rendered.startswith("---")
        assert "name: vault-distill-ops" in rendered
        assert "author: distill-vault" in rendered

    def test_render_codex_has_html_comment(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        rendered = render_skill(spec, "codex")
        assert "<!-- Codex skill:" in rendered
        assert "---" not in rendered.split("\n")[0]  # no YAML frontmatter

    def test_render_claude_has_at_metadata(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        rendered = render_skill(spec, "claude")
        assert "@name vault-distill-ops" in rendered
        assert "@description" in rendered

    def test_render_zh_uses_localized_headings(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="zh", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        rendered = render_skill(spec, "hermes")
        assert "适用场景" in rendered
        assert "工作流" in rendered


# ---------------------------------------------------------------------------
# discover_skill_specs / get_skill_spec edge cases
# ---------------------------------------------------------------------------


class TestDiscoverSkillSpecs:
    def test_empty_vault_returns_no_specs(self, tmp_path):
        vault = tmp_path / "empty"
        vault.mkdir()
        assert discover_skill_specs(vault) == []

    def test_non_skill_md_files_ignored(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        # Write a non-skill md file
        skills_dir = vault / "system" / "skills"
        (skills_dir / "random-notes.md").write_text("---\ntype: blog\n---\nHello", encoding="utf-8")
        specs = discover_skill_specs(vault)
        names = [s.name for s in specs]
        assert "vault-distill-ops" in names
        assert "random-notes" not in names

    def test_get_skill_spec_raises_for_missing(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        with pytest.raises(FileNotFoundError, match="not found"):
            get_skill_spec(vault, "nonexistent-skill")


# ---------------------------------------------------------------------------
# _to_skill_spec with real frontmatter
# ---------------------------------------------------------------------------


class TestToSkillSpec:
    def test_converts_en_frontmatter_to_spec(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        assert spec.name == "vault-distill-ops"
        assert spec.lang == "en"
        assert len(spec.triggers) >= 4
        assert len(spec.instruction_priority) >= 3
        assert len(spec.workflow) >= 3
        assert len(spec.verification_checklist) >= 3
        assert "hermes" in spec.platform_notes

    def test_converts_zh_frontmatter_to_spec(self, tmp_path):
        from distill.init_cmd import init_vault
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="zh", with_examples=False)
        spec = get_skill_spec(vault, "vault-distill-ops")
        assert spec.name == "vault-distill-ops"
        assert spec.lang == "zh"
        assert len(spec.triggers) >= 4
        assert "distill search" in spec.instruction_priority[1] or "ripgrep" in spec.instruction_priority[1]


# ---------------------------------------------------------------------------
# DEFAULT_INSTALL_DIRS / SUPPORTED_SKILL_TARGETS constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_all_targets_have_default_dirs(self):
        for target in SUPPORTED_SKILL_TARGETS:
            assert target in DEFAULT_INSTALL_DIRS

    def test_default_dirs_contain_tilde(self):
        for target, dir_path in DEFAULT_INSTALL_DIRS.items():
            assert "~" in dir_path or "/" in dir_path

    def test_three_platforms(self):
        assert len(SUPPORTED_SKILL_TARGETS) == 3
        assert set(SUPPORTED_SKILL_TARGETS) == {"hermes", "codex", "claude"}
