"""Instance-upgrade runtime surface for aligning a vault with current distill engine capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .capabilities import CapabilityPayload, collect_capabilities
from .config import load_config
from .index import VaultIndex

LEGACY_RUNTIME_DOC_PATTERNS = [
    "AGENTS.md",
    "系统/技能/*.md",
    "system/skills/*.md",
    "系统/运行时/*.md",
    "system/runtime/*.md",
]
CURRENT_RUNTIME_COMMANDS = ["distill route", "distill plan", "distill capture", "distill apply"]
LEGACY_HINT_COMMANDS = ["distill status", "distill lint", "distill run"]


class DoctorPayload(TypedDict):
    """Canonical doctor payload for engine→instance runtime adoption checks."""

    engine_version: str
    runtime_stage: str
    has_checkpoint: bool
    install_mode: str
    editable_source_path: str | None
    adoption_status: str
    capability_gaps: list[str]
    recommended_actions: list[str]
    warnings: list[str]
    legacy_runtime_docs: list[str]


class UpgradePlanPayload(TypedDict):
    """Canonical upgrade-plan payload for instance runtime adoption work."""

    action: str
    status: str
    target: str
    summary: str
    steps: list[str]
    warnings: list[str]


def _iter_runtime_docs(vault_root: Path) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in LEGACY_RUNTIME_DOC_PATTERNS:
        for path in vault_root.glob(pattern):
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            candidates.append(path)
    return sorted(candidates)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _is_legacy_runtime_doc(text: str) -> bool:
    lowered = text.lower()
    mentions_current = any(command in lowered for command in CURRENT_RUNTIME_COMMANDS)
    mentions_legacy = any(command in lowered for command in LEGACY_HINT_COMMANDS)
    return mentions_legacy and not mentions_current


def _relative_to_vault(path: Path, vault_root: Path) -> str:
    try:
        return path.relative_to(vault_root).as_posix()
    except ValueError:
        return str(path)


def _engine_authority_gaps(vault_root: Path, capabilities: CapabilityPayload) -> list[str]:
    runtime = load_config(vault_root).get("runtime", {})
    gaps: list[str] = []
    expected_version = runtime.get("engine_version")
    if expected_version and str(expected_version) != capabilities["engine_version"]:
        gaps.append(
            f"Configured engine version {expected_version} does not match imported engine {capabilities['engine_version']}."
        )
    expected_source = runtime.get("editable_source_path")
    actual_source = capabilities.get("editable_source_path")
    if expected_source and (
        not actual_source
        or Path(str(expected_source)).expanduser().resolve() != Path(actual_source).expanduser().resolve()
    ):
        gaps.append(
            f"Configured editable source {expected_source} does not match imported engine source {actual_source or 'none'}."
        )
    return gaps


def _capability_gaps(
    legacy_runtime_docs: list[str],
    index: VaultIndex,
    engine_authority_gaps: list[str],
) -> list[str]:
    gaps: list[str] = []
    gaps.extend(engine_authority_gaps)
    if legacy_runtime_docs:
        gaps.append("Legacy runtime docs still describe distill status/lint/run but do not adopt distill route/plan/capture/apply.")
    if not index.has_checkpoint():
        gaps.append("Vault has no checkpoint yet, so runtime adoption should follow the preflight path before trusting graph-derived output.")
    if index.runtime_stage() == "needs_attention":
        gaps.append("Vault runtime still has broken links or true orphans, so instance upgrade should include cleanup before claiming a trusted runtime.")
    return gaps


def _recommended_actions(
    legacy_runtime_docs: list[str],
    index: VaultIndex,
    engine_authority_gaps: list[str],
) -> list[str]:
    actions: list[str] = []
    if engine_authority_gaps:
        actions.append("Activate or install the configured Distill engine, then rerun `distill capabilities --format json`.")
    if legacy_runtime_docs:
        actions.append("Run `distill capabilities` to inspect the current engine runtime surface.")
        actions.append("Replace legacy small-task guidance in runtime docs with `distill route`, `distill plan`, `distill capture`, and `distill apply`.")
        actions.append("Run `distill upgrade-plan` for the minimal engine→instance adoption checklist.")
    if not index.has_checkpoint():
        actions.append("Run `distill lint` first, then `distill run`, before declaring the instance aligned with the runtime.")
    elif index.runtime_stage() == "needs_attention":
        actions.append("Repair the current runtime blockers, then rerun `distill doctor --instance-upgrade` to verify trusted-runtime adoption.")
    if not actions:
        actions.append("No instance-runtime upgrade is currently required.")
    return actions


def doctor_instance(vault_root: Path | str) -> DoctorPayload:
    """Return the canonical engine→instance doctor payload for runtime adoption checks."""
    vault = Path(vault_root)
    capabilities: CapabilityPayload = collect_capabilities()
    engine_authority_gaps = _engine_authority_gaps(vault, capabilities)
    index = VaultIndex(vault)
    index.scan()
    legacy_docs = [
        _relative_to_vault(path, vault)
        for path in _iter_runtime_docs(vault)
        if _is_legacy_runtime_doc(_read_text(path))
    ]
    adoption_status = "current"
    if legacy_docs or engine_authority_gaps:
        adoption_status = "upgrade_recommended"
    elif not index.has_checkpoint() or index.runtime_stage() != "trusted_runtime":
        adoption_status = "review_required"
    warnings: list[str] = []
    if not index.has_checkpoint():
        warnings.append("No checkpoint detected; runtime adoption checks are operating in preflight mode.")
    if legacy_docs:
        warnings.append("Legacy runtime docs were detected and should be updated to the compact route/plan/apply surface.")
    if engine_authority_gaps:
        warnings.append("The vault is configured for a different Distill engine version or source path.")
    if index.runtime_stage() == "needs_attention":
        warnings.append("The vault runtime still needs attention before it can be treated as a fully trusted runtime.")
    return {
        "engine_version": capabilities["engine_version"],
        "runtime_stage": index.runtime_stage(),
        "has_checkpoint": index.has_checkpoint(),
        "install_mode": capabilities["install_mode"],
        "editable_source_path": capabilities["editable_source_path"],
        "adoption_status": adoption_status,
        "capability_gaps": _capability_gaps(legacy_docs, index, engine_authority_gaps),
        "recommended_actions": _recommended_actions(legacy_docs, index, engine_authority_gaps),
        "warnings": warnings,
        "legacy_runtime_docs": legacy_docs,
    }


def build_upgrade_plan(vault_root: Path | str) -> UpgradePlanPayload:
    """Build the canonical instance-runtime upgrade plan from doctor findings."""
    vault = Path(vault_root)
    doctor = doctor_instance(vault)
    steps: list[str] = []
    status = "not_needed"
    summary = "Instance runtime already matches the current engine surface."
    if doctor["adoption_status"] != "current":
        status = "planned"
        summary = "Align vault runtime docs and operating flow with the current engine surfaces."
        if doctor["legacy_runtime_docs"]:
            steps.append("Update legacy runtime docs to reference distill route/plan/capture/apply for small knowledge tasks.")
        if not doctor["has_checkpoint"]:
            steps.append("Run distill lint and distill run so the instance has a checkpoint-backed runtime before adopting trusted-runtime guidance.")
        if doctor["runtime_stage"] == "needs_attention":
            steps.append("Clear broken links or true orphans before declaring the instance fully upgraded.")
        steps.append("Re-run distill doctor --instance-upgrade and confirm the adoption status is current or review_required without legacy-doc gaps.")
    if not steps:
        steps.append("No action required.")
    return {
        "action": "instance_runtime_upgrade",
        "status": status,
        "target": str(vault),
        "summary": summary,
        "steps": steps,
        "warnings": list(doctor["warnings"]),
    }


def render_doctor_markdown(payload: DoctorPayload) -> str:
    """Render the shared human-readable doctor surface for instance runtime checks."""
    lines = [
        "[Instance Doctor]",
        f"  engine_version: {payload['engine_version']}",
        f"  runtime_stage: {payload['runtime_stage']}",
        f"  has_checkpoint: {payload['has_checkpoint']}",
        f"  install_mode: {payload['install_mode']}",
        f"  editable_source_path: {payload['editable_source_path'] or '-'}",
        f"  adoption_status: {payload['adoption_status']}",
        "  capability_gaps:",
    ]
    for item in payload["capability_gaps"] or ["none"]:
        lines.append(f"    - {item}")
    lines.append("  recommended_actions:")
    for item in payload["recommended_actions"] or ["none"]:
        lines.append(f"    - {item}")
    lines.append("  legacy_runtime_docs:")
    for item in payload["legacy_runtime_docs"] or ["none"]:
        lines.append(f"    - {item}")
    if payload["warnings"]:
        lines.append("  warnings:")
        for item in payload["warnings"]:
            lines.append(f"    - {item}")
    return "\n".join(lines)


def render_upgrade_plan_markdown(payload: UpgradePlanPayload) -> str:
    """Render the shared human-readable instance upgrade plan surface."""
    lines = [
        "[Instance Upgrade Plan]",
        f"  action: {payload['action']}",
        f"  status: {payload['status']}",
        f"  target: {payload['target']}",
        f"  summary: {payload['summary']}",
        "  steps:",
    ]
    for item in payload["steps"]:
        lines.append(f"    - {item}")
    if payload["warnings"]:
        lines.append("  warnings:")
        for item in payload["warnings"]:
            lines.append(f"    - {item}")
    return "\n".join(lines)


__all__ = [
    "DoctorPayload",
    "UpgradePlanPayload",
    "doctor_instance",
    "build_upgrade_plan",
    "render_doctor_markdown",
    "render_upgrade_plan_markdown",
]
