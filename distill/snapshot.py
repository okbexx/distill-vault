"""Single-pass immutable representation of a Markdown vault."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import frontmatter

from .config import get_ops_dir, get_scan_dirs, load_config
from .vault_semantics import extract_frontmatter_links, extract_wikilinks


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

        for scan_root in get_scan_dirs(config, root):
            for path in sorted(scan_root.rglob("*.md")):
                resolved = path.resolve()
                if resolved in seen or resolved == ops_dir or ops_dir in resolved.parents:
                    continue
                seen.add(resolved)
                rel = resolved.relative_to(root).as_posix()
                try:
                    post = frontmatter.load(str(resolved))
                except Exception as exc:
                    diagnostics.append(SnapshotDiagnostic(
                        path=rel,
                        code="frontmatter-parse-error",
                        message=str(exc),
                    ))
                    continue

                metadata = dict(post.metadata)
                content = post.content or ""
                links = extract_wikilinks(content)
                links.extend(extract_frontmatter_links(metadata, include_plain_strings=True))
                objects.append(VaultObject(
                    path=rel,
                    title=str(metadata.get("title") or resolved.stem),
                    type=str(metadata.get("type") or "unknown"),
                    status=str(metadata.get("status") or "unknown"),
                    frontmatter=MappingProxyType(metadata),
                    content=content,
                    links=tuple(links),
                ))

        return cls(root=root, objects=tuple(objects), diagnostics=tuple(diagnostics))

    @classmethod
    def from_objects(
        cls,
        vault_root: Path | str,
        objects: Iterable[dict[str, Any]],
    ) -> "VaultSnapshot":
        root = Path(vault_root).expanduser().resolve()
        converted = []
        for obj in objects:
            metadata = dict(obj.get("frontmatter") or {})
            links = list(obj.get("wikilinks") or [])
            if not links:
                links = extract_wikilinks(obj.get("content") or "")
                links.extend(extract_frontmatter_links(metadata, include_plain_strings=True))
            converted.append(VaultObject(
                path=str(obj["path"]),
                title=str(obj.get("title") or Path(str(obj["path"])).stem),
                type=str(obj.get("type") or "unknown"),
                status=str(obj.get("status") or "unknown"),
                frontmatter=MappingProxyType(metadata),
                content=str(obj.get("content") or ""),
                links=tuple(links),
            ))
        return cls(root=root, objects=tuple(converted))
