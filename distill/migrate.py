"""Explicit, idempotent vault contract migrations."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .atomic_io import atomic_write_text
from .config import get_scan_dirs, load_config
from .schema import _json_instance, load_object_schema
from .vault_semantics import (
    KNOWLEDGE_PRESENTATION,
    PROJECT_PRESENTATION,
    PRESENTATION_SECTIONS,
    build_lookup_indexes,
    extract_frontmatter_links,
    extract_h2_headings,
    extract_wikilinks,
    resolve_link_target,
)


SUPPORTED_OBJECT_TYPES = {
    "analysis",
    "concept",
    "constraint",
    "decision",
    "entity",
    "output",
    "project",
    "source",
}
DEFAULT_STATUSES = {
    "analysis": "active",
    "concept": "active",
    "constraint": "active",
    "decision": "active",
    "entity": "active",
    "output": "draft",
    "project": "active",
    "source": "linked",
}
LIFECYCLE_STAGES = {
    "archived": "archived",
    "draft": "parsed",
    "linked": "linked",
    "raw": "raw",
    "superseded": "superseded",
    "retired": "archived",
}
FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<header>.*?)(?P<closing>\r?\n---[ \t]*(?:\r?\n|\Z))",
    re.DOTALL,
)
TOP_LEVEL_KEY_RE = re.compile(r"^(?!-)(?P<key>[^\s#][^:]*):(?:\s.*)?$")
DATE_RE = re.compile(r"(?P<date>20\d{2}-\d{2}-\d{2})")
RELATION_FIELDS = {
    "blocked_by",
    "concepts",
    "constraints",
    "decisions",
    "derived_from",
    "entities",
    "evidence",
    "outputs",
    "key_outputs",
    "project",
    "projects",
    "related_concepts",
    "related_decisions",
    "related_entities",
    "related_outputs",
    "related_projects",
    "related_sources",
    "source_basis",
    "sources",
    "supersedes",
}
STABLE_KNOWLEDGE_TYPES = {"concept", "decision", "constraint"}


@dataclass(frozen=True)
class MigrationFileChange:
    path: str
    operations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "operations": list(self.operations)}


def migrate_vault(vault_root: Path | str, *, target_version: int, apply: bool = False) -> dict[str, Any]:
    """Plan or apply a supported vault migration."""
    if target_version not in {1, 2, 3}:
        raise ValueError(f"unsupported migration target: {target_version}")

    root = Path(vault_root).expanduser().resolve()
    config = load_config(root)
    schema = load_object_schema(root, config)
    validator = Draft202012Validator(schema) if schema else None
    seen_paths: set[Path] = set()
    rendered_files: dict[Path, str] = {}
    metadata_by_path: dict[str, dict[str, Any]] = {}
    changes: list[MigrationFileChange] = []
    files_scanned = 0

    used_ids: set[str] = set()
    candidates: list[tuple[Path, str, str, dict[str, Any], list[str]]] = []
    for scan_root in get_scan_dirs(config, root):
        for path in sorted(scan_root.rglob("*.md")):
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            rel = resolved.relative_to(root).as_posix()
            if not _is_object_layer_path(rel, config):
                continue
            files_scanned += 1
            raw = resolved.read_text(encoding="utf-8")
            matched = FRONTMATTER_RE.match(raw)
            if not matched:
                continue
            header, cleanup_operations = _clean_header(matched.group("header"))
            metadata = yaml.safe_load(header) or {}
            if not isinstance(metadata, dict):
                continue
            obj_type = str(metadata.get("type") or "unknown")
            if obj_type == "log":
                obj_type = "output"
            if obj_type not in SUPPORTED_OBJECT_TYPES:
                continue
            if metadata.get("id"):
                used_ids.add(str(metadata["id"]))
            candidates.append((resolved, rel, raw, metadata, cleanup_operations))

    reverse_compounding = _build_reverse_compounding_relations(candidates)

    for path, rel, raw, metadata, cleanup_operations in candidates:
        matched = FRONTMATTER_RE.match(raw)
        assert matched is not None
        header, _ = _clean_header(matched.group("header"))
        operations = list(cleanup_operations)
        original_type = str(metadata.get("type") or "unknown")
        obj_type = "output" if original_type == "log" else original_type

        for relation in sorted(RELATION_FIELDS):
            if relation not in metadata:
                continue
            normalized_relation = _normalize_relation_value(metadata[relation])
            if normalized_relation != metadata[relation]:
                metadata[relation] = normalized_relation
                header = _set_field(header, relation, normalized_relation)
                operations.append(f"normalize relation list: {relation}")

        if original_type == "log":
            metadata["type"] = "output"
            header = _set_field(header, "type", "output")
            operations.append("type: log -> output")

        if not metadata.get("id"):
            object_id = _deterministic_id(obj_type, rel, used_ids)
            used_ids.add(object_id)
            metadata["id"] = object_id
            header = _set_field(header, "id", object_id)
            operations.append(f"add id: {object_id}")

        status = metadata.get("status")
        if status == "已发布":
            status = "published"
            metadata["status"] = status
            header = _set_field(header, "status", status)
            operations.append("status: 已发布 -> published")
        elif status in (None, ""):
            status = "completed" if original_type == "log" else DEFAULT_STATUSES[obj_type]
            metadata["status"] = status
            header = _set_field(header, "status", status)
            operations.append(f"add status: {status}")

        lifecycle_stage = metadata.get("lifecycle_stage")
        expected_stage = LIFECYCLE_STAGES.get(str(status), "maintained")
        if not lifecycle_stage:
            metadata["lifecycle_stage"] = expected_stage
            header = _set_field(header, "lifecycle_stage", expected_stage)
            operations.append(f"add lifecycle_stage: {expected_stage}")

        inferred_date = _infer_date(metadata, rel)
        if obj_type == "source":
            source_type = metadata.get("source_type")
            if not source_type:
                source_type = _infer_source_type(metadata, rel)
                metadata["source_type"] = source_type
                header = _set_field(header, "source_type", source_type)
                operations.append(f"add source_type: {source_type}")
            header = _ensure_field(header, metadata, "created_at", inferred_date, operations)
            header = _ensure_field(header, metadata, "source_url", None, operations)
            header = _ensure_field(header, metadata, "author", None, operations)
            header = _ensure_field(header, metadata, "reliability", "unknown", operations)
            for relation in ("projects", "concepts", "entities", "outputs"):
                header = _ensure_field(header, metadata, relation, [], operations)

        if obj_type == "output":
            output_type = metadata.get("output_type")
            if not output_type:
                output_type = _infer_output_type(metadata, rel)
                metadata["output_type"] = output_type
                header = _set_field(header, "output_type", output_type)
                operations.append(f"add output_type: {output_type}")
            header = _ensure_field(header, metadata, "created_at", inferred_date, operations)
            audience = "public" if status == "published" else "unspecified"
            header = _ensure_field(header, metadata, "audience", audience, operations)
            project = metadata.get("projects") or []
            header = _ensure_field(header, metadata, "project", project, operations)
            derived_from = metadata.get("sources") or []
            header = _ensure_field(header, metadata, "derived_from", derived_from, operations)

        if target_version >= 2 and obj_type == "project":
            header = _migrate_project_v2(header, metadata, operations)
        if target_version >= 3 and obj_type == "project":
            header = _ensure_presentation(
                header, metadata, PROJECT_PRESENTATION, operations
            )
        elif target_version >= 3 and obj_type in STABLE_KNOWLEDGE_TYPES:
            header = _ensure_presentation(
                header, metadata, KNOWLEDGE_PRESENTATION, operations
            )
            relations = reverse_compounding.get(rel, {})
            for field in ("related_projects", "related_outputs", "feedback_candidates", "supersedes"):
                header = _merge_relation_field(
                    header,
                    metadata,
                    field,
                    relations.get(field, []),
                    operations,
                )

        body = raw[matched.end() :]
        if target_version >= 2 and obj_type == "project":
            body = _migrate_project_body_v2(body, str(metadata.get("summary") or ""), operations)
        if target_version >= 3 and obj_type == "project":
            body = _migrate_project_body_v3(body, metadata, operations, _path_language(rel))
        elif target_version >= 3 and obj_type in STABLE_KNOWLEDGE_TYPES:
            body = _migrate_knowledge_body_v3(body, metadata, operations, _path_language(rel))
        rendered = raw[: matched.start("header")] + header + matched.group("closing") + body
        parsed = yaml.safe_load(header) or {}
        metadata_by_path[rel] = parsed
        if rendered != raw:
            rendered_files[path] = rendered
            changes.append(MigrationFileChange(rel, tuple(operations)))

    validation_errors = _validate_migrated_metadata(metadata_by_path, validator)
    validation_errors.extend(_duplicate_id_errors(metadata_by_path))
    if apply and validation_errors:
        raise ValueError("migration validation failed: " + "; ".join(validation_errors[:10]))
    if apply:
        for path, rendered in rendered_files.items():
            atomic_write_text(path, rendered, root=root)

    return {
        "target_version": target_version,
        "apply": apply,
        "files_scanned": files_scanned,
        "files_changed": len(changes),
        "validation_errors": validation_errors,
        "changes": [change.as_dict() for change in changes],
    }


def _is_object_layer_path(path: str, config: dict[str, Any]) -> bool:
    include_globs = config.get("schema", {}).get("include_globs") or []
    if include_globs:
        return any(fnmatch.fnmatchcase(path, pattern) for pattern in include_globs)
    roots = [
        *config.get("vault", {}).get("knowledge_dirs", []),
        *config.get("vault", {}).get("output_dirs", []),
    ]
    return any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots if root != ".")


def _build_reverse_compounding_relations(
    candidates: list[tuple[Path, str, str, dict[str, Any], list[str]]],
) -> dict[str, dict[str, list[str]]]:
    """Project reverse adoption into stable knowledge without inventing usage facts."""
    objects = [
        {
            "path": rel,
            "title": str(metadata.get("title") or path.stem),
            "type": "output" if metadata.get("type") == "log" else str(metadata.get("type") or "unknown"),
            "frontmatter": metadata,
        }
        for path, rel, _, metadata, _ in candidates
    ]
    path_index, title_index, filename_index = build_lookup_indexes(objects)
    direct_sources: dict[str, set[str]] = {}
    for obj in objects:
        if obj["type"] not in STABLE_KNOWLEDGE_TYPES:
            continue
        metadata = obj["frontmatter"]
        links = extract_frontmatter_links(
            {"basis": [metadata.get("source_basis"), metadata.get("evidence")]},
            relation_fields=["basis"],
            include_plain_strings=True,
        )
        resolved = {
            target
            for link in links
            if (target := resolve_link_target(
                link,
                path_index=path_index,
                title_index=title_index,
                filename_index=filename_index,
            ))
        }
        direct_sources[obj["path"]] = resolved

    result: dict[str, dict[str, list[str]]] = {}
    for (_, source_rel, raw, metadata, _), source_obj in zip(candidates, objects):
        matched = FRONTMATTER_RE.match(raw)
        body = raw[matched.end() :] if matched else raw
        links = extract_wikilinks(body)
        links.extend(extract_frontmatter_links(metadata, include_plain_strings=True))
        for link in links:
            target = resolve_link_target(
                link,
                path_index=path_index,
                title_index=title_index,
                filename_index=filename_index,
            )
            if not target or target == source_rel:
                continue
            target_obj = path_index.get(target)
            if not target_obj or target_obj["type"] not in STABLE_KNOWLEDGE_TYPES:
                continue
            field = None
            if source_obj["type"] == "project":
                field = "related_projects"
            elif source_obj["type"] == "output" and not _is_timeline_output(source_obj):
                field = "related_outputs"
            elif source_obj["type"] == "source" and source_rel not in direct_sources.get(target, set()):
                field = "feedback_candidates"
            if field is None:
                continue
            value = f"[[{source_rel.removesuffix('.md')}]]"
            bucket = result.setdefault(target, {}).setdefault(field, [])
            if value not in bucket:
                bucket.append(value)
    return result


def _is_timeline_output(obj: dict[str, Any]) -> bool:
    output_type = str(obj.get("frontmatter", {}).get("output_type") or "").lower()
    path = str(obj.get("path") or "")
    return output_type in {"log", "daily", "daily_log"} or "/日志/" in path or "/logs/" in path.lower()


def _clean_header(header: str) -> tuple[str, list[str]]:
    blocks: list[tuple[str | None, list[str]]] = []
    current_key: str | None = None
    current_lines: list[str] = []
    for line in header.splitlines():
        match = TOP_LEVEL_KEY_RE.match(line)
        if match:
            if current_lines:
                blocks.append((current_key, current_lines))
            current_key = match.group("key").strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        blocks.append((current_key, current_lines))

    selected: dict[str, tuple[int, list[str]]] = {}
    for index, (key, lines) in enumerate(blocks):
        if key is None:
            continue
        score = _block_value_score(key, lines)
        previous = selected.get(key)
        if previous is None or score > _block_value_score(key, previous[1]):
            selected[key] = (index, lines)

    emitted: set[str] = set()
    output: list[str] = []
    operations: list[str] = []
    for _, (key, lines) in enumerate(blocks):
        if key is None:
            output.extend(lines)
            continue
        if key in emitted:
            operations.append(f"remove duplicate field: {key}")
            continue
        emitted.add(key)
        chosen = selected[key][1]
        if chosen is not lines:
            operations.append(f"remove duplicate field: {key}")
        deduped = _deduplicate_direct_list(chosen)
        if len(deduped) != len(chosen):
            operations.append(f"deduplicate list: {key}")
        output.extend(deduped)
    return "\n".join(output), operations


def _block_value_score(key: str, lines: list[str]) -> int:
    try:
        value = (yaml.safe_load("\n".join(lines)) or {}).get(key)
    except Exception:
        return 0
    if value in (None, "", [], {}):
        return 0
    return 1


def _deduplicate_direct_list(lines: list[str]) -> list[str]:
    item_matches = [
        (index, re.match(r"^(?P<indent>\s+)-\s+(?P<value>.+)$", line))
        for index, line in enumerate(lines)
    ]
    item_matches = [(index, match) for index, match in item_matches if match]
    if not item_matches:
        return lines
    minimum_indent = min(len(match.group("indent")) for _, match in item_matches)
    seen: set[str] = set()
    output = []
    for line in lines:
        match = re.match(r"^(?P<indent>\s+)-\s+(?P<value>.+)$", line)
        if match and len(match.group("indent")) == minimum_indent:
            value = match.group("value").strip()
            if value in seen:
                continue
            seen.add(value)
        output.append(line)
    return output


def _set_field(header: str, key: str, value: Any) -> str:
    lines = header.splitlines()
    key_pattern = re.compile(rf"^{re.escape(key)}:(?:\s.*)?$")
    for index, line in enumerate(lines):
        if key_pattern.match(line):
            end = index + 1
            while end < len(lines) and not TOP_LEVEL_KEY_RE.match(lines[end]):
                end += 1
            lines[index:end] = _render_field(key, value)
            return "\n".join(lines)
    if lines and lines[-1].strip():
        lines.extend(_render_field(key, value))
    else:
        lines[-1:] = _render_field(key, value) + ([""] if lines else [])
    return "\n".join(lines)


def _remove_field(header: str, key: str) -> str:
    """Remove one top-level YAML field while preserving neighboring formatting."""
    lines = header.splitlines()
    key_pattern = re.compile(rf"^{re.escape(key)}:(?:\s.*)?$")
    for index, line in enumerate(lines):
        if not key_pattern.match(line):
            continue
        end = index + 1
        while end < len(lines) and not TOP_LEVEL_KEY_RE.match(lines[end]):
            end += 1
        del lines[index:end]
        break
    return "\n".join(lines)


def _ensure_presentation(
    header: str,
    metadata: dict[str, Any],
    presentation: str,
    operations: list[str],
) -> str:
    """Mark an object for deterministic human-facing presentation checks."""
    if metadata.get("presentation") == presentation:
        return header
    metadata["presentation"] = presentation
    operations.append(f"set presentation: {presentation}")
    return _set_field(header, "presentation", presentation)


def _merge_relation_field(
    header: str,
    metadata: dict[str, Any],
    field: str,
    discovered: list[str],
    operations: list[str],
) -> str:
    existing = _normalize_relation_value(metadata.get(field) or [])
    if not isinstance(existing, list):
        existing = [existing]
    merged = list(existing)
    for item in discovered:
        if item not in merged:
            merged.append(item)
    if field in metadata and merged == metadata[field]:
        return header
    metadata[field] = merged
    operations.append(f"project compounding relation: {field}")
    return _set_field(header, field, merged)


def _migrate_project_v2(
    header: str,
    metadata: dict[str, Any],
    operations: list[str],
) -> str:
    """Turn a task-oriented project frontmatter block into a knowledge dossier."""
    if "summary" not in metadata:
        summary = metadata.get("current_focus") or metadata.get("goal") or ""
        metadata["summary"] = summary
        header = _set_field(header, "summary", summary)
        operations.append("add project summary")

    for obsolete in ("current_focus", "next_step"):
        if obsolete in metadata:
            metadata.pop(obsolete, None)
            header = _remove_field(header, obsolete)
            operations.append(f"remove task-oriented field: {obsolete}")

    outputs = _normalize_relation_value(metadata.get("outputs") or [])
    if "key_outputs" not in metadata:
        key_outputs = [
            _ensure_wikilink(item)
            for item in outputs
            if isinstance(item, str) and "/日志/" not in item and "/logs/" not in item.lower()
        ][:12]
        metadata["key_outputs"] = key_outputs
        header = _set_field(header, "key_outputs", key_outputs)
        operations.append("derive key_outputs from non-log outputs")
    if "outputs" in metadata:
        metadata.pop("outputs", None)
        header = _remove_field(header, "outputs")
        operations.append("remove project output timeline")

    for relation in ("sources", "decisions", "constraints", "concepts", "entities", "key_outputs"):
        value = metadata.get(relation)
        if not isinstance(value, list):
            continue
        normalized = [_ensure_wikilink(item) for item in value]
        if normalized != value:
            metadata[relation] = normalized
            header = _set_field(header, relation, normalized)
            operations.append(f"normalize project wikilinks: {relation}")
    return header


def _ensure_wikilink(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text.startswith("[[") or "://" in text:
        return value
    if text.endswith(".md"):
        text = text[:-3]
    if "/" not in text:
        return value
    return f"[[{text}]]"


def _migrate_project_body_v2(body: str, summary: str, operations: list[str]) -> str:
    replacements = {
        "## 状态摘要": "## 已完成成果",
        "## Status Summary": "## Completed Outcomes",
        "## 近期进展": "## 已完成成果",
        "## 当前运行边界状态": "## 运行边界",
        "## 当前关键规则": "## 关键规则",
        "## 近期验证": "## 验证记录",
        "## 当前资产": "## 资产清单",
        "## 最新跟进": "## 近期研究成果",
        "## 当前已知问题与修复": "## 已验证问题与修复",
    }
    rendered = body
    for previous, replacement in replacements.items():
        if previous in rendered:
            rendered = rendered.replace(previous, replacement)
            operations.append(f"rename project heading: {previous} -> {replacement}")
    for heading in (
        "下一步",
        "Next Steps",
        "当前焦点",
        "近期输出",
        "相关输出",
        "变更记录",
    ):
        pattern = re.compile(
            rf"\n## {re.escape(heading)}\s*\n.*?(?=\n## |\Z)",
            re.DOTALL,
        )
        if pattern.search(rendered):
            rendered = pattern.sub("", rendered)
            operations.append(f"remove project timeline section: ## {heading}")
    completed_pattern = re.compile(r"\n## 已完成成果\s*\n(?P<content>.*?)(?=\n## |\Z)", re.DOTALL)
    completed_matches = list(completed_pattern.finditer(rendered))
    completed_size = sum(len(match.group("content").strip()) for match in completed_matches)
    if completed_matches and (len(completed_matches) > 1 or completed_size > 2000):
        concise = summary.strip() or "详细成果保留在关联来源与输出中。"
        kept = False

        def replace_completed(match: re.Match[str]) -> str:
            nonlocal kept
            if kept:
                return ""
            kept = True
            return f"\n## 已完成成果\n\n{concise}\n"

        rendered = completed_pattern.sub(replace_completed, rendered)
        operations.append("consolidate completed-outcomes timeline")
    evidence_embed = "![[浏览/项目证据.base]]"
    if evidence_embed not in rendered:
        rendered = rendered.rstrip() + f"\n\n## 关联证据\n\n{evidence_embed}\n"
        operations.append("embed project evidence base")
    return rendered


def _migrate_project_body_v3(
    body: str,
    metadata: dict[str, Any],
    operations: list[str],
    lang_hint: str | None = None,
) -> str:
    """Add a compact human-facing handbook above the existing project detail."""
    lang = _presentation_language(body, metadata, lang_hint)
    required = PRESENTATION_SECTIONS[PROJECT_PRESENTATION][lang]
    existing = extract_h2_headings(body)
    missing = [heading for heading in required if heading not in existing]
    if not missing:
        return body

    zh = lang == "zh"
    summary = str(metadata.get("summary") or metadata.get("goal") or ("尚未沉淀项目结论。" if zh else "No project conclusion has been captured."))
    decisions = _relation_text(metadata.get("decisions"), "尚未沉淀关键决策。" if zh else "No key decisions captured.")
    constraints = _relation_text(metadata.get("constraints"), "尚未沉淀关键约束。" if zh else "No key constraints captured.")
    evidence = _relation_text(
        [metadata.get("sources"), metadata.get("key_outputs")],
        "尚未关联验证证据。" if zh else "No validation evidence linked.",
    )
    if zh:
        sections = {
            "一页结论": summary,
            "资产与系统地图": "- 尚未沉淀。按项目形态补充仓库、系统、交付物、内容或运维资产。",
            "如何使用或运行": "- 尚未沉淀。补充启动、访问、交付、维护或复现项目成果的最短路径。",
            "配置与访问": "- 尚未沉淀。只记录非敏感配置与凭据所在位置，不记录密码、令牌或私钥。",
            "已验证事实": f"- {summary}",
            "决策与约束": f"- 决策：{decisions}\n- 约束：{constraints}",
            "验证与证据": f"- {evidence}",
        }
    else:
        sections = {
            "At a Glance": summary,
            "Asset and System Map": "- Not captured yet. Add repositories, systems, deliverables, content, or operational assets.",
            "How to Use or Run": "- Not captured yet. Add the shortest path to start, access, deliver, maintain, or reproduce the work.",
            "Configuration and Access": "- Not captured yet. Record non-secret configuration and credential locations, never secret values.",
            "Verified Facts": f"- {summary}",
            "Decisions and Constraints": f"- Decisions: {decisions}\n- Constraints: {constraints}",
            "Validation and Evidence": f"- {evidence}",
        }
    block = _render_missing_sections(required, missing, sections)
    operations.append("add project handbook presentation")
    if existing.intersection(required):
        return body.rstrip() + f"\n\n{block.rstrip()}\n"
    return _insert_after_title(body, block)


def _migrate_knowledge_body_v3(
    body: str,
    metadata: dict[str, Any],
    operations: list[str],
    lang_hint: str | None = None,
) -> str:
    """Expose how stable knowledge was created, validated, reused, and evolved."""
    lang = _presentation_language(body, metadata, lang_hint)
    required = PRESENTATION_SECTIONS[KNOWLEDGE_PRESENTATION][lang]
    existing = extract_h2_headings(body)
    missing = [heading for heading in required if heading not in existing]

    zh = lang == "zh"
    obj_type = str(metadata.get("type") or "knowledge")
    conclusion = str(
        metadata.get("definition")
        or metadata.get("statement")
        or metadata.get("context")
        or metadata.get("workaround")
        or metadata.get("title")
        or ("尚未提炼一句话结论。" if zh else "No one-sentence conclusion has been distilled.")
    )
    source_fallback = "尚未关联来源" if zh else "No source linked"
    source = _relation_text(
        [metadata.get("source_basis"), metadata.get("evidence")],
        source_fallback,
    )
    projects = _relation_text(
        [metadata.get("related_projects"), metadata.get("project")],
        "尚未记录复用项目" if zh else "No reuse project recorded",
    )
    outputs = _relation_text(metadata.get("related_outputs"), "尚未记录复利产物" if zh else "No compounding output recorded")
    feedback = _relation_text(metadata.get("feedback_candidates"), "尚未发现反馈候选" if zh else "No feedback candidate found")
    neighbors = _relation_text(
        [metadata.get("related_concepts"), metadata.get("related_decisions")],
        "尚未关联相邻知识" if zh else "No adjacent knowledge linked",
    )
    supersedes = _relation_text(metadata.get("supersedes"), "当前没有替代关系" if zh else "No supersession relationship")
    status = f"{metadata.get('status', 'unknown')} / {metadata.get('lifecycle_stage', 'unknown')}"
    if zh:
        validation = "已有可追溯证据" if source != source_fallback else "待补验证证据"
        lifecycle = f"""| 阶段 | 当前状态 | 证据或去向 |
| --- | --- | --- |
| 产生 | 已记录来源 | {_table_text(source)} |
| 提炼 | 已形成 `{obj_type}` 稳定对象 | 本页核心内容 |
| 验证 | {validation} | {_table_text(source)} |
| 稳定 | `{status}` | Git 历史与对象状态 |
| 复用 | 已关联项目或待补 | {_table_text(projects)} |
| 反馈 | 关联来源候选或待补 | {_table_text(feedback)} |
| 复利 | 已关联产物或待补 | {_table_text(outputs)} |
| 演化 | 显式保留替代关系 | {_table_text(supersedes)} |"""
        sections = {
            "一句话结论": conclusion,
            "知识生命周期": lifecycle,
            "适用与复用": f"- 适用项目：{projects}\n- 相邻知识：{neighbors}\n- 反馈候选：{feedback}\n- 复利产物：{outputs}",
            "证据与演化": f"- 来源与验证：{source}\n- 反馈候选只表示新增来源关系，不自动等同于已验证反馈。\n- 替代关系：{supersedes}",
        }
    else:
        validation = "Traceable evidence exists" if source != source_fallback else "Validation evidence needed"
        lifecycle = f"""| Stage | Current state | Evidence or destination |
| --- | --- | --- |
| Generated | Source recorded | {_table_text(source)} |
| Distilled | Stable `{obj_type}` object created | Core content on this page |
| Validated | {validation} | {_table_text(source)} |
| Stabilized | `{status}` | Git history and object status |
| Reused | Linked project or pending | {_table_text(projects)} |
| Feedback | Linked source candidate or pending | {_table_text(feedback)} |
| Compounded | Linked output or pending | {_table_text(outputs)} |
| Evolved | Supersession remains explicit | {_table_text(supersedes)} |"""
        sections = {
            "One-sentence Conclusion": conclusion,
            "Knowledge Lifecycle": lifecycle,
            "Application and Reuse": f"- Projects: {projects}\n- Adjacent knowledge: {neighbors}\n- Feedback candidates: {feedback}\n- Compounding outputs: {outputs}",
            "Evidence and Evolution": f"- Sources and validation: {source}\n- Feedback candidates only indicate newer source relations, not validated feedback by themselves.\n- Supersession: {supersedes}",
        }
    rendered = body
    for heading in required:
        if heading in existing:
            rendered = _replace_h2_section(rendered, heading, sections[heading])
    if missing:
        block = _render_missing_sections(required, missing, sections)
        if existing.intersection(required):
            rendered = rendered.rstrip() + f"\n\n{block.rstrip()}\n"
        else:
            detail_heading = "详细内容" if zh else "Detailed Content"
            rendered = _insert_contract_after_title(rendered, block, detail_heading)
    if rendered != body:
        operations.append("refresh knowledge compounding presentation")
    return rendered


def _render_missing_sections(
    required: tuple[str, ...],
    missing: list[str],
    content_by_heading: dict[str, str],
) -> str:
    return "\n\n".join(
        f"## {heading}\n\n{content_by_heading[heading]}"
        for heading in required
        if heading in missing
    ) + "\n"


def _replace_h2_section(body: str, heading: str, content: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}[ \t]*\n.*?(?=^##[ \t]+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    replacement = f"## {heading}\n\n{content.rstrip()}\n\n"
    return pattern.sub(replacement, body, count=1)


def _path_language(path: str) -> str | None:
    if path.startswith(("知识/", "输出/")):
        return "zh"
    if path.startswith(("knowledge/", "output/")):
        return "en"
    return None


def _presentation_language(
    body: str,
    metadata: dict[str, Any],
    lang_hint: str | None = None,
) -> str:
    if lang_hint in {"zh", "en"}:
        return lang_hint
    headings = extract_h2_headings(body)
    for presentation in PRESENTATION_SECTIONS.values():
        for lang, expected in presentation.items():
            if headings.intersection(expected):
                return lang
    text = f"{metadata.get('title', '')}\n{body}"
    return "zh" if re.search(r"[\u3400-\u9fff]", text) else "en"


def _insert_after_title(body: str, block: str) -> str:
    title = re.search(r"^# .+$", body, flags=re.MULTILINE)
    if title is None:
        return f"\n{block.rstrip()}\n\n{body.lstrip()}"
    return f"{body[:title.end()]}\n\n{block.rstrip()}\n\n{body[title.end():].lstrip()}"


def _insert_contract_after_title(body: str, block: str, detail_heading: str) -> str:
    title = re.search(r"^# .+$", body, flags=re.MULTILINE)
    if title is None:
        return f"\n{block.rstrip()}\n\n## {detail_heading}\n\n{body.lstrip()}"
    remainder = body[title.end():].lstrip()
    detail = f"\n\n## {detail_heading}\n\n{remainder}" if remainder else ""
    return f"{body[:title.end()]}\n\n{block.rstrip()}{detail}"


def _relation_text(value: Any, fallback: str) -> str:
    items: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
        elif item not in (None, ""):
            text = str(item).strip()
            if text and text not in items:
                items.append(text)

    visit(value)
    return "、".join(items) if items else fallback


def _table_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _ensure_field(
    header: str,
    metadata: dict[str, Any],
    key: str,
    value: Any,
    operations: list[str],
) -> str:
    if key in metadata:
        return header
    metadata[key] = value
    operations.append(f"add {key}")
    return _set_field(header, key, value)


def _render_field(key: str, value: Any) -> list[str]:
    rendered = yaml.safe_dump(
        {key: value},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    return rendered.splitlines()


def _deterministic_id(obj_type: str, path: str, used_ids: set[str]) -> str:
    stem = Path(path).stem.strip().lower()
    slug = re.sub(r"[^0-9a-zA-Z\u3400-\u9fff]+", "-", stem).strip("-") or "object"
    candidate = f"{obj_type}-{slug}"
    if candidate not in used_ids:
        return candidate
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]
    return f"{candidate}-{digest}"


def _infer_date(metadata: dict[str, Any], path: str) -> str | None:
    for key in ("created_at", "date", "updated_at", "updated"):
        value = metadata.get(key)
        if value:
            matched = DATE_RE.search(str(value))
            if matched:
                return matched.group("date")
    matched = DATE_RE.search(Path(path).stem)
    return matched.group("date") if matched else None


def _infer_source_type(metadata: dict[str, Any], path: str) -> str:
    text = f"{path} {metadata.get('title', '')}".lower()
    source_url = str(metadata.get("source_url") or "").lower()
    if "github.com" in source_url:
        return "github"
    if source_url.startswith(("http://", "https://")):
        return "web"
    if "碎碎念" in text or "conversation" in text:
        return "conversation"
    return "note"


def _infer_output_type(metadata: dict[str, Any], path: str) -> str:
    text = f"{path} {metadata.get('title', '')}".lower()
    if "日志/" in path:
        return "log"
    if "周报" in text or "weekly" in text:
        return "weekly"
    if "日报" in text or "daily" in text:
        return "daily"
    if "报告" in text or "report" in text:
        return "report"
    return "artifact"


def _normalize_relation_value(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    flattened: list[Any] = []

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if item not in flattened:
            flattened.append(item)

    visit(value)
    return flattened


def _validate_migrated_metadata(
    metadata_by_path: dict[str, dict[str, Any]],
    validator: Draft202012Validator | None,
) -> list[str]:
    if validator is None:
        return []
    errors = []
    for path, metadata in sorted(metadata_by_path.items()):
        for error in validator.iter_errors(_json_instance(metadata)):
            field = ".".join(str(item) for item in error.path)
            errors.append(f"{path}{f' ({field})' if field else ''}: {error.message}")
    return errors


def _duplicate_id_errors(metadata_by_path: dict[str, dict[str, Any]]) -> list[str]:
    paths_by_id: dict[str, list[str]] = {}
    for path, metadata in metadata_by_path.items():
        object_id = metadata.get("id")
        if object_id:
            paths_by_id.setdefault(str(object_id), []).append(path)
    return [
        f"duplicate id {object_id}: {', '.join(paths)}"
        for object_id, paths in sorted(paths_by_id.items())
        if len(paths) > 1
    ]


__all__ = ["MigrationFileChange", "migrate_vault"]
