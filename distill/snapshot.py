"""Single-pass immutable representation of a Markdown vault."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import frontmatter

from .config import get_ops_dir, get_scan_dirs, load_config
from .vault_semantics import (
    extract_frontmatter_links, extract_wikilinks, is_plain_inbox_source,
    is_raw_source, source_attachment_owners,
)


@dataclass(frozen=True)
class VaultObject:
    path: str
    title: str
    type: str
    status: str
    frontmatter: Mapping[str, Any]
    content: str
    links: tuple[str, ...]

    def as_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        payload = {
            "path": self.path,
            "title": self.title,
            "type": self.type,
            "status": self.status,
            "frontmatter": dict(self.frontmatter),
        }
        if include_content:
            payload["content"] = self.content
        return payload


@dataclass(frozen=True)
class SnapshotDiagnostic:
    path: str
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class VaultSnapshot:
    root: Path
    objects: tuple[VaultObject, ...]
    diagnostics: tuple[SnapshotDiagnostic, ...] = field(default_factory=tuple)

    @property
    def by_path(self) -> Mapping[str, VaultObject]:
        return MappingProxyType({obj.path: obj for obj in self.objects})

    @property
    def by_id(self) -> Mapping[str, VaultObject]:
        return MappingProxyType({
            str(obj.frontmatter["id"]): obj
            for obj in self.objects
            if obj.frontmatter.get("id")
        })

    @classmethod
    def scan(cls, vault_root: Path | str, config: dict | None = None) -> "VaultSnapshot":
        root = Path(vault_root).expanduser().resolve()
        config = config or load_config(root)
        ops_dir = get_ops_dir(config, root).resolve()
        seen: set[Path] = set()
        objects: list[VaultObject] = []
        diagnostics: list[SnapshotDiagnostic] = []

        paths = []
        for scan_root in get_scan_dirs(config, root):
            for path in sorted(scan_root.rglob("*.md")):
                resolved = path.resolve()
                if (resolved in seen or not resolved.is_relative_to(root)
                        or resolved != path.absolute()
                        or resolved == ops_dir or ops_dir in resolved.parents):
                    continue
                seen.add(resolved)
                paths.append(resolved.relative_to(root).as_posix())
        owners = source_attachment_owners(root, paths)
        for rel in paths:
            try:
                if rel in owners:
                    # Do not parse even valid frontmatter in copied original evidence.
                    content = (root / rel).read_bytes().decode("utf-8", errors="replace")
                    metadata = {"type": "source", "status": "raw", "evidence_owner": owners[rel]}
                else:
                    post = frontmatter.load(str(root / rel))
                    metadata = dict(post.metadata)
                    content = post.content or ""
                objects.append(_make_object(root, config, rel, metadata, content))
            except Exception as exc:
                diagnostics.append(SnapshotDiagnostic(
                    path=rel, code="frontmatter-parse-error", message=str(exc),
                ))

        return cls(root=root, objects=tuple(objects), diagnostics=tuple(diagnostics))

    @classmethod
    def from_objects(
        cls,
        vault_root: Path | str,
        objects: Iterable[dict[str, Any]],
        config: dict | None = None,
    ) -> "VaultSnapshot":
        root = Path(vault_root).expanduser().resolve()
        config = config or load_config(root)
        objects = list(objects)
        owners = source_attachment_owners(root, (str(obj["path"]) for obj in objects))
        converted = []
        for obj in objects:
            rel = str(obj["path"])
            candidate = root / rel
            if (not candidate.resolve().is_relative_to(root)
                    or candidate.resolve() != candidate.absolute()):
                continue
            metadata = dict(obj.get("frontmatter") or {})
            content = str(obj.get("content") or "")
            if rel in owners:
                metadata = {"type": "source", "status": "raw", "evidence_owner": owners[rel]}
                content = candidate.read_bytes().decode("utf-8", errors="replace")
            else:
                for key in ("type", "status"):
                    if key not in metadata and obj.get(key) not in (None, "", "unknown"):
                        metadata[key] = obj[key]
            converted.append(_make_object(root, config, rel, metadata, content,
                                          obj.get("wikilinks"),
                                          None if rel in owners else obj.get("title")))
        return cls(root=root, objects=tuple(converted))


def _make_object(root, config, path, metadata, content, preextracted=None, fallback_title=None):
    """Normalize capture semantics once for disk scans and pipeline objects."""
    metadata = dict(metadata)
    if is_plain_inbox_source(path, metadata, root, config):
        metadata.update(type="source", status="raw")
    if is_raw_source(metadata):
        links = extract_frontmatter_links(metadata, include_plain_strings=True)
    elif preextracted:
        links = list(preextracted)
    else:
        links = extract_wikilinks(content)
        links.extend(extract_frontmatter_links(metadata, include_plain_strings=True))
    return VaultObject(
        path=path, title=str(metadata.get("title") or fallback_title or Path(path).stem),
        type=str(metadata.get("type") or "unknown"),
        status=str(metadata.get("status") or "unknown"),
        frontmatter=MappingProxyType(metadata), content=content, links=tuple(links),
    )
