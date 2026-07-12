"""Engine capability surface for distill-vault runtime adoption and upgrade checks."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TypedDict

from . import __version__
from .worker_pool import WorkerPool

SUPPORTED_RUNTIME_SURFACES = [
    "projection_route",
    "projection_plan",
    "projection_apply",
    "promotion_review",
    "promotion_apply",
    "vault_status",
    "lint_check",
    "lint_fix",
    "pipeline_run",
    "pipeline_status",
]

STATUS_FIELDS = [
    "total_objects",
    "type_distribution",
    "status_distribution",
    "total_wikilinks",
    "broken_links",
    "orphan_objects",
    "true_orphans",
    "system_docs",
    "runtime_stage",
    "has_checkpoint",
    "scan_roots",
    "vault_layout",
    "next_steps",
]

WORKER_POOL_MODES = ["auto", "process", "thread", "serial"]


class CapabilityPayload(TypedDict):
    """Canonical engine-capabilities payload for CLI/MCP runtime adoption checks."""

    engine_version: str
    module_path: str
    executable_path: str
    python_path: str
    install_mode: str
    editable_source_path: str | None
    supported_commands: list[str]
    supported_runtime_surfaces: list[str]
    status_fields: list[str]
    worker_pool_modes: list[str]


def _detect_engine_version() -> str:
    """Return the version shipped by the imported engine, including editable installs."""
    return __version__


def _module_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _detect_install_mode(source_root: Path) -> tuple[str, str | None]:
    editable_markers = [source_root / "setup.py", source_root / "README.md", source_root / "distill"]
    if all(marker.exists() for marker in editable_markers):
        return "editable", str(source_root)
    if source_root.name == "site-packages":
        return "installed", None
    return "source_tree", str(source_root) if source_root.exists() else None


def _supported_commands() -> list[str]:
    from .cli import cli as root_cli

    return sorted(root_cli.commands.keys())


def collect_capabilities() -> CapabilityPayload:
    """Collect the canonical engine capability payload for CLI and MCP surfaces."""
    module_path = Path(__file__).resolve().parent / "__init__.py"
    source_root = _module_root()
    install_mode, editable_source_path = _detect_install_mode(source_root)
    executable_path = shutil.which("distill") or sys.argv[0] or sys.executable
    worker_pool_modes = [mode for mode in WORKER_POOL_MODES if mode in WorkerPool.VALID_MODES]
    return {
        "engine_version": _detect_engine_version(),
        "module_path": str(module_path),
        "executable_path": str(Path(executable_path).resolve()),
        "python_path": str(Path(sys.executable).resolve()),
        "install_mode": install_mode,
        "editable_source_path": editable_source_path,
        "supported_commands": _supported_commands(),
        "supported_runtime_surfaces": list(SUPPORTED_RUNTIME_SURFACES),
        "status_fields": list(STATUS_FIELDS),
        "worker_pool_modes": worker_pool_modes,
    }


def render_capabilities_markdown(payload: CapabilityPayload) -> str:
    """Render the engine-capabilities payload as a shared human-readable surface."""
    lines = [
        "[Engine Capabilities]",
        f"  engine_version: {payload['engine_version']}",
        f"  install_mode: {payload['install_mode']}",
        f"  module_path: {payload['module_path']}",
        f"  executable_path: {payload['executable_path']}",
        f"  python_path: {payload['python_path']}",
        f"  editable_source_path: {payload['editable_source_path'] or '-'}",
        "  supported_commands:",
    ]
    for item in payload["supported_commands"]:
        lines.append(f"    - {item}")
    lines.append("  supported_runtime_surfaces:")
    for item in payload["supported_runtime_surfaces"]:
        lines.append(f"    - {item}")
    lines.append("  status_fields:")
    for item in payload["status_fields"]:
        lines.append(f"    - {item}")
    lines.append(f"  worker_pool_modes: {payload['worker_pool_modes']}")
    return "\n".join(lines)


__all__ = [
    "CapabilityPayload",
    "collect_capabilities",
    "render_capabilities_markdown",
]
