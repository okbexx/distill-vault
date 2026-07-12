"""Tests for git hook management and commit workflow."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from distill.cli import cli
from distill.commit import DistillCommit
from distill.hooks import HOOK_NAMES, MANAGED_MARKER, VaultHooks
from distill.init_cmd import init_vault
from distill.lint import VaultLinter


@pytest.fixture
def fake_git(tmp_path):
    git_dir = tmp_path / ".git"
    (git_dir / "hooks").mkdir(parents=True)
    return tmp_path


class TestVaultHooks:
    def test_install_all_hooks(self, fake_git):
        hooks = VaultHooks(fake_git)

        result = hooks.install()

        assert result == {"installed": list(HOOK_NAMES), "skipped": []}
        for hook_name in HOOK_NAMES:
            hook_path = fake_git / ".git" / "hooks" / hook_name
            assert hook_path.exists()
            assert MANAGED_MARKER in hook_path.read_text(encoding="utf-8")
            mode = hook_path.stat().st_mode
            assert mode & stat.S_IXUSR

    def test_install_skips_existing_non_managed(self, fake_git):
        hook_path = fake_git / ".git" / "hooks" / "pre-commit"
        original_content = "#!/bin/sh\necho custom hook\n"
        hook_path.write_text(original_content, encoding="utf-8")
        hook_path.chmod(0o755)

        hooks = VaultHooks(fake_git)
        result = hooks.install()

        assert "pre-commit" in result["skipped"]
        assert "pre-commit" not in result["installed"]
        assert hook_path.read_text(encoding="utf-8") == original_content

    def test_install_overwrites_managed(self, fake_git):
        hook_path = fake_git / ".git" / "hooks" / "pre-commit"
        old_content = f"#!/bin/sh\n{MANAGED_MARKER}\necho old managed hook\n"
        hook_path.write_text(old_content, encoding="utf-8")
        hook_path.chmod(0o755)

        hooks = VaultHooks(fake_git)
        result = hooks.install()

        assert "pre-commit" in result["installed"]
        new_content = hook_path.read_text(encoding="utf-8")
        assert new_content != old_content
        assert MANAGED_MARKER in new_content
        assert "distill-vault: commit blocked by lint errors in staged files." in new_content

    def test_uninstall_removes_managed(self, fake_git):
        hooks = VaultHooks(fake_git)
        hooks.install()

        result = hooks.uninstall()

        assert result == {"removed": list(HOOK_NAMES), "not_found": []}
        for hook_name in HOOK_NAMES:
            assert not (fake_git / ".git" / "hooks" / hook_name).exists()

    def test_uninstall_ignores_non_managed(self, fake_git):
        hook_path = fake_git / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho keep me\n", encoding="utf-8")
        hook_path.chmod(0o755)

        hooks = VaultHooks(fake_git)
        result = hooks.uninstall()

        assert "pre-commit" in result["not_found"]
        assert hook_path.exists()
        assert MANAGED_MARKER not in hook_path.read_text(encoding="utf-8")

    def test_status_reports_correctly(self, fake_git):
        hooks = VaultHooks(fake_git)
        hooks.install()

        status = hooks.status()

        assert status == {hook_name: True for hook_name in HOOK_NAMES}


class TestDistillCommit:
    @pytest.fixture
    def git_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
        return tmp_path

    @staticmethod
    def _is_distill_command(command, subcommand):
        return (
            len(command) >= 4
            and command[:3] == [sys.executable, "-m", "distill.cli"]
            and command[3] == subcommand
        )

    def test_distill_subcommands_use_current_interpreter(self, git_repo):
        commit = DistillCommit(git_repo)

        with patch("distill.commit.subprocess.run") as mocked_run:
            mocked_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            commit._run_distill("lint", "--format", "json")

        assert mocked_run.call_args.args[0] == [
            sys.executable,
            "-m",
            "distill.cli",
            "lint",
            "--format",
            "json",
        ]

    def test_commit_success(self, git_repo):
        commit = DistillCommit(git_repo)
        calls = []

        def fake_run(command, cwd, capture_output, text):
            calls.append(command)
            if self._is_distill_command(command, "lint"):
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"issues": []}), stderr="")
            if command == ["git", "add", "-A"]:
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            if command[:2] == ["git", "commit"]:
                return subprocess.CompletedProcess(command, 0, stdout="[main abc123] test commit", stderr="")
            if command == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc123\n", stderr="")
            if self._is_distill_command(command, "run"):
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {command}")

        with patch("distill.commit.subprocess.run", side_effect=fake_run):
            result = commit.commit("test commit")

        assert result == {
            "success": True,
            "lint_issues": [],
            "commit_hash": "abc123",
            "push_success": None,
            "error": None,
        }
        assert ["git", "add", "-A"] in calls
        assert ["git", "rev-parse", "HEAD"] in calls

    def test_commit_blocked_by_lint_errors(self, git_repo):
        commit = DistillCommit(git_repo)
        lint_payload = {
            "issues": [
                {"severity": "error", "message": "bad frontmatter"},
                {"severity": "warning", "message": "style issue"},
            ]
        }

        def fake_run(command, cwd, capture_output, text):
            if self._is_distill_command(command, "lint"):
                return subprocess.CompletedProcess(command, 1, stdout=json.dumps(lint_payload), stderr="")
            raise AssertionError(f"Unexpected command: {command}")

        with patch("distill.commit.subprocess.run", side_effect=fake_run) as mocked_run:
            result = commit.commit("test commit")

        assert result["success"] is False
        assert result["commit_hash"] is None
        assert result["push_success"] is None
        assert result["error"] == "distill lint reported error-level issues"
        assert result["lint_issues"] == [{"severity": "error", "message": "bad frontmatter"}]
        assert mocked_run.call_count == 1

    def test_commit_push(self, git_repo):
        commit = DistillCommit(git_repo)
        calls = []

        def fake_run(command, cwd, capture_output, text):
            calls.append(command)
            if self._is_distill_command(command, "lint"):
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"issues": []}), stderr="")
            if command == ["git", "add", "-A"]:
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            if command[:2] == ["git", "commit"]:
                return subprocess.CompletedProcess(command, 0, stdout="[main def456] push commit", stderr="")
            if command == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, stdout="def456\n", stderr="")
            if self._is_distill_command(command, "run"):
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            if command == ["git", "push"]:
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {command}")

        with patch("distill.commit.subprocess.run", side_effect=fake_run):
            result = commit.commit("push commit", push=True)

        assert result == {
            "success": True,
            "lint_issues": [],
            "commit_hash": "def456",
            "push_success": True,
            "error": None,
        }
        assert ["git", "push"] in calls

    def test_commit_scopes_git_add_to_requested_paths(self, git_repo):
        commit = DistillCommit(git_repo)
        calls = []

        def fake_run(command, cwd, capture_output, text):
            calls.append(command)
            if self._is_distill_command(command, "lint"):
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"issues": []}), stderr="")
            if command == ["git", "add", "--", "知识/来源/2026-05-12-碎碎念.md", "知识/项目/激光雷达.md"]:
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            if command[:2] == ["git", "commit"]:
                return subprocess.CompletedProcess(command, 0, stdout="[main a1b2c3] scoped commit", stderr="")
            if command == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, stdout="a1b2c3\n", stderr="")
            if self._is_distill_command(command, "run"):
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {command}")

        with patch("distill.commit.subprocess.run", side_effect=fake_run):
            result = commit.commit(
                "scoped commit",
                paths=["知识/来源/2026-05-12-碎碎念.md", "知识/项目/激光雷达.md"],
            )

        assert result["success"] is True
        assert ["git", "add", "--", "知识/来源/2026-05-12-碎碎念.md", "知识/项目/激光雷达.md"] in calls
        assert ["git", "add", "-A"] not in calls

    def test_commit_skip_run_suppresses_pipeline_execution(self, git_repo):
        commit = DistillCommit(git_repo)
        calls = []

        def fake_run(command, cwd, capture_output, text):
            calls.append(command)
            if self._is_distill_command(command, "lint"):
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"issues": []}), stderr="")
            if command == ["git", "add", "-A"]:
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            if command[:2] == ["git", "commit"]:
                return subprocess.CompletedProcess(command, 0, stdout="[main c3d4e5] no run", stderr="")
            if command == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, stdout="c3d4e5\n", stderr="")
            raise AssertionError(f"Unexpected command: {command}")

        with patch("distill.commit.subprocess.run", side_effect=fake_run):
            result = commit.commit("no run", skip_run=True)

        assert result["success"] is True
        assert not any(self._is_distill_command(command, "run") for command in calls)

    def test_commit_cli_threads_paths_and_skip_run(self, git_repo):
        (git_repo / "knowledge").mkdir()
        runner = CliRunner()
        captured = {}

        class FakeCommit:
            def __init__(self, vault_root):
                captured["vault_root"] = vault_root

            def commit(self, message, push=False, skip_lint=False, paths=None, skip_run=False):
                captured.update({
                    "message": message,
                    "push": push,
                    "skip_lint": skip_lint,
                    "paths": paths,
                    "skip_run": skip_run,
                })
                return {
                    "success": True,
                    "lint_issues": [],
                    "commit_hash": "12345678",
                    "push_success": None,
                    "error": None,
                }

        with patch("distill.commit.DistillCommit", FakeCommit):
            result = runner.invoke(
                cli,
                [
                    "--vault", str(git_repo), "commit", "small capture",
                    "--paths", "知识/来源/2026-05-12-碎碎念.md",
                    "--paths", "知识/项目/激光雷达.md",
                    "--skip-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert captured["message"] == "small capture"
        assert captured["paths"] == ["知识/来源/2026-05-12-碎碎念.md", "知识/项目/激光雷达.md"]
        assert captured["skip_run"] is True
        assert "✓ Committed" in result.output


class TestStagedLintBehavior:
    @pytest.fixture
    def git_vault(self, tmp_path):
        vault = tmp_path / "vault"
        init_vault(str(vault), lang="en", with_examples=False)
        subprocess.run(["git", "init"], cwd=vault, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "okbexx"], cwd=vault, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "okbexx@gmail.com"], cwd=vault, check=True, capture_output=True, text=True)
        (vault / "knowledge" / "test.md").write_text(
            "---\ntype: concept\ntitle: Test\nstatus: active\n---\nhello\n",
            encoding="utf-8",
        )
        return vault

    def test_staged_lint_filters_to_staged_files(self, git_vault):
        # Create one broken staged file and one unstaged clean file
        broken = git_vault / "knowledge" / "broken.md"
        broken.write_text(
            "---\ntype: concept\ntitle: Broken\nstatus: active\n---\n[[missing-target]]\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "knowledge/broken.md"], cwd=git_vault, check=True, capture_output=True, text=True)

        linter = VaultLinter(git_vault)
        linter.scan()
        issues = linter.lint(staged=True)

        assert issues, "Expected staged issues for broken.md"
        assert all(issue.get("file") == "knowledge/broken.md" for issue in issues)
        assert any(issue.get("severity") == "error" for issue in issues)

    def test_staged_lint_ignores_unstaged_repo_warnings(self, git_vault):
        subprocess.run(["git", "add", "knowledge/test.md"], cwd=git_vault, check=True, capture_output=True, text=True)

        linter = VaultLinter(git_vault)
        linter.scan()
        issues = linter.lint(staged=True)

        # Should only report issues belonging to staged file, not repo-wide system warnings
        assert all(issue.get("file") == "knowledge/test.md" for issue in issues)

    def test_pre_commit_hook_allows_first_clean_commit(self, git_vault):
        hooks = VaultHooks(git_vault)
        hooks.install()
        subprocess.run(["git", "add", "knowledge/test.md"], cwd=git_vault, check=True, capture_output=True, text=True)

        result = subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=git_vault,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + "\n" + result.stderr

    def test_pre_commit_hook_blocks_staged_error(self, git_vault):
        hooks = VaultHooks(git_vault)
        hooks.install()
        (git_vault / "knowledge" / "test.md").write_text(
            "---\ntype: concept\ntitle: Test\nstatus: active\n---\n[[missing-target]]\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "knowledge/test.md"], cwd=git_vault, check=True, capture_output=True, text=True)

        result = subprocess.run(
            ["git", "commit", "-m", "should fail"],
            cwd=git_vault,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode != 0
        assert "commit blocked" in (result.stdout + result.stderr)
