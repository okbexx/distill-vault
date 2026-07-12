"""Guarded atomic filesystem writes for vault-owned artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AtomicWriteResult:
    path: Path
    bytes_written: int
    sha256: str


def resolve_guarded_path(path: Path | str, root: Path | str) -> Path:
    """Resolve a target and reject writes outside ``root`` through traversal or symlinks."""
    root_path = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved_parent = candidate.parent.resolve()
    resolved = resolved_parent / candidate.name
    if resolved != root_path and root_path not in resolved.parents:
        raise ValueError(f"write target escapes root: {path}")
    return resolved


def atomic_write_text(
    path: Path | str,
    content: str,
    *,
    root: Path | str,
    encoding: str = "utf-8",
) -> AtomicWriteResult:
    """Write text beside the target, fsync it, and atomically replace the target."""
    target = resolve_guarded_path(path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode(encoding)
    mode = target.stat().st_mode if target.exists() else None
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return AtomicWriteResult(
        path=target,
        bytes_written=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


__all__ = ["AtomicWriteResult", "atomic_write_text", "resolve_guarded_path"]
