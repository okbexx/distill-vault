"""Vault indexing engine."""

import json
from pathlib import Path
from collections import defaultdict

from distill.atomic_io import atomic_write_text
from distill.config import load_config, get_scan_dirs, get_ops_dir
from distill.snapshot import VaultSnapshot
from distill.vault_semantics import (
    build_lookup_indexes,
    classify_orphan_path,
    extract_frontmatter_links,
    extract_wikilinks,
    resolve_existing_vault_asset,
    resolve_link_target,
    should_ignore_broken_link,
)
from distill.next_steps import guidance_from_index, render_next_steps_markdown


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class VaultIndex:
    def __init__(self, vault_root: Path, config=None, snapshot: VaultSnapshot | None = None):
        self.root = Path(vault_root).expanduser().resolve()
        self.config = config or load_config(self.root)
        self.objects = []
        self.wikilinks = defaultdict(list)
        self.backlinks = defaultdict(list)
        self.broken_links = []
        self.orphans = []
        self.orphan_buckets = {"true_orphan": [], "system_doc": [], "timeline_archive": []}
        self.stats = {}
        self._has_checkpoint_override = None
        self.snapshot = snapshot

    def scan(self):
        """Scan all markdown files under configured scan directories."""
        self.objects = []
        self.wikilinks = defaultdict(list)
        self.backlinks = defaultdict(list)
        self.broken_links = []
        self.orphans = []
        self.orphan_buckets = {"true_orphan": [], "system_doc": [], "timeline_archive": []}
        self.snapshot = self.snapshot or VaultSnapshot.scan(self.root, config=self.config)
        for obj in self.snapshot.objects:
            self._index_object(obj)
        self._analyze()

    def _index_object(self, snapshot_object):
        rel = snapshot_object.path
        obj = {
            "path": rel,
            "title": snapshot_object.title,
            "type": snapshot_object.type,
            "status": snapshot_object.status,
            "frontmatter": _json_safe(dict(snapshot_object.frontmatter)),
        }
        self.objects.append(obj)
        for link in snapshot_object.links:
            self.wikilinks[rel].append(link)
            self.backlinks[link].append(rel)

    def _analyze(self):
        # Build lookup tables
        path_index, title_index, filename_index = build_lookup_indexes(self.objects)
        self._title_index = title_index
        self._path_index = path_index

        # Resolve wikilinks
        resolved_backlinks = defaultdict(set)
        for src, targets in self.wikilinks.items():
            for t in targets:
                resolved_target = resolve_link_target(
                    t,
                    path_index=path_index,
                    title_index=title_index,
                    filename_index=filename_index,
                )
                if resolved_target:
                    resolved_backlinks[resolved_target].add(src)
                    continue
                if resolve_existing_vault_asset(t, self.root):
                    continue
                if should_ignore_broken_link(t):
                    continue
                self.broken_links.append({"from": src, "to": t})

        self.backlinks = defaultdict(list, {key: sorted(value) for key, value in resolved_backlinks.items()})
        linked = set(self.backlinks.keys())

        # Orphans
        for obj in self.objects:
            p = obj["path"]
            has_out = len(self.wikilinks.get(p, [])) > 0
            has_in = p in linked
            if not has_out and not has_in:
                bucket = classify_orphan_path(p, obj.get("frontmatter"))
                self.orphan_buckets.setdefault(bucket, []).append(p)
                self.orphans.append(p)
        # Stats
        type_counts = defaultdict(int)
        status_counts = defaultdict(int)
        for obj in self.objects:
            type_counts[obj["type"]] += 1
            status_counts[obj["status"]] += 1
        self.stats = {
            "total_objects": len(self.objects),
            "type_distribution": dict(sorted(type_counts.items())),
            "status_distribution": dict(sorted(status_counts.items())),
            "total_wikilinks": sum(len(v) for v in self.wikilinks.values()),
            "broken_links": len(self.broken_links),
            "orphan_objects": len(self.orphans),
            "true_orphans": len(self.orphan_buckets.get("true_orphan", [])),
            "system_docs": len(self.orphan_buckets.get("system_doc", [])),
            "timeline_archives": len(self.orphan_buckets.get("timeline_archive", [])),
        }

    def recommended_next_steps(self):
        return guidance_from_index(self)

    def has_checkpoint(self) -> bool:
        if self._has_checkpoint_override is not None:
            return bool(self._has_checkpoint_override)
        return (self.root / ".distill" / "checkpoint.json").exists()

    def runtime_stage(self) -> str:
        has_checkpoint = self.has_checkpoint()
        if not has_checkpoint:
            return "preflight"
        if self.stats.get("broken_links", 0) or self.stats.get("true_orphans", 0):
            return "needs_attention"
        return "trusted_runtime"

    def scan_roots(self) -> list[str]:
        roots = []
        for path in get_scan_dirs(self.config, self.root):
            try:
                rel = path.relative_to(self.root)
                normalized = rel.as_posix()
                roots.append(normalized if normalized else ".")
            except ValueError:
                roots.append(str(path))
        return roots

    def vault_layout_payload(self) -> dict:
        return {
            "knowledge_dirs": list(self.config.get("vault", {}).get("knowledge_dirs", [])),
            "output_dirs": list(self.config.get("vault", {}).get("output_dirs", [])),
            "ops_dirs": list(self.config.get("vault", {}).get("ops_dirs", [])),
            "system_dirs": list(self.config.get("vault", {}).get("system_dirs", [])),
        }

    def status_payload(self) -> dict:
        payload = dict(self.stats)
        payload["runtime_stage"] = self.runtime_stage()
        payload["has_checkpoint"] = self.has_checkpoint()
        payload["scan_roots"] = self.scan_roots()
        payload["vault_layout"] = self.vault_layout_payload()
        payload["next_steps"] = self.recommended_next_steps()
        return payload

    def auto_index_payload(self) -> dict:
        return {
            "objects": sorted(self.objects, key=lambda obj: obj.get("path", "")),
            "stats": dict(self.stats),
            "broken_links": sorted(
                self.broken_links,
                key=lambda item: (item.get("from", ""), item.get("to", "")),
            ),
            "orphans": sorted(self.orphans),
            "orphan_buckets": {
                key: sorted(value)
                for key, value in sorted(self.orphan_buckets.items())
            },
            "runtime_stage": self.runtime_stage(),
            "has_checkpoint": self.has_checkpoint(),
            "scan_roots": self.scan_roots(),
            "vault_layout": self.vault_layout_payload(),
            "next_steps": self.recommended_next_steps(),
        }

    def report(self) -> str:
        lines = []
        lines.append("=" * 50)
        lines.append("distill-vault Index Report")
        lines.append("=" * 50)
        lines.append("")
        lines.append("[Overview]")
        lines.append(f"  runtime_stage: {self.runtime_stage()}")
        for k, v in self.stats.items():
            if isinstance(v, dict):
                lines.append(f"  {k}:")
                for kk, vv in v.items():
                    lines.append(f"    {kk}: {vv}")
            else:
                lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("[Vault Layout]")
        for key, value in self.status_payload()["vault_layout"].items():
            lines.append(f"  {key}: {value}")
        lines.append(f"  scan_roots: {self.scan_roots()}")
        lines.append("")
        if self.broken_links:
            lines.append(f"[Broken Links] ({len(self.broken_links)} total)")
            for bl in self.broken_links[:10]:
                lines.append(f"  {bl['from']} -> [[{bl['to']}]]")
            if len(self.broken_links) > 10:
                lines.append(f"  ... and {len(self.broken_links)-10} more")
            lines.append("")
        if self.orphans:
            true_orphans = self.orphan_buckets.get("true_orphan", [])
            system_docs = self.orphan_buckets.get("system_doc", [])
            timeline_archives = self.orphan_buckets.get("timeline_archive", [])
            lines.append(f"[Orphans] ({len(self.orphans)} total)")
            if true_orphans:
                lines.append(f"  True Orphans ({len(true_orphans)}):")
                for op in true_orphans[:10]:
                    lines.append(f"    {op}")
                if len(true_orphans) > 10:
                    lines.append(f"    ... and {len(true_orphans)-10} more")
            if system_docs:
                lines.append(f"  System Docs ({len(system_docs)}):")
                for op in system_docs[:10]:
                    lines.append(f"    {op}")
                if len(system_docs) > 10:
                    lines.append(f"    ... and {len(system_docs)-10} more")
            if timeline_archives:
                lines.append(f"  Timeline Archives ({len(timeline_archives)}):")
                for op in timeline_archives[:10]:
                    lines.append(f"    {op}")
                if len(timeline_archives) > 10:
                    lines.append(f"    ... and {len(timeline_archives)-10} more")
            lines.append("")
        guidance = render_next_steps_markdown(self.recommended_next_steps(), heading="[Recommended Next Steps]")
        if guidance:
            lines.append(guidance)
            lines.append("")
        return "\n".join(lines)

    def save(self):
        ops_dir = get_ops_dir(self.config, self.root) / "索引"
        ops_dir.mkdir(parents=True, exist_ok=True)
        idx_path = ops_dir / "auto-index.json"
        def _default(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        content = json.dumps(
            self.auto_index_payload(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_default,
        )
        atomic_write_text(idx_path, content, root=self.root)
        return idx_path
