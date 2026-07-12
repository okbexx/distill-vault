"""Explicit write surface for agent-provided vault objects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .atomic_io import atomic_write_text

@dataclass(frozen=True)
class WriteObjectResult:
    status: str
    path: str
    bytes_written: int
    sha256: str
    overwritten: bool


def write_object(
    vault_root: Path | str,
    target: str,
    content: str,
    *,
    overwrite: bool = False,
) -> WriteObjectResult:
    """Write a markdown object inside a vault with path and overwrite guards."""
    if not target.strip():
        raise ValueError("target path is required")

    if not content.strip():
        raise ValueError("content is required")

    vault = Path(vault_root).expanduser().resolve()
    relative = _normalize_relative_target(target)
    target_path = (vault / relative).resolve()

    if target_path != vault and vault not in target_path.parents:
        raise ValueError(f"target escapes vault root: {target}")

    if target_path.suffix.lower() != ".md":
        raise ValueError(f"target must be a markdown file: {target}")

    existed = target_path.exists()
    if existed and not overwrite:
        raise FileExistsError(f"target already exists: {relative.as_posix()}")

    write_result = atomic_write_text(target_path, content, root=vault)

    return WriteObjectResult(
        status="written",
        path=relative.as_posix(),
        bytes_written=write_result.bytes_written,
        sha256=write_result.sha256,
        overwritten=existed,
    )


def _normalize_relative_target(target: str) -> Path:
    normalized = target.replace("\\", "/").strip()
    path = Path(normalized)

    if path.is_absolute() or PureWindowsPath(target).is_absolute() or ".." in path.parts:
        raise ValueError(f"target must stay inside the vault: {target}")

    return path
