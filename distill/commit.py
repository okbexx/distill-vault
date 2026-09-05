"""Commit workflow wrapper for distill-vault repositories."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


class DistillCommit:
    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root).expanduser().resolve()

    def commit(self, message: str, push: bool = False, skip_lint: bool = False, paths: list[str] | None = None, skip_run: bool = False) -> dict:
        """Execute: distill lint → git add → git commit → optional distill run → optional git push

        Steps:
        1. Run distill lint (without --fix). If there are ERROR-level issues, abort and report.
        2. git add -A, or git add -- <paths...> when paths are provided
        3. git commit -m <message>
        4. distill run (incremental) unless skip_run=True
        5. If push: git push

        Returns dict with keys:
        - success: bool
        - lint_issues: list of error issues found
        - commit_hash: str or None
        - push_success: bool or None
        - error: str or None
        """
        lint_issues = []
        for value in paths or []:
            path = Path(value)
            if (not value or path.is_absolute() or ".." in path.parts
                    or value.startswith(":") or any(c in value for c in "*?[]")
                    or not (self.vault_root / path).resolve().is_relative_to(self.vault_root)):
                return self._failure([], None, None, f"expected literal vault-relative path: {value}")
        if not skip_lint:
            lint_args = ["lint", "--format", "json"]
            for path in paths or []:
                lint_args.extend(["--paths", path])
            lint_result = self._run_distill(*lint_args)
            lint_issues = self._extract_error_issues(lint_result)
            if lint_issues:
                return {
                    "success": False,
                    "lint_issues": lint_issues,
                    "commit_hash": None,
                    "push_success": None,
                    "error": "distill lint reported error-level issues",
                }
            if lint_result.returncode != 0 and not lint_issues:
                return {
                    "success": False,
                    "lint_issues": [],
                    "commit_hash": None,
                    "push_success": None,
                    "error": self._command_error("distill lint", lint_result),
                }

        add_command = ["git", "add", "-A"] if not paths else ["git", "add", "--", *paths]
        add_result = self._run_command(add_command)
        if add_result.returncode != 0:
            return self._failure(lint_issues, None, None, self._command_error("git add", add_result))

        commit_command = ["git", "commit", "-m", message]
        if paths:
            commit_command.extend(["--only", "--", *paths])
        commit_result = self._run_command(commit_command)
        if commit_result.returncode != 0:
            return self._failure(lint_issues, None, None, self._command_error("git commit", commit_result))

        hash_result = self._run_command(["git", "rev-parse", "HEAD"])
        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else None

        if not skip_run:
            run_result = self._run_distill("run", "--incremental")
            if run_result.returncode != 0:
                return self._failure(
                    lint_issues, commit_hash, None,
                    self._command_error("distill run", run_result),
                )

        push_success = None
        if push:
            push_result = self._run_command(["git", "push"])
            push_success = push_result.returncode == 0
            if not push_success:
                return self._failure(lint_issues, commit_hash, False, self._command_error("git push", push_result))

        return {
            "success": True,
            "lint_issues": [],
            "commit_hash": commit_hash,
            "push_success": push_success,
            "error": None,
        }

    def _run_distill(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run_command([sys.executable, "-m", "distill.cli", *args])

    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.vault_root,
            capture_output=True,
            text=True,
        )

    def _extract_error_issues(self, lint_result: subprocess.CompletedProcess[str]) -> list[dict]:
        payload = self._parse_json_output(lint_result.stdout)
        issues = payload.get("issues", []) if isinstance(payload, dict) else []
        return [issue for issue in issues if issue.get("severity") == "error"]

    def _parse_json_output(self, output: str) -> dict:
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _failure(self, lint_issues: list[dict], commit_hash: str | None, push_success: bool | None, error: str) -> dict:
        return {
            "success": False,
            "lint_issues": lint_issues,
            "commit_hash": commit_hash,
            "push_success": push_success,
            "error": error,
        }

    def _command_error(self, label: str, result: subprocess.CompletedProcess[str]) -> str:
        details = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        return f"{label} failed: {details}"
