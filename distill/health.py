"""Health checker."""

import json
from pathlib import Path
from .index import VaultIndex
from .next_steps import render_next_steps_markdown


class HealthChecker:
    def __init__(self, vault_root: Path, config=None, snapshot=None):
        self.vault = Path(vault_root)
        self.index = VaultIndex(vault_root, config=config, snapshot=snapshot)

    def scan(self):
        self.index.scan()

    def recommended_next_steps(self):
        return self.index.recommended_next_steps()

    def report(self, fmt="markdown") -> str:
        stats = self.index.stats
        if fmt == "json":
            return json.dumps(self.index.status_payload(), ensure_ascii=False, indent=2)
        payload = self.index.status_payload()
        lines = []
        lines.append("# Health Report")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Runtime stage: {payload['runtime_stage']}")
        lines.append(f"- Total objects: {stats['total_objects']}")
        lines.append(f"- Total wikilinks: {stats['total_wikilinks']}")
        lines.append(f"- Broken links: {stats['broken_links']}")
        lines.append(f"- Orphan objects: {stats['orphan_objects']}")
        lines.append(f"- True orphans: {stats.get('true_orphans', 0)}")
        lines.append(f"- System docs: {stats.get('system_docs', 0)}")
        lines.append(f"- Timeline archives: {stats.get('timeline_archives', 0)}")
        lines.append("")
        lines.append("## Vault Layout")
        for key, value in payload.get("vault_layout", {}).items():
            lines.append(f"- {key}: {value}")
        lines.append(f"- scan_roots: {payload.get('scan_roots', [])}")
        lines.append("")
        lines.append("## Type Distribution")
        for t, c in stats.get("type_distribution", {}).items():
            lines.append(f"- {t}: {c}")
        lines.append("")
        lines.append("## Status Distribution")
        for s, c in stats.get("status_distribution", {}).items():
            lines.append(f"- {s}: {c}")
        lines.append("")
        if stats["broken_links"] > 50:
            lines.append("⚠️ **High broken link count - consider running `distill lint --fix`**")
        if stats.get("true_orphans", 0) > 20:
            lines.append("⚠️ **High true orphan count - consider linking these objects**")
        guidance = render_next_steps_markdown(self.recommended_next_steps())
        if guidance:
            lines.append(guidance)
        return "\n".join(lines)
