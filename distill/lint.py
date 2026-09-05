"""Vault linter with auto-fix capabilities."""

import fnmatch
import re
import subprocess
from pathlib import Path
from collections import defaultdict

import frontmatter

from .atomic_io import atomic_write_text
from .config import load_config, resolve_path_type, resolve_type_status
from .index import VaultIndex
from .next_steps import guidance_from_lint
from .schema import validate_snapshot
from .vault_semantics import (
    PRESENTATION_SECTIONS,
    WIKILINK_RE,
    extract_h2_headings,
    should_ignore_broken_link,
)

# Chinese → English type mapping
TYPE_MAP = {
    "来源": "source",
    "项目": "project",
    "实体": "entity",
    "概念": "concept",
    "输出": "output",
    "决策": "decision",
    "约束": "constraint",
    "任务": "task",
    "分析": "analysis",
}


class VaultLinter:
    def __init__(self, vault_root: Path, config=None, snapshot=None):
        self.vault = Path(vault_root)
        self.config = config or load_config(self.vault)
        self.index = VaultIndex(vault_root, config=self.config, snapshot=snapshot)
        self.issues = []
        self._fixes_applied = []

    def scan(self):
        self.index.scan()

    def lint(self, fix=False, staged=False, paths=None):
        if paths:
            if fix or staged:
                raise ValueError("--paths cannot be combined with --fix or --staged")
            return self._lint_paths(paths)
        self._check_broken_links()
        self._check_orphans()
        self._check_frontmatter_completeness()
        self._check_type_consistency()
        self._check_schema()
        self._check_presentation_contracts()
        if staged:
            staged_files = self._get_staged_files()
            self.issues = [issue for issue in self.issues if self._issue_matches_staged(issue, staged_files)]
        if fix:
            self._auto_fix()
        return self.issues

    def _lint_paths(self, paths):
        """Validate selected objects, retaining the full index only for link lookup.

        Selection happens before schema validation and diagnostic limits, not
        after whole-vault lint. Deleted files have no schema/body to validate.
        """
        from .snapshot import VaultSnapshot
        root = self.vault.resolve()
        selected = []
        for value in paths:
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts or value.startswith(":") or any(c in value for c in "*?[]"):
                raise ValueError(f"expected literal vault-relative path: {value}")
            resolved = (root / path).resolve()
            if not resolved.is_relative_to(root):
                raise ValueError(f"path escapes vault: {value}")
            selected.append(path.as_posix().rstrip("/"))
        tracked = subprocess.run(["git", "ls-files", "--deleted", "-z", "--", *selected],
                                 cwd=root, capture_output=True, text=True)
        staged_deleted = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=D", "--no-renames", "-z", "--", *selected],
                                       cwd=root, capture_output=True, text=True)
        if tracked.stdout or staged_deleted.stdout:
            raise ValueError("scoped validation does not support deletions; use full-vault commit to validate incoming links")
        def matches(path):
            return any(scope == "." or path == scope or path.startswith(scope + "/") for scope in selected)
        snapshot = self.index.snapshot
        if snapshot is None:
            raise ValueError("scan must be called before lint")
        subset = VaultSnapshot(root, tuple(obj for obj in snapshot.objects if matches(obj.path)),
                               tuple(d for d in snapshot.diagnostics if matches(d.path)))
        scoped = VaultLinter(root, config=self.config, snapshot=subset)
        scoped.index.objects = [obj for obj in self.index.objects if matches(obj["path"])]
        # All targets remain visible, but unrelated broken links are never checked
        # or allowed to consume the diagnostic budget.
        for link in self.index.broken_links:
            if matches(link["from"]):
                scoped.issues.append({"severity": "error", "rule": "broken-wikilink",
                    "message": f"Broken link: [[{link['to']}]] in {link['from']}",
                    "file": link["from"], "link": link["to"]})
        scoped.issues.extend({"severity": d.severity, "rule": d.code,
                              "file": d.path, "message": d.message} for d in subset.diagnostics)
        scoped._check_frontmatter_completeness()
        scoped._check_type_consistency()
        scoped._check_schema()
        scoped._check_presentation_contracts()
        self.issues = scoped.issues
        return self.issues

    def _check_broken_links(self):
        for bl in self.index.broken_links[:50]:
            self.issues.append({
                "severity": "error",
                "rule": "broken-wikilink",
                "message": f"Broken link: [[{bl['to']}]] in {bl['from']}",
                "file": bl["from"],
                "link": bl["to"],
            })

    def _check_orphans(self):
        for op in self.index.orphans[:20]:
            bucket = "true_orphan"
            for name, paths in self.index.orphan_buckets.items():
                if op in paths:
                    bucket = name
                    break
            informational_messages = {
                "raw_inbox": f"Raw inbox source (no classification required): {op}",
                "system_doc": f"System doc (informational): {op}",
                "timeline_archive": f"Timeline archive (informational): {op}",
            }
            severity = "info" if bucket in informational_messages else "warning"
            message = informational_messages.get(bucket, f"Orphan object: {op}")
            self.issues.append({
                "severity": severity,
                "rule": "orphan-object",
                "message": message,
                "file": op,
                "orphan_bucket": bucket,
            })

    def _check_frontmatter_completeness(self):
        required = {"title", "type", "status"}
        for obj in self.index.objects:
            if not self._requires_frontmatter(obj["path"]):
                continue
            fm = obj.get("frontmatter", {})
            missing = required - set(fm.keys())
            if missing:
                self.issues.append({
                    "severity": "warning",
                    "rule": "incomplete-frontmatter",
                    "message": f"Missing frontmatter fields: {missing}",
                    "file": obj["path"],
                })

    def _check_type_consistency(self):
        valid_types = set(self.config.get("objects", {}).get("types", [])) | {"unknown"}
        for obj in self.index.objects:
            t = obj.get("type", "")
            if t and t not in valid_types:
                self.issues.append({
                    "severity": "warning",
                    "rule": "unknown-type",
                    "message": f"Unknown type '{t}'",
                    "file": obj["path"],
                    "current_type": t,
                })

    def _check_schema(self):
        if self.index.snapshot is None:
            return
        try:
            schema_issues = validate_snapshot(self.index.snapshot, self.config)
        except (FileNotFoundError, ValueError) as exc:
            self.issues.append({
                "severity": "error",
                "rule": "schema-configuration",
                "message": str(exc),
                "file": "distill.yaml",
            })
            return
        self.issues.extend(issue.as_dict() for issue in schema_issues)

    def _check_presentation_contracts(self):
        """Check body sections only for objects that opt into a presentation contract."""
        for obj in self.index.objects:
            metadata = obj.get("frontmatter", {})
            presentation = metadata.get("presentation")
            localized_sections = PRESENTATION_SECTIONS.get(presentation)
            if localized_sections is None:
                continue
            path = obj["path"]
            snapshot_obj = self.index.snapshot.by_path.get(path) if self.index.snapshot else None
            if snapshot_obj is None:
                continue
            actual = extract_h2_headings(snapshot_obj.content)
            if any(set(headings).issubset(actual) for headings in localized_sections.values()):
                continue
            expected = " / ".join("、".join(headings) for headings in localized_sections.values())
            self.issues.append({
                "severity": "warning",
                "rule": "incomplete-presentation-contract",
                "message": f"Presentation '{presentation}' requires one complete heading set: {expected}",
                "file": path,
            })

    def _get_staged_files(self) -> set[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                cwd=self.vault,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return set()
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _issue_matches_staged(self, issue: dict, staged_files: set[str]) -> bool:
        if not staged_files:
            return False
        file_path = issue.get("file")
        if not file_path:
            return False
        return file_path in staged_files

    def _auto_fix(self):
        """Apply automatic fixes to vault files."""
        # Build resolution tables
        title_to_path = {obj["title"]: obj["path"] for obj in self.index.objects}
        path_to_obj = {obj["path"]: obj for obj in self.index.objects}
        filename_to_path = {}
        for obj in self.index.objects:
            fname = Path(obj["path"]).stem
            if fname not in filename_to_path:
                filename_to_path[fname] = obj["path"]

        # Build set of broken link targets per file
        broken_per_file = defaultdict(set)
        for bl in self.index.broken_links:
            broken_per_file[bl["from"]].add(bl["to"])

        # Process each markdown file
        for obj in self.index.objects:
            file_path = self.vault / obj["path"]
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8")
            original = content
            file_rel = obj["path"]

            # Fix 1: Chinese types in frontmatter (safe for all files)
            content = self._fix_frontmatter_types(content)

            # Fix 2: Non-markdown file references in wikilink brackets (safe)
            content = self._fix_non_md_wikilinks(content)

            # Fix 3: [[target|alias]] → [[target]] (safe)
            content = self._fix_alias_wikilinks(content)

            # Fix 4: Only fix actually broken wikilinks
            if file_rel in broken_per_file:
                broken_targets = broken_per_file[file_rel]
                content = self._fix_specific_broken_links(
                    content, broken_targets, title_to_path, filename_to_path
                )

            # Fix 5: Frontmatter completeness (status/type/title)
            if self._requires_frontmatter(file_rel):
                content = self._fix_frontmatter_completeness(file_rel, content)

            if content != original:
                atomic_write_text(file_path, content, root=self.vault)
                self._fixes_applied.append(file_rel)

        if self._fixes_applied:
            # Re-index after fixes
            self.index = VaultIndex(self.vault, config=self.config)
            self.index.scan()
            self.issues = []
            self._check_broken_links()
            self._check_orphans()
            self._check_frontmatter_completeness()
            self._check_type_consistency()
            self._check_schema()
            self._check_presentation_contracts()

    def _fix_frontmatter_types(self, content: str) -> str:
        """Replace Chinese type values with English in frontmatter."""
        for cn, en in TYPE_MAP.items():
            content = re.sub(
                rf'^(type:\s*){re.escape(cn)}\s*$',
                rf'\1{en}',
                content,
                flags=re.MULTILINE,
            )
        return content

    def _fix_specific_broken_links(self, content: str, broken_targets: set,
                                   title_to_path: dict, filename_to_path: dict) -> str:
        """Only fix wikilinks that are known to be broken."""
        def replacer(m):
            link = m.group(1)
            # Skip alias syntax
            if "|" in link:
                return m.group(0)
            # Only process known broken targets
            if link not in broken_targets:
                return m.group(0)

            # Try exact title match
            if link in title_to_path:
                return m.group(0)  # Shouldn't happen if broken, but be safe

            # Try filename match
            if link in filename_to_path:
                return m.group(0)

            # Try path match
            candidate = link + ".md" if not link.endswith(".md") else link
            if candidate in filename_to_path:
                return m.group(0)

            # Try fuzzy match: find object with similar title
            best_match = None
            best_score = 0
            for title, path in title_to_path.items():
                if link in title or title in link:
                    score = len(set(link) & set(title))
                    if score > best_score:
                        best_score = score
                        best_match = title

            if best_match:
                return f"[[{best_match}]]"

            # Can't fix - leave as is
            return m.group(0)

        return WIKILINK_RE.sub(replacer, content)

    def _fix_non_md_wikilinks(self, content: str) -> str:
        """Remove wikilink brackets around non-markdown file references."""
        def replacer(m):
            link = m.group(1)
            if "|" in link:
                link = link.split("|")[0]
            if should_ignore_broken_link(link):
                return link
            return m.group(0)
        return WIKILINK_RE.sub(replacer, content)

    def _fix_alias_wikilinks(self, content: str) -> str:
        """Convert [[target|alias]] to [[target]]."""
        def replacer(m):
            link = m.group(1)
            if "|" in link:
                target = link.split("|")[0]
                return f"[[{target}]]"
            return m.group(0)
        return WIKILINK_RE.sub(replacer, content)

    def _fix_frontmatter_completeness(self, file_rel: str, content: str) -> str:
        """Infer and fill missing frontmatter fields."""
        try:
            post = frontmatter.loads(content)
        except Exception:
            return content

        fm = dict(post.metadata)
        modified = False

        # Infer type from path if missing
        if not fm.get("type") or fm.get("type") == "unknown":
            inferred = self._infer_type_from_path(file_rel)
            if inferred and inferred != "unknown":
                fm["type"] = inferred
                modified = True

        # Infer status from type if missing
        if not fm.get("status") or fm.get("status") == "unknown":
            inferred = self._infer_status_from_type(fm.get("type", "unknown"))
            fm["status"] = inferred
            modified = True

        # Infer title from filename if missing
        if not fm.get("title"):
            fname = Path(file_rel).stem
            # Remove date prefix like 2026-04-12-
            title = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', fname)
            title = title.replace('-', ' ').replace('_', ' ')
            fm["title"] = title
            modified = True

        if modified:
            post.metadata = fm
            return frontmatter.dumps(post)
        return content

    def _infer_type_from_path(self, path: str) -> str:
        """Infer object type from file path."""
        return resolve_path_type(path, self.config)

    def _infer_status_from_type(self, obj_type: str) -> str:
        """Infer status from object type."""
        resolved = resolve_type_status(obj_type, self.config)
        return resolved if resolved != "unknown" else "draft"

    def _requires_frontmatter(self, path: str) -> bool:
        """Whether a file should be held to object-card frontmatter rules."""
        normalized = path.replace("\\", "/")
        explicit_globs = self.config.get("lint", {}).get("frontmatter_required_globs")
        if explicit_globs is not None:
            return any(fnmatch.fnmatch(normalized, pattern) for pattern in explicit_globs)

        obj_type = resolve_path_type(normalized, self.config)
        return obj_type != "unknown" and obj_type != "output"

    def recommended_next_steps(self, issues=None):
        return guidance_from_lint(self.issues if issues is None else issues, vault_root=self.vault)

    def get_fix_report(self) -> str:
        if not self._fixes_applied:
            return "No fixes applied."
        lines = [f"Applied fixes to {len(self._fixes_applied)} file(s):"]
        for fix in self._fixes_applied[:20]:
            lines.append(f"  - {fix}")
        if len(self._fixes_applied) > 20:
            lines.append(f"  ... and {len(self._fixes_applied) - 20} more")
        return "\n".join(lines)
