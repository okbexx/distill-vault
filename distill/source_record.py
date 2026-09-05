"""Source-only inbox capture; no routing, classification or promotion required."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid
from urllib.parse import quote

import yaml

from .atomic_io import resolve_guarded_path
from .commit import recommended_commit_command
from .config import get_scan_dirs, load_config


def record_source(vault_root: Path | str, text: str, *, attachments: list[str] | None = None) -> dict:
    """Create a unique raw source bundle, copying attachments without replacing files.

    ``capture.source_dir`` may select an inbox within configured scan roots.
    Otherwise use a conventional source folder or the first knowledge root.
    Raw UTF-8 bytes live in original.txt (including whitespace and line endings).
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if attachments is not None and (not isinstance(attachments, list) or not all(isinstance(p, str) for p in attachments)):
        raise ValueError("attachments must be a list of file paths")
    if not text.strip() and not attachments:
        raise ValueError("text or at least one attachment is required")
    vault = Path(vault_root).expanduser().resolve()
    config = load_config(vault)
    knowledge = config.get("vault", {}).get("knowledge_dirs") or []
    roots = [(vault / p).resolve() for p in knowledge] or [p.resolve() for p in get_scan_dirs(config, vault)]
    configured = config.get("capture", {}).get("source_dir")
    if configured:
        inbox = vault / configured
    elif (vault / "知识").exists() and (vault / "知识").resolve() in roots:
        inbox = vault / "知识/来源"
    elif (vault / "knowledge").exists() and (vault / "knowledge").resolve() in roots:
        inbox = vault / "knowledge/source"
    else:
        knowledge = config.get("vault", {}).get("knowledge_dirs") or []
        inbox = vault / knowledge[0] if knowledge else (roots[0] if roots else vault / "收件箱")
    inbox = resolve_guarded_path(inbox / ".guard", vault).parent
    if not any(inbox == root or root in inbox.parents for root in roots):
        raise ValueError("source inbox must be inside configured scan roots")
    inputs = [Path(p).expanduser().resolve(strict=True) for p in (attachments or [])]
    if any(not p.is_file() for p in inputs):
        raise ValueError("attachments must be regular files")
    stamp = datetime.now(timezone.utc)
    identifier = f"{stamp:%Y-%m-%d}-{uuid.uuid4().hex}"
    bundle = resolve_guarded_path(inbox / identifier, vault)
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.mkdir()  # Exclusive reservation: collisions never replace existing content.
    try:
        raw = bundle / "original.txt"
        with raw.open("xb") as handle:
            handle.write(text.encode("utf-8"))
        copied = []
        for number, source in enumerate(inputs, 1):
            destination = bundle / f"{number}-{source.name}"
            with source.open("rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
            copied.append(destination)
        metadata = {
            "id": f"source-{identifier}", "type": "source", "title": f"Inbox {identifier}",
            "status": "raw", "lifecycle_stage": "raw", "source_type": "note",
            "created_at": stamp.isoformat(), "source_url": None, "author": None,
            "reliability": "unknown", "projects": [], "concepts": [], "entities": [], "outputs": [],
            "attachments": [path.name for path in copied],
        }
        body = text + "\n\n---\n[Original UTF-8 bytes](original.txt)\n"
        for path in copied:
            body += f"\n[Attachment]({quote(path.name)})\n"
        source_path = bundle / "source.md"
        with source_path.open("x", encoding="utf-8", newline="") as handle:
            handle.write("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n\n" + body)
    except BaseException:
        shutil.rmtree(bundle)
        raise
    relative = lambda p: p.relative_to(vault).as_posix()
    touched = [relative(source_path), relative(raw), *map(relative, copied)]
    message = "知识库: 保存临时记录"
    command = recommended_commit_command(vault, touched, message)
    return {
        "action": "source_record", "operation": "source_only", "status": "applied",
        "source_path": relative(source_path), "raw_path": relative(raw),
        "attachment_paths": list(map(relative, copied)), "touched_paths": touched,
        "recommended_commit_paths": touched, "recommended_commit_message": message,
        "recommended_commit_command": command,
    }
