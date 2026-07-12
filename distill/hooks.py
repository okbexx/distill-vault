"""Git hook management for distill-vault repositories."""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

MANAGED_MARKER = "# distill-vault managed"
HOOK_NAMES = ("pre-commit", "post-commit", "post-merge")


class VaultHooks:
    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root).expanduser().resolve()
        self.git_dir = self.vault_root / ".git"
        self.hooks_dir = self.git_dir / "hooks"

    def install(self) -> dict:
        """Install distill git hooks into the vault's .git/hooks/ directory.

        Installs three hooks:
        1. pre-commit: runs `distill lint --staged` — blocks commit on staged error-level issues
        2. post-commit: runs `distill run --incremental` — keeps index fresh (background)
        3. post-merge: runs `distill run` — refreshes index after pull

        Returns dict with keys: installed (list of hook names), skipped (list of existing hooks)
        """
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        installed: list[str] = []
        skipped: list[str] = []

        for hook_name, content in self._hook_scripts().items():
            hook_path = self.hooks_dir / hook_name
            if hook_path.exists() and not self._is_managed_hook(hook_path):
                skipped.append(hook_name)
                continue

            hook_path.write_text(content, encoding="utf-8")
            hook_path.chmod(0o755)
            installed.append(hook_name)

        return {"installed": installed, "skipped": skipped}

    def uninstall(self) -> dict:
        """Remove distill-managed git hooks.
        Only removes hooks that contain '# distill-vault managed' marker.
        Returns dict with keys: removed (list of hook names), not_found (list)
        """
        removed: list[str] = []
        not_found: list[str] = []

        for hook_name in HOOK_NAMES:
            hook_path = self.hooks_dir / hook_name
            if hook_path.exists() and self._is_managed_hook(hook_path):
                hook_path.unlink()
                removed.append(hook_name)
            else:
                not_found.append(hook_name)

        return {"removed": removed, "not_found": not_found}

    def status(self) -> dict:
        """Check which distill hooks are installed.
        Returns dict with keys for each hook name and whether it's installed.
        """
        return {
            hook_name: (self.hooks_dir / hook_name).exists() and self._is_managed_hook(self.hooks_dir / hook_name)
            for hook_name in HOOK_NAMES
        }

    def _hook_scripts(self) -> dict[str, str]:
        cmd = self._distill_shell_command()
        vault = shlex.quote(str(self.vault_root))

        pre_commit = "\n".join([
            "#!/bin/sh",
            MANAGED_MARKER,
            f"cd {vault} || exit 1",
            f"{cmd} lint --staged",
            'status=$?',
            'if [ "$status" -ne 0 ]; then',
            '    echo "distill-vault: commit blocked by lint errors in staged files." >&2',
            '    exit $status',
            'fi',
            'exit 0',
            '',
        ])

        post_commit = "\n".join([
            "#!/bin/sh",
            MANAGED_MARKER,
            f"cd {vault} || exit 0",
            f"{cmd} run --incremental >/dev/null 2>&1 &",
            "exit 0",
            '',
        ])

        post_merge = "\n".join([
            "#!/bin/sh",
            MANAGED_MARKER,
            f"cd {vault} || exit 0",
            f"{cmd} run || true",
            "exit 0",
            '',
        ])

        return {
            "pre-commit": pre_commit,
            "post-commit": post_commit,
            "post-merge": post_merge,
        }

    def _distill_shell_command(self) -> str:
        distill_path = shutil.which("distill")
        if distill_path:
            return shlex.quote(distill_path)
        return "python3 -m distill.cli"

    def _is_managed_hook(self, hook_path: Path) -> bool:
        try:
            return MANAGED_MARKER in hook_path.read_text(encoding="utf-8")
        except OSError:
            return False
