"""Graph-based intelligent rename for vault objects.

Uses the graph index for high-confidence inbound references and falls back to
text search for wikilinks in markdown files. Supports dry-run previews and
optional file moves with git-aware rename behavior.
"""

from __future__ import annotations

import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .atomic_io import atomic_write_text
from .config import get_scan_dirs, load_config
from .graph_index import GraphIndex
from .index import VaultIndex


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class GraphRename:
    """Smart rename helper backed by the graph database and vault index."""

    def __init__(self, vault_root: Path, graph_index: Optional[GraphIndex] = None, config=None):
        self.vault = Path(vault_root).expanduser().resolve()
        self.config = config or load_config(self.vault)
        self.graph = graph_index or GraphIndex(self.vault)
        self.index = VaultIndex(self.vault, config=self.config)
        self.index.scan()

    def rename(
        self,
        old_name_or_path: str,
        new_name: str,
        *,
        dry_run: bool = True,
        rename_file: bool = False,
    ) -> Dict:
        old_path, old_title = self._resolve_target(old_name_or_path)
        if old_path is None or old_title is None:
            raise ValueError(f"Object not found: {old_name_or_path}")

        if self._is_protected_path(old_path):
            raise ValueError(f"Refusing to rename protected file under 系统/: {old_path}")

        graph_refs = self._find_graph_references(old_path)
        text_refs = self._find_text_references(old_title, old_path)
        changes = self._merge_references(graph_refs, text_refs, old_title, old_path, new_name)

        file_renamed = False
        new_path = old_path
        if rename_file:
            new_path = self._build_new_path(old_path, new_name)
            if self._is_protected_path(new_path):
                raise ValueError(f"Refusing to move file into protected 系统/ path: {new_path}")

        if not dry_run:
            self._apply_changes(changes)
            if rename_file and new_path != old_path:
                self._rename_file(old_path, new_path)
                file_renamed = True
        else:
            file_renamed = bool(rename_file and new_path != old_path)

        return {
            "old_name": old_title,
            "new_name": new_name,
            "file_renamed": file_renamed,
            "old_path": old_path,
            "new_path": new_path,
            "changes": changes,
            "total_changes": len(changes),
            "dry_run": dry_run,
        }

    def _resolve_target(self, old_name_or_path: str) -> Tuple[Optional[str], Optional[str]]:
        raw = (old_name_or_path or "").strip()
        if not raw:
            return None, None

        candidate_path = raw
        if candidate_path in self.index._path_index:
            obj = self.index._path_index[candidate_path]
            return obj["path"], obj.get("title") or Path(obj["path"]).stem

        normalized = raw if raw.endswith(".md") else f"{raw}.md"
        if normalized in self.index._path_index:
            obj = self.index._path_index[normalized]
            return obj["path"], obj.get("title") or Path(obj["path"]).stem

        if raw in self.index._title_index:
            path = self.index._title_index[raw]
            obj = self.index._path_index[path]
            return path, obj.get("title") or Path(path).stem

        for path, obj in self.index._path_index.items():
            if Path(path).stem == raw:
                return path, obj.get("title") or Path(path).stem

        return None, None

    def _find_graph_references(self, old_path: str) -> List[Tuple[str, str]]:
        return [
            (row["path"], row.get("relation") or "wikilink")
            for row in self.graph.incoming(old_path)
        ]

    def _find_text_references(self, old_title: str, old_path: str) -> List[Tuple[str, int, str, str]]:
        refs: List[Tuple[str, int, str, str]] = []
        stem = Path(old_path).stem
        aliases: Set[str] = {old_title, old_path, stem}
        aliases.add(old_path[:-3] if old_path.endswith(".md") else old_path)

        for md_path in self._iter_markdown_files():
            rel_path = str(md_path.relative_to(self.vault))
            if self._is_protected_path(rel_path):
                continue
            try:
                lines = md_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line_no, line in enumerate(lines, start=1):
                for match in WIKILINK_RE.finditer(line):
                    inner = match.group(1)
                    target = inner.split("|", 1)[0].strip()
                    if target in aliases:
                        refs.append((rel_path, line_no, match.group(0), inner))
        return refs

    def _merge_references(
        self,
        graph_refs: List[Tuple[str, str]],
        text_refs: List[Tuple[str, int, str, str]],
        old_title: str,
        old_path: str,
        new_name: str,
    ) -> List[Dict]:
        graph_files = {path for path, _ in graph_refs if not self._is_protected_path(path)}
        changes: List[Dict] = []
        seen = set()

        for rel_path, line_no, old_text, inner in text_refs:
            if self._is_protected_path(rel_path):
                continue
            new_text = self._rewrite_wikilink(inner, old_title, old_path, new_name)
            key = (rel_path, line_no, old_text, new_text)
            if old_text == new_text or key in seen:
                continue
            seen.add(key)
            changes.append(
                {
                    "file": rel_path,
                    "line": line_no,
                    "old_text": old_text,
                    "new_text": new_text,
                    "confidence": "graph" if rel_path in graph_files else "text_search",
                }
            )

        changes.sort(key=lambda item: (item["file"], item["line"], item["old_text"]))
        return changes

    def _rewrite_wikilink(self, inner: str, old_title: str, old_path: str, new_name: str) -> str:
        target, sep, display = inner.partition("|")
        target = target.strip()
        aliases = {
            old_title,
            old_path,
            Path(old_path).stem,
            old_path[:-3] if old_path.endswith(".md") else old_path,
        }
        if target not in aliases:
            return f"[[{inner}]]"
        if sep:
            return f"[[{new_name}|{display}]]"
        return f"[[{new_name}]]"

    def _apply_changes(self, changes: List[Dict]) -> None:
        grouped: Dict[str, List[Dict]] = {}
        for change in changes:
            grouped.setdefault(change["file"], []).append(change)

        for rel_path, file_changes in grouped.items():
            abs_path = self.vault / rel_path
            original = abs_path.read_text(encoding="utf-8")
            updated = original
            ordered = sorted(file_changes, key=lambda item: len(item["old_text"]), reverse=True)
            for change in ordered:
                updated = updated.replace(change["old_text"], change["new_text"])
            if updated != original:
                atomic_write_text(abs_path, updated, root=self.vault)

    def _rename_file(self, old_path: str, new_path: str) -> None:
        old_abs = self.vault / old_path
        new_abs = self.vault / new_path
        if not old_abs.exists():
            raise FileNotFoundError(f"Source file does not exist: {old_path}")
        if new_abs.exists():
            raise FileExistsError(f"Destination already exists: {new_path}")
        new_abs.parent.mkdir(parents=True, exist_ok=True)
        if self._is_git_repo():
            subprocess.run(["git", "mv", str(old_abs), str(new_abs)], check=True, cwd=self.vault)
        else:
            old_abs.rename(new_abs)

    def _build_new_path(self, old_path: str, new_name: str) -> str:
        return str(Path(old_path).with_name(f"{new_name}.md"))

    def _iter_markdown_files(self):
        for root in get_scan_dirs(self.config, self.vault):
            yield from root.rglob("*.md")

    def _is_protected_path(self, rel_path: str) -> bool:
        normalized = str(rel_path).replace("\\", "/")
        for system_dir in self.config.get("vault", {}).get("system_dirs", []):
            if normalized == system_dir or normalized.startswith(f"{system_dir}/"):
                return True
        return False

    def _is_git_repo(self) -> bool:
        try:
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.vault,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True
        except Exception:
            return False
