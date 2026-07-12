"""Promotion discovery plus guarded semantic proposal review and apply."""

import re
from pathlib import Path
from collections import defaultdict
from typing import Any, TypedDict

import frontmatter
from jsonschema import Draft202012Validator

from .atomic_io import atomic_write_text
from .config import load_config, resolve_path_type
from .index import VaultIndex
from .schema import _json_instance, load_object_schema
from .atomic_io import resolve_guarded_path


# Promotion rules: source_type → suggested target type
SOURCE_TYPE_PROMOTION = {
    "conversation": "concept",
    "article": "concept",
    "github": "project",
    "documentation": "concept",
    "video": "concept",
    "tweet": "concept",
    "weekly": "output",
    "daily": "output",
}

# Keywords that suggest a decision
DECISION_KEYWORDS = [
    "决定", "选择", "采用", "弃用", "确定", "否决",
    "decide", "choose", "adopt", "drop", "settle", "reject",
    "方案", "对比", "优势", "劣势", "trade-off", "权衡",
]

# Keywords that suggest a concept
CONCEPT_KEYWORDS = [
    "框架", "模型", "原理", "方法", "模式", "理论",
    "framework", "model", "principle", "method", "pattern", "theory",
    "定义", "核心", "关键", "definition", "core", "key",
]

STABLE_PROMOTION_TYPES = {"concept", "decision", "constraint"}
SOURCE_RELATION_FIELDS = {
    "concept": "concepts",
    "decision": "decisions",
    "constraint": "constraints",
}


class PromotionReviewPayload(TypedDict):
    """Deterministic review result for one agent-authored semantic proposal."""

    status: str
    source: str
    target: str
    target_type: str | None
    title: str | None
    touched_paths: list[str]
    duplicate_paths: list[str]
    validation_errors: list[str]
    warnings: list[str]
    requires_confirmation: bool


class PromotionApplyPayload(TypedDict):
    """Applied result for a reviewed semantic promotion."""

    status: str
    source: str
    target: str
    target_type: str
    title: str
    touched_paths: list[str]


class PromotionPipeline:
    def __init__(self, vault_root: Path, config=None, snapshot=None):
        self.vault = Path(vault_root)
        self.config = config or load_config(self.vault)
        self.index = VaultIndex(vault_root, config=self.config, snapshot=snapshot)

        promote_config = self.config.get("promote", {})
        self._exclude_types = set(promote_config.get("exclude_types", []))
        self._min_backlinks = int(promote_config.get("min_backlinks", 2))
        self._min_words = int(promote_config.get("min_words", 100))

        # Resolve configured directory names
        vault_cfg = self.config.get("vault", {})
        self._knowledge_dir = self._first_dir(vault_cfg.get("knowledge_dirs"), "知识")
        self._output_dir = self._first_dir(vault_cfg.get("output_dirs"), "输出")

    @staticmethod
    def _first_dir(entries, default: str) -> str:
        if isinstance(entries, str):
            return entries
        if entries:
            return entries[0]
        return default

    def scan(self):
        self.index.scan()

    def plan(self, auto=False) -> list:
        """Generate promotion actions for raw sources."""
        self.actions = []

        # Build existing title/path sets for dedup
        existing_titles = {obj["title"].lower() for obj in self.index.objects}
        existing_paths = {obj["path"] for obj in self.index.objects}

        for obj in self.index.objects:
            if obj.get("type") != "source":
                continue

            fm = obj.get("frontmatter", {})
            content = self._read_content(obj["path"])
            if content is None:
                continue

            backlinks = len(self.index.backlinks.get(obj["path"], []))

            # Skip if already well-linked
            has_concepts = bool(fm.get("concepts") or fm.get("related_concepts"))
            has_decisions = bool(fm.get("decisions") or fm.get("related_decisions"))
            has_projects = bool(fm.get("projects") or fm.get("related_projects"))

            # Rule 1: Decision detection (skip configured excluded types)
            source_type = fm.get("source_type", "")
            fname = Path(obj["path"]).stem
            skip_extract = source_type in self._exclude_types or any(
                kw in fname for kw in ["日报", "周报", "碎碎念"]
            )

            if not skip_extract and not has_decisions and self._contains_keywords(content, DECISION_KEYWORDS):
                self.actions.append({
                    "type": "extract-decision",
                    "source": obj["path"],
                    "source_title": obj.get("title", ""),
                    "target": f"{self._knowledge_dir}/决策/{Path(obj['path']).stem}.md",
                    "reason": f"Source '{obj['title']}' contains decision keywords",
                    "confidence": "medium",
                    "auto_safe": False,
                })

            # Rule 2: Concept detection (skip configured excluded types)
            if not skip_extract and not has_concepts and self._contains_keywords(content, CONCEPT_KEYWORDS):
                self.actions.append({
                    "type": "extract-concept",
                    "source": obj["path"],
                    "source_title": obj.get("title", ""),
                    "target": f"{self._knowledge_dir}/概念/{Path(obj['path']).stem}.md",
                    "reason": f"Source '{obj['title']}' contains concept keywords",
                    "confidence": "medium",
                    "auto_safe": False,
                })

            # Rule 3: Source → Output promotion (daily/weekly logs)
            if source_type in ("daily", "weekly") and not has_projects:
                # Check if there's a corresponding output already
                output_name = Path(obj["path"]).stem
                output_path = f"{self._output_dir}/日志/{output_name}.md"
                if output_path not in existing_paths:
                    self.actions.append({
                        "type": "promote-to-output",
                        "source": obj["path"],
                        "source_title": obj.get("title", ""),
                        "target": output_path,
                        "reason": f"Daily/weekly log '{obj['title']}' should be promoted to output",
                        "confidence": "high",
                        "auto_safe": True,
                    })

            # Rule 4: Orphan source with rich content → concept
            if not skip_extract and not has_concepts and not has_decisions and not has_projects:
                word_count = len(content.split())
                if word_count >= self._min_words and backlinks < self._min_backlinks:
                    self.actions.append({
                        "type": "synthesize-concept",
                        "source": obj["path"],
                        "source_title": obj.get("title", ""),
                        "target": f"{self._knowledge_dir}/概念/{Path(obj['path']).stem}.md",
                        "reason": (
                            f"Rich underlinked source ({word_count} words, {backlinks} backlinks) "
                            f"'{obj['title']}' — synthesize into concept"
                        ),
                        "confidence": "low",
                        "auto_safe": False,
                    })

        if auto:
            return [action for action in self.actions if action.get("auto_safe") is True]
        return self.actions

    def apply(self, actions: list):
        """Apply promotion actions."""
        for action in actions:
            if action["type"] == "promote-to-output":
                self._apply_promote_to_output(action)
            elif action["type"] == "extract-concept":
                self._apply_extract_concept(action)
            elif action["type"] == "extract-decision":
                self._apply_extract_decision(action)
            elif action["type"] == "synthesize-concept":
                self._apply_extract_concept(action)

    def _apply_promote_to_output(self, action: dict):
        """Move/rename a source to output directory with updated frontmatter."""
        src_path = self.vault / action["source"]
        if not src_path.exists():
            return
        target_path = self.vault / action["target"]
        target_path.parent.mkdir(parents=True, exist_ok=True)

        post = frontmatter.load(str(src_path))
        post.metadata["type"] = "output"
        post.metadata["output_type"] = "log"
        post.metadata["status"] = "completed"
        post.metadata["lifecycle_stage"] = "maintained"
        post.metadata.setdefault("created_at", post.metadata.get("date"))
        post.metadata.setdefault("audience", "unspecified")
        post.metadata.setdefault("project", post.metadata.get("projects") or [])
        post.metadata.setdefault("derived_from", [f"[[{action['source'].removesuffix('.md')}]]"])
        if "source_type" in post.metadata:
            del post.metadata["source_type"]

        atomic_write_text(target_path, frontmatter.dumps(post), root=self.vault)
        # Optionally remove original
        # src_path.unlink()

    def _apply_extract_concept(self, action: dict):
        """Create a concept object from source content."""
        src_path = self.vault / action["source"]
        if not src_path.exists():
            return
        target_path = self.vault / action["target"]
        if target_path.exists():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)

        post = frontmatter.load(str(src_path))
        title = post.get("title", Path(action["source"]).stem)
        concept_fm = {
            "id": f"concept-{Path(action['source']).stem}",
            "type": "concept",
            "title": title,
            "status": "draft",
            "lifecycle_stage": "promoted",
            "definition": title,
            "source_basis": [f"[[{action['source'].replace('.md', '')}]]"],
            "related_projects": post.get("projects", []),
            "related_concepts": [],
        }
        concept_post = frontmatter.Post(post.content, **concept_fm)
        atomic_write_text(target_path, frontmatter.dumps(concept_post), root=self.vault)

    def _apply_extract_decision(self, action: dict):
        """Create a decision object from source content."""
        src_path = self.vault / action["source"]
        if not src_path.exists():
            return
        target_path = self.vault / action["target"]
        if target_path.exists():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)

        post = frontmatter.load(str(src_path))
        title = post.get("title", Path(action["source"]).stem)
        decision_fm = {
            "id": f"decision-{Path(action['source']).stem}",
            "type": "decision",
            "title": title,
            "status": "draft",
            "lifecycle_stage": "promoted",
            "project": post.get("projects", []),
            "context": action.get("reason", ""),
            "decision_date": post.get("created_at") or post.get("date"),
            "evidence": [f"[[{action['source'].replace('.md', '')}]]"],
            "constraints": [],
            "supersedes": [],
            "related_outputs": [],
        }
        decision_post = frontmatter.Post(post.content, **decision_fm)
        atomic_write_text(target_path, frontmatter.dumps(decision_post), root=self.vault)

    def _read_content(self, rel_path: str) -> str:
        path = self.vault / rel_path
        if not path.exists():
            return None
        try:
            post = frontmatter.load(str(path))
            return post.content
        except Exception:
            return path.read_text(encoding="utf-8")

    def _contains_keywords(self, content: str, keywords: list) -> bool:
        content_lower = content.lower()
        return any(kw.lower() in content_lower for kw in keywords)


def review_promotion(
    vault_root: Path | str,
    *,
    source: str,
    target: str,
    content: str,
) -> PromotionReviewPayload:
    """Review an agent-authored stable object without mutating the vault."""
    vault = Path(vault_root).expanduser().resolve()
    config = load_config(vault)
    errors: list[str] = []
    warnings: list[str] = []
    duplicate_paths: list[str] = []

    try:
        source_path = resolve_guarded_path(source, vault)
        target_path = resolve_guarded_path(target, vault)
    except ValueError as exc:
        return _blocked_review(source, target, [str(exc)])

    if source_path.suffix.lower() != ".md" or not source_path.exists():
        errors.append(f"source must be an existing Markdown object: {source}")
    if target_path.suffix.lower() != ".md":
        errors.append(f"target must be a Markdown path: {target}")
    if target_path.exists():
        errors.append(f"target already exists: {target}")
    if not content.strip():
        errors.append("proposal content is required")

    target_type: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = {}
    if content.strip():
        try:
            post = frontmatter.loads(content)
            metadata = dict(post.metadata)
            target_type = str(metadata.get("type")) if metadata.get("type") else None
            title = str(metadata.get("title")) if metadata.get("title") else None
            if not post.content.strip():
                errors.append("proposal body is required")
        except Exception as exc:
            errors.append(f"invalid Markdown frontmatter: {exc}")

    if target_type not in STABLE_PROMOTION_TYPES:
        errors.append("proposal type must be concept, decision, or constraint")
    configured_type = resolve_path_type(_relative_path(target_path, vault), config)
    if target_type and configured_type != target_type:
        errors.append(f"target path resolves to type {configured_type}, not {target_type}")

    if source_path.exists():
        try:
            source_type = str(frontmatter.load(str(source_path)).get("type", "unknown"))
            if source_type not in {"source", "output"}:
                errors.append(f"promotion source must be source or output, got {source_type}")
        except Exception as exc:
            errors.append(f"cannot parse source frontmatter: {exc}")

    schema = load_object_schema(vault, config)
    if schema and metadata:
        validator = Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(_json_instance(metadata)), key=lambda item: list(item.path)):
            field = ".".join(str(part) for part in error.path)
            errors.append(f"schema{f' ({field})' if field else ''}: {error.message}")

    index = VaultIndex(vault, config=config)
    index.scan()
    proposal_id = str(metadata.get("id") or "")
    for obj in index.objects:
        if title and str(obj.get("title", "")).casefold() == title.casefold():
            duplicate_paths.append(obj["path"])
        if proposal_id and str(obj.get("frontmatter", {}).get("id", "")) == proposal_id:
            duplicate_paths.append(obj["path"])
    duplicate_paths = sorted(set(duplicate_paths))
    if duplicate_paths:
        errors.append("proposal duplicates an existing title or id")

    if metadata.get("lifecycle_stage") != "promoted":
        warnings.append("new stable objects should normally start at lifecycle_stage=promoted")

    return {
        "status": "blocked" if errors else "ready",
        "source": _relative_path(source_path, vault),
        "target": _relative_path(target_path, vault),
        "target_type": target_type,
        "title": title,
        "touched_paths": [_relative_path(source_path, vault), _relative_path(target_path, vault)],
        "duplicate_paths": duplicate_paths,
        "validation_errors": errors,
        "warnings": warnings,
        "requires_confirmation": True,
    }


def apply_promotion(
    vault_root: Path | str,
    *,
    source: str,
    target: str,
    content: str,
) -> PromotionApplyPayload:
    """Apply a reviewed proposal and add the deterministic source backlink."""
    review = review_promotion(vault_root, source=source, target=target, content=content)
    if review["status"] != "ready":
        raise ValueError("promotion review blocked: " + "; ".join(review["validation_errors"]))

    vault = Path(vault_root).expanduser().resolve()
    source_path = resolve_guarded_path(source, vault)
    target_path = resolve_guarded_path(target, vault)
    source_before = source_path.read_text(encoding="utf-8")
    source_post = frontmatter.loads(source_before)
    relation_field = SOURCE_RELATION_FIELDS[review["target_type"]]
    values = source_post.metadata.get(relation_field) or []
    if not isinstance(values, list):
        values = [values]
    target_link = f"[[{review['target'].removesuffix('.md')}]]"
    if target_link not in values:
        values.append(target_link)
    source_post.metadata[relation_field] = values

    atomic_write_text(target_path, content.rstrip() + "\n", root=vault)
    try:
        atomic_write_text(source_path, frontmatter.dumps(source_post), root=vault)
    except Exception:
        target_path.unlink(missing_ok=True)
        atomic_write_text(source_path, source_before, root=vault)
        raise
    return {
        "status": "applied",
        "source": review["source"],
        "target": review["target"],
        "target_type": review["target_type"],
        "title": review["title"] or target_path.stem,
        "touched_paths": review["touched_paths"],
    }


def _relative_path(path: Path, vault: Path) -> str:
    try:
        return path.relative_to(vault).as_posix()
    except ValueError:
        return str(path)


def _blocked_review(source: str, target: str, errors: list[str]) -> PromotionReviewPayload:
    return {
        "status": "blocked",
        "source": source,
        "target": target,
        "target_type": None,
        "title": None,
        "touched_paths": [],
        "duplicate_paths": [],
        "validation_errors": errors,
        "warnings": [],
        "requires_confirmation": True,
    }


__all__ = [
    "PromotionPipeline",
    "PromotionReviewPayload",
    "PromotionApplyPayload",
    "review_promotion",
    "apply_promotion",
]
