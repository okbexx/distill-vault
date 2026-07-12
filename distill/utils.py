"""Utilities."""

from pathlib import Path

from .config import looks_like_obsidian_vault


def find_vault_root(start: Path) -> Path | None:
    """Find vault root by looking for distill markers or an Obsidian marker directory."""
    current = start.resolve()
    for _ in range(10):  # max depth
        # Check for config file first
        if (current / "distill.yaml").exists():
            return current
        # Existing Obsidian vaults can run in inferred mode before distill.yaml exists
        if (current / ".obsidian").exists():
            return current
        # Check for Chinese or English knowledge base structure
        if (current / "知识").exists() or (current / "knowledge").exists():
            return current
        if looks_like_obsidian_vault(current):
            return current
        if current.parent == current:
            break
        current = current.parent
    return None
