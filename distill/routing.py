"""Shared runtime contract for minimal route / plan / apply knowledge-task surfaces.

This module is the single source of truth for the minimal-task routing runtime
used by CLI and MCP entrypoints.

Public contract layers:
- compact route: low-noise read/write boundary discovery
- full plan: machine-oriented action plan built on top of the route
- applied result: execution result after the minimal write path runs

Any new route/plan/apply fields should be added through the shared builders and
then consumed unchanged by CLI + MCP surfaces so product contracts do not drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

import frontmatter

from .atomic_io import atomic_write_text
from .commit import recommended_commit_command
from .config import load_config
from .index import VaultIndex


FACT_HINTS = (
    "记录",
    "完成",
    "已完成",
    "已发布",
    "已上线",
    "已验证",
    "上线",
    "发布",
    "修复",
    "调整",
    "record",
    "completed",
    "shipped",
    "verified",
    "release",
    "launch",
)

FORWARD_LOOKING_HINTS = (
    "下一步",
    "接下来",
    "计划",
    "待处理",
    "待完成",
    "争取",
    "todo",
    "next step",
    "plan to",
)


@dataclass(frozen=True)
class CaptureResult:
    """Canonical applied-result record for the completed-fact capture path.

    This dataclass is the internal execution result that backs the public
    apply/capture payload surface.
    """

    action: str
    status: str
    operation: str
    source_path: str
    project_path: str | None
    touched_paths: list[str]
    recommended_commit_paths: list[str]
    recommended_commit_message: str
    recommended_commit_command: str


class PlanPayload(TypedDict):
    """Canonical full-plan machine contract for minimal-task routing."""

    action: str
    status: str
    intent: str
    operation: str
    confidence: str
    target_project: str | None
    read_paths: list[str]
    write_paths: list[str]
    optional_paths: list[str]
    skip_steps: list[str]
    recommended_commit_paths: list[str]
    recommended_commit_message: str | None
    recommended_commit_command: str | None
    why: list[str]
    warnings: list[str]


class RoutePayload(TypedDict):
    """Canonical compact-route machine contract for minimal-task routing."""

    intent: str
    operation: str
    confidence: str
    target_project: str | None
    read_paths: list[str]
    write_paths: list[str]
    optional_paths: list[str]
    skip_steps: list[str]
    recommended_commit_paths: list[str]
    recommended_commit_message: str | None
    recommended_commit_command: str | None
    why: list[str]
    warnings: list[str]


class ApplyPayload(TypedDict):
    """Canonical applied-result machine contract for minimal-task routing."""

    action: str
    status: str
    operation: str
    source_path: str
    project_path: str | None
    touched_paths: list[str]
    recommended_commit_paths: list[str]
    recommended_commit_message: str
    recommended_commit_command: str


def _today_iso() -> str:
    return date.today().isoformat()


def build_plan_payload(
    *,
    action: str,
    status: str,
    intent: str,
    operation: str,
    confidence: str,
    target_project: str | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
    optional_paths: list[str] | None = None,
    skip_steps: list[str] | None = None,
    recommended_commit_paths: list[str] | None = None,
    recommended_commit_message: str | None = None,
    recommended_commit_command: str | None = None,
    why: list[str] | None = None,
    warnings: list[str] | None = None,
) -> PlanPayload:
    """Build the canonical full plan payload for the runtime contract.

    This is the richest machine-facing route/plan surface and is the source of
    truth for CLI `distill plan --format json` and MCP `projection_plan`.

    Stable fields in the full plan contract:
    - action
    - status
    - intent
    - operation
    - confidence
    - target_project
    - read_paths
    - write_paths
    - optional_paths
    - skip_steps
    - recommended_commit_paths
    - recommended_commit_message
    - recommended_commit_command
    - why
    - warnings
    """
    return {
        "action": action,
        "status": status,
        "intent": intent,
        "operation": operation,
        "confidence": confidence,
        "target_project": target_project,
        "read_paths": list(read_paths or []),
        "write_paths": list(write_paths or []),
        "optional_paths": list(optional_paths or []),
        "skip_steps": list(skip_steps or []),
        "recommended_commit_paths": list(recommended_commit_paths or []),
        "recommended_commit_message": recommended_commit_message,
        "recommended_commit_command": recommended_commit_command,
        "why": list(why or []),
        "warnings": list(warnings or []),
    }


def build_route_payload(plan: PlanPayload) -> RoutePayload:
    """Build the compact route payload derived from a full plan.

    This is the low-noise boundary-discovery contract used by CLI
    `distill route --format json` and MCP `projection_route`.

    The compact route intentionally does not include action or status. It keeps
    only the minimal surface needed for read/write-set discovery plus
    recommended_commit_* guidance.
    """
    return {
        "intent": plan.get("intent", ""),
        "operation": plan.get("operation"),
        "confidence": plan.get("confidence"),
        "target_project": plan.get("target_project"),
        "read_paths": list(plan.get("read_paths", [])),
        "write_paths": list(plan.get("write_paths", [])),
        "optional_paths": list(plan.get("optional_paths", [])),
        "skip_steps": list(plan.get("skip_steps", [])),
        "recommended_commit_paths": list(plan.get("recommended_commit_paths", [])),
        "recommended_commit_message": plan.get("recommended_commit_message"),
        "recommended_commit_command": plan.get("recommended_commit_command"),
        "why": list(plan.get("why", [])),
        "warnings": list(plan.get("warnings", [])),
    }


def build_apply_payload(result: CaptureResult) -> ApplyPayload:
    """Build the canonical applied result payload from a CaptureResult.

    This is the execution-result contract used by CLI `capture/apply --format
    json` and MCP `projection_apply`.

    Stable fields in the applied result contract:
    - action
    - status
    - operation
    - source_path
    - project_path
    - touched_paths
    - recommended_commit_paths
    - recommended_commit_message
    - recommended_commit_command
    """
    return {
        "action": result.action,
        "status": result.status,
        "operation": result.operation,
        "source_path": result.source_path,
        "project_path": result.project_path,
        "touched_paths": list(result.touched_paths),
        "recommended_commit_paths": list(result.recommended_commit_paths),
        "recommended_commit_message": result.recommended_commit_message,
        "recommended_commit_command": result.recommended_commit_command,
    }


def render_route_markdown(payload: RoutePayload) -> str:
    """Render the compact route contract as the shared human-readable surface.

    CLI `distill route` should use this renderer instead of building markdown at
    the callsite so the route text surface stays aligned with the JSON contract.
    """
    return _render_plan_markdown(payload, include_action_status=False)


def render_plan_markdown(payload: PlanPayload) -> str:
    """Render the full plan contract as the shared human-readable surface.

    CLI `distill plan` should use this renderer so action/status and route fields
    are presented consistently across human-facing surfaces.
    """
    return _render_plan_markdown(payload, include_action_status=True)


def render_apply_markdown(payload: ApplyPayload, *, verb: str) -> str:
    """Render the applied result contract as the shared human-readable surface.

    CLI `distill capture` and `distill apply` should both call this renderer so
    execution-result text stays aligned with the shared apply payload.
    """
    lines = [
        f"✓ {verb}",
        f"Source: {payload.get('source_path')}",
    ]
    if payload.get("project_path"):
        lines.append(f"Project: {payload['project_path']}")
    lines.append("Touched paths:")
    for path in payload.get("touched_paths", []):
        lines.append(f"  - {path}")
    return "\n".join(lines)


def _render_plan_markdown(payload: dict[str, Any], *, include_action_status: bool) -> str:
    lines: list[str] = []
    if include_action_status:
        lines.append(f"Action: {payload.get('action')}")
        lines.append(f"Status: {payload.get('status')}")
    lines.append(f"Operation: {payload.get('operation')}")
    lines.append(f"Confidence: {payload.get('confidence')}")
    lines.append(f"Target project: {payload.get('target_project') or '-'}")
    lines.append("Read paths:")
    for path in payload.get("read_paths", []):
        lines.append(f"  - {path}")
    lines.append("Write paths:")
    for path in payload.get("write_paths", []):
        lines.append(f"  - {path}")
    if payload.get("optional_paths"):
        lines.append("Optional paths:")
        for path in payload["optional_paths"]:
            lines.append(f"  - {path}")
    lines.append("Skip steps:")
    for step in payload.get("skip_steps", []):
        lines.append(f"  - {step}")
    if payload.get("recommended_commit_command"):
        lines.append("Recommended commit:")
        lines.append(f"  {payload['recommended_commit_command']}")
    if payload.get("warnings"):
        lines.append("Warnings:")
        for item in payload["warnings"]:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def route_intent(vault_root: Path | str, intent: str, project_hint: str | None = None) -> RoutePayload:
    """Return the compact route contract for a user intent.

    This is the public low-noise planner used by CLI `distill route` and MCP
    `projection_route` for read/write boundary discovery.
    """
    plan = route_plan(vault_root, intent, project_hint=project_hint)
    return build_route_payload(plan)


def route_plan(vault_root: Path | str, intent: str, project_hint: str | None = None) -> PlanPayload:
    """Return the full plan contract for a user intent.

    This is the richer machine-oriented runtime API used by CLI `distill plan`
    and MCP `projection_plan`. It includes normalized action/status fields in
    addition to the minimal route boundary.
    """
    vault = Path(vault_root).expanduser().resolve()
    config = load_config(vault)
    index = VaultIndex(vault, config=config)
    index.scan()

    normalized_intent = (intent or "").strip()
    lowered = normalized_intent.lower()
    project_obj = _find_project(index, normalized_intent, project_hint)

    if project_obj and any(token in lowered for token in FORWARD_LOOKING_HINTS):
        return build_plan_payload(
            action="knowledge_capture",
            status="needs_disambiguation",
            intent=normalized_intent,
            operation="fact_capture",
            confidence="low",
            target_project=project_obj["title"],
            read_paths=[project_obj["path"]],
            write_paths=[],
            skip_steps=["project dossier write"],
            why=["intent mixes completed facts with schedule or future work"],
            warnings=[
                "Project dossiers only accept completed facts; remove next steps, plans, and pending work before applying."
            ],
        )

    if project_obj and any(token in lowered for token in FACT_HINTS):
        source_path = _today_source_path(config, vault)
        existing_source = source_path if (vault / source_path).exists() else source_path
        project_path = project_obj["path"]
        commit_message = _recommended_commit_message(project_obj["title"])
        commit_paths = [source_path, project_path]
        return build_plan_payload(
            action="knowledge_capture",
            status="planned",
            intent=normalized_intent,
            operation="fact_capture",
            confidence="high",
            target_project=project_obj["title"],
            read_paths=[project_path, existing_source],
            write_paths=commit_paths,
            optional_paths=[],
            skip_steps=[
                "distill run",
                "repo-wide lint",
                "repo-wide index maintenance",
            ],
            recommended_commit_paths=commit_paths,
            recommended_commit_message=commit_message,
            recommended_commit_command=recommended_commit_command(vault, commit_paths, commit_message),
            why=[
                "matched existing project object",
                "intent contains a completed or verified fact",
            ],
            warnings=[],
        )

    warnings = []
    confidence = "low"
    if not project_obj:
        warnings.append("No matching project object found; provide --project to narrow the route.")
    return build_plan_payload(
        action="generic_update",
        status="needs_disambiguation",
        intent=normalized_intent,
        operation="generic_update",
        confidence=confidence,
        target_project=project_obj["title"] if project_obj else None,
        read_paths=[project_obj["path"]] if project_obj else [],
        write_paths=[],
        optional_paths=[],
        skip_steps=["distill run", "repo-wide index maintenance"],
        recommended_commit_paths=[],
        recommended_commit_message=None,
        recommended_commit_command=None,
        why=["no deterministic minimal capture route available"],
        warnings=warnings,
    )


def _find_project(index: VaultIndex, intent: str, project_hint: str | None = None) -> dict[str, Any] | None:
    hint = (project_hint or "").strip()
    candidates = [obj for obj in index.objects if obj.get("type") == "project"]
    if hint:
        for obj in candidates:
            if obj.get("title") == hint or Path(obj["path"]).stem == hint:
                return obj
    for obj in candidates:
        title = obj.get("title", "")
        stem = Path(obj["path"]).stem
        if title and title in intent:
            return obj
        if stem and stem in intent:
            return obj
    return None


def _today_source_path(config: dict[str, Any], vault_root: Path) -> str:
    today = _today_iso()
    zh_root = Path("知识") / "来源"
    en_root = Path("knowledge") / "source"
    if (vault_root / "知识").exists():
        return str(zh_root / f"{today}-碎碎念.md")
    if (vault_root / "knowledge").exists():
        return str(en_root / f"{today}-notes.md")
    if zh_root.as_posix() in str(config.get("objects", {}).get("path_type_map", {})):
        return str(zh_root / f"{today}-碎碎念.md")
    return str(en_root / f"{today}-notes.md")


def _recommended_commit_message(project_title: str | None) -> str:
    title = (project_title or "知识").strip() or "知识"
    return f"知识库: 记录{title}成果"



def capture_progress_update(
    vault_root: Path | str,
    intent: str,
    *,
    project_hint: str | None = None,
) -> CaptureResult:
    """Execute the completed-fact capture path and return the applied result.

    This is the write-side runtime API behind CLI `distill capture`,
    `distill apply`, and MCP `projection_apply`.
    """
    plan = route_plan(vault_root, intent, project_hint=project_hint)
    if plan.get("operation") != "fact_capture" or plan.get("status") != "planned":
        warnings = "; ".join(plan.get("warnings", [])) or "route did not resolve to fact_capture"
        raise ValueError(warnings)

    vault = Path(vault_root)
    source_path = plan["write_paths"][0]
    project_path = plan["write_paths"][1] if len(plan.get("write_paths", [])) > 1 else None

    _append_progress_source(
        vault / source_path,
        intent,
        vault,
        project_path=project_path,
    )
    if project_path:
        _refresh_project_dossier(vault / project_path, source_path, intent, vault)

    touched = [source_path]
    if project_path:
        touched.append(project_path)
    project_title = plan.get("target_project")
    commit_message = plan.get("recommended_commit_message") or _recommended_commit_message(project_title)
    commit_command = plan.get("recommended_commit_command") or recommended_commit_command(vault, touched, commit_message)
    return CaptureResult(
        action="knowledge_capture",
        status="applied",
        operation="fact_capture",
        source_path=source_path,
        project_path=project_path,
        touched_paths=touched,
        recommended_commit_paths=touched,
        recommended_commit_message=commit_message,
        recommended_commit_command=commit_command,
    )


def _append_progress_source(
    path: Path,
    intent: str,
    vault_root: Path,
    *,
    project_path: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        post = frontmatter.load(str(path))
        body = post.content.rstrip()
        bullet = f"- {intent.strip()}"
        if bullet not in body.splitlines():
            body = f"{body}\n{bullet}".strip()
        post.content = body + "\n"
    else:
        title = f"{_today_iso()} notes" if "knowledge/source" in str(path) else f"{_today_iso()} 碎碎念"
        post = frontmatter.Post(f"- {intent.strip()}\n", **{
            "title": title,
        })
    _ensure_capture_source_metadata(post, path, project_path=project_path)
    atomic_write_text(path, _dump_frontmatter(post), root=vault_root)


def _ensure_capture_source_metadata(
    post: frontmatter.Post,
    path: Path,
    *,
    project_path: str | None,
) -> None:
    """Complete the portable v3 Source contract for fact-capture evidence."""
    post.metadata.setdefault("id", f"source-{path.stem}")
    post.metadata["type"] = "source"
    post.metadata.setdefault("title", path.stem)
    post.metadata.setdefault("source_type", "conversation")
    post.metadata.setdefault("created_at", _today_iso())
    post.metadata.setdefault("source_url", None)
    post.metadata.setdefault("author", None)
    post.metadata.setdefault("reliability", "high")
    post.metadata["status"] = "linked"
    post.metadata.setdefault("lifecycle_stage", "linked")

    projects = post.metadata.get("projects") or []
    if not isinstance(projects, list):
        projects = [projects]
    if project_path:
        project_link = f"[[{project_path.removesuffix('.md')}]]"
        if project_link not in projects:
            projects.append(project_link)
    post.metadata["projects"] = projects
    for field in ("concepts", "entities", "outputs"):
        value = post.metadata.get(field) or []
        post.metadata[field] = value if isinstance(value, list) else [value]


def _dump_frontmatter(post: frontmatter.Post) -> str:
    """Serialize a post with one trailing newline for stable Git diffs."""
    return frontmatter.dumps(post).rstrip() + "\n"


def _refresh_project_dossier(path: Path, source_path: str, intent: str, vault_root: Path) -> None:
    if not path.exists():
        return
    post = frontmatter.load(str(path))
    post.metadata["updated"] = _today_iso()
    post.metadata.pop("current_focus", None)
    post.metadata.pop("next_step", None)
    sources = post.metadata.get("sources") or []
    if not isinstance(sources, list):
        sources = [sources]
    source_link = f"[[{source_path.removesuffix('.md')}]]"
    if source_link not in sources:
        sources.append(source_link)
    post.metadata["sources"] = sources
    body = post.content.rstrip()
    summary_line = f"- {_today_iso()}: {intent.strip()}"
    if "## 已验证事实" in body:
        if summary_line not in body:
            body = body.replace("## 已验证事实", f"## 已验证事实\n{summary_line}", 1)
    elif "## Verified Facts" in body:
        if summary_line not in body:
            body = body.replace("## Verified Facts", f"## Verified Facts\n{summary_line}", 1)
    elif "## 已完成成果" in body:
        if summary_line not in body:
            body = body.replace("## 已完成成果", f"## 已完成成果\n{summary_line}", 1)
    elif "## Completed Outcomes" in body:
        if summary_line not in body:
            body = body.replace("## Completed Outcomes", f"## Completed Outcomes\n{summary_line}", 1)
    else:
        if body:
            body = f"{body}\n\n## 已验证事实\n{summary_line}"
        else:
            body = f"# {title}\n\n## 已验证事实\n{summary_line}\n"
    post.content = body + ("\n" if not body.endswith("\n") else "")
    atomic_write_text(path, _dump_frontmatter(post), root=vault_root)


__all__ = [
    "CaptureResult",
    "PlanPayload",
    "RoutePayload",
    "ApplyPayload",
    "build_plan_payload",
    "build_route_payload",
    "build_apply_payload",
    "render_route_markdown",
    "render_plan_markdown",
    "render_apply_markdown",
    "route_intent",
    "route_plan",
    "capture_progress_update",
]
