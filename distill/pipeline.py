"""Composable vault pipeline with deterministic exported artifacts.

Features:
- Declarative phase dependencies with typed inputs/outputs
- Kahn's topological sort with cycle detection (DFS path tracing)
- Incremental updates via content-hash checkpoints
- Staleness detection (compare checkpoint commit vs HEAD)
- Progress events: start → progress → complete/error
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import hashlib
import json
import time

from .atomic_io import atomic_write_text
from .config import get_ops_dir, get_scan_dirs, load_config


class PhaseError(Exception):
    """Error wrapper that preserves phase name and original cause."""
    def __init__(self, phase_name: str, cause: Exception):
        self.phase_name = phase_name
        self.cause = cause
        super().__init__(f"Phase '{phase_name}' failed: {cause}")


class Phase:
    """A single pipeline phase with declared dependencies."""
    
    def __init__(self, name: str, deps: List[str], fn: Callable,
                 description: str = ""):
        self.name = name
        self.deps = deps
        self.fn = fn
        self.description = description or name
        self.duration = 0.0
        self.objects_processed = 0
        self.errors: List[str] = []
        self.cached = False
        self._output = None

    def reset(self):
        self.duration = 0.0
        self.objects_processed = 0
        self.errors = []
        self.cached = False
        self._output = None
    
    def run(self, ctx: "PipelineContext") -> Any:
        self.cached = False
        start = time.time()
        try:
            result = self.fn(ctx)
            self.duration = time.time() - start
            self._output = result
            return result
        except Exception as e:
            self.duration = time.time() - start
            self.errors.append(str(e))
            raise PhaseError(self.name, e) from e
    
    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.cached:
            return "cached"
        if self.duration > 0:
            return "complete"
        return "pending"


class PipelineContext:
    """Shared context for pipeline execution.
    
    Each phase reads inputs via get() and writes outputs via set().
    Only declared deps are accessible — prevents implicit coupling.
    """
    
    def __init__(self, vault_root: Path, worker_pool=None, config=None):
        self.vault = Path(vault_root).expanduser().resolve()
        self.config = config or load_config(self.vault)
        self.results: Dict[str, Any] = {}
        self.changed_files: List[str] = []
        self.stats: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.worker_pool = worker_pool
        self._events: List[Dict] = []
    
    def get(self, key: str, default=None) -> Any:
        return self.results.get(key, default)
    
    def set(self, key: str, value: Any):
        self.results[key] = value
    
    def emit(self, event_type: str, data: dict = None):
        """Emit a progress event."""
        self._events.append({
            "type": event_type,
            "phase": data.get("phase", "") if data else "",
            "data": data or {},
            "timestamp": time.time(),
        })


def _stable_value(value):
    if isinstance(value, dict):
        return {k: _stable_value(value[k]) for k in sorted(value)}
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, list):
        normalized = [_stable_value(item) for item in value]
        try:
            return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        except TypeError:
            return normalized
    return value


def _hash_file(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def compute_file_hashes(vault_root: Path, config: Optional[dict] = None) -> Dict[str, str]:
    vault_root = Path(vault_root).expanduser().resolve()
    config = config or load_config(vault_root)
    ops_dir = get_ops_dir(config, vault_root)
    hashes: Dict[str, str] = {}

    for dir_path in get_scan_dirs(config, vault_root):
        if not dir_path.exists():
            continue
        for file_path in dir_path.rglob("*.md"):
            if ops_dir in file_path.parents:
                continue
            try:
                rel = str(file_path.relative_to(vault_root))
                hashes[rel] = _hash_file(file_path)
            except Exception:
                continue

    return dict(sorted(hashes.items()))


class PipelineDAG:
    """DAG-based pipeline runner with topological sort execution.
    
    Features:
    - Kahn's algorithm for topological ordering
    - Cycle detection with DFS path tracing
    - Incremental execution via content-hash checkpoints
    - Staleness detection
    """
    
    def __init__(self, vault_root: Path, worker_pool=None, config=None):
        self.vault = Path(vault_root).expanduser().resolve()
        self.config = config or load_config(self.vault)
        self.phases: Dict[str, Phase] = {}
        self.ctx = PipelineContext(vault_root, worker_pool=worker_pool, config=self.config)
        self._execution_order: List[str] = []
    
    def register(self, name: str, deps: List[str] = None,
                 description: str = ""):
        """Decorator to register a phase with declared dependencies."""
        def decorator(fn: Callable):
            self.phases[name] = Phase(name, deps or [], fn, description)
            return fn
        return decorator
    
    def _topological_sort(self) -> List[str]:
        """Kahn's algorithm with cycle detection.
        
        If cycle detected, DFS traces the exact cycle path for debugging.
        """
        in_degree: Dict[str, int] = {name: 0 for name in self.phases}
        adj: Dict[str, List[str]] = defaultdict(list)
        
        for name, phase in self.phases.items():
            for dep in phase.deps:
                if dep in self.phases:
                    adj[dep].append(name)
                    in_degree[name] += 1
                # Unknown deps are silently ignored (external deps)
        
        queue = deque(n for n, d in in_degree.items() if d == 0)
        ordered = []
        
        while queue:
            node = queue.popleft()
            ordered.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(ordered) != len(self.phases):
            # DFS to find the exact cycle
            cycle = self._find_cycle()
            cycle_str = " -> ".join(cycle + [cycle[0]])
            raise ValueError(f"Pipeline has circular dependencies: {cycle_str}")
        
        self._execution_order = ordered
        return ordered
    
    def _find_cycle(self) -> List[str]:
        """DFS to trace the first cycle in the dependency graph."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in self.phases}
        parent: Dict[str, str] = {}
        
        def dfs(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            for dep in self.phases[node].deps:
                if dep not in self.phases:
                    continue
                if color[dep] == GRAY:
                    # Found cycle — trace path
                    cycle = [dep, node]
                    curr = node
                    while curr in parent:
                        curr = parent[curr]
                        cycle.append(curr)
                        if curr == dep:
                            break
                    return list(reversed(cycle))
                if color[dep] == WHITE:
                    parent[dep] = node
                    result = dfs(dep)
                    if result:
                        return result
            color[node] = BLACK
            return None
        
        for name in self.phases:
            if color[name] == WHITE:
                result = dfs(name)
                if result:
                    return result
        return []
    
    def run(self, incremental: bool = False) -> Dict[str, Any]:
        """Execute all phases in topological order.
        
        Args:
            incremental: If True, skip phases whose inputs haven't changed.
        
        Returns:
            Dict of phase_name -> {duration, objects, errors}
        """
        order = self._topological_sort()
        for phase in self.phases.values():
            phase.reset()

        # Load checkpoint for incremental
        checkpoint = self._load_checkpoint() if incremental else {}
        checkpoint_hashes = checkpoint.get("file_hashes", {})
        if incremental and checkpoint_hashes:
            self.ctx.set("file_hashes", compute_file_hashes(self.vault, config=self.config))
        changed_phases: Set[str] = set()
        
        results = {}
        for phase_name in order:
            phase = self.phases[phase_name]
            
            # Check if we can skip (incremental mode)
            if incremental and phase_name in checkpoint.get("phases", {}):
                deps_changed = any(
                    d in changed_phases
                    for d in phase.deps if d in self.phases
                )
                input_changed = self._has_input_changed(
                    phase_name, checkpoint_hashes
                )
                if not deps_changed and not input_changed:
                    cached_result = checkpoint["phases"][phase_name]
                    phase.cached = True
                    phase.objects_processed = int(cached_result.get("objects", 0) or 0)
                    phase.errors = list(cached_result.get("errors", []) or [])
                    results[phase_name] = cached_result
                    continue
            
            # Emit start event
            self.ctx.emit("start", {"phase": phase_name})
            
            phase.run(self.ctx)
            results[phase_name] = {
                "duration": round(phase.duration, 3),
                "objects": phase.objects_processed,
                "errors": _stable_value(phase.errors),
            }
            changed_phases.add(phase_name)
            
            # Emit complete event
            self.ctx.emit("complete", {
                "phase": phase_name,
                "duration": phase.duration,
                "objects": phase.objects_processed,
            })
        
        self._save_checkpoint(results)
        return results
    
    def _has_input_changed(self, phase_name: str,
                           old_hashes: Dict[str, int]) -> bool:
        """Check if any input files for a phase have changed."""
        current_hashes = self.ctx.get("file_hashes", {})
        if not old_hashes or not current_hashes:
            return True
        
        # Any new or modified files means inputs changed
        for path, h in current_hashes.items():
            if old_hashes.get(path) != h:
                return True
        
        # Any deleted files
        for path in old_hashes:
            if path not in current_hashes:
                return True
        
        return False
    
    def _load_checkpoint(self) -> dict:
        cp_path = self.vault / ".distill" / "checkpoint.json"
        if cp_path.exists():
            try:
                return json.loads(cp_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}
    
    def _save_checkpoint(self, results: dict):
        cp_path = self.vault / ".distill" / "checkpoint.json"
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "phases": {
                phase_name: {
                    "objects": result.get("objects", 0),
                    "errors": _stable_value(result.get("errors", [])),
                }
                for phase_name, result in results.items()
            },
            "file_hashes": dict(sorted(self.ctx.get("file_hashes", {}).items())),
        }
        worker_pool = self.worker_pool_summary()
        if worker_pool:
            data["worker_pool"] = _stable_value(worker_pool)
        atomic_write_text(
            cp_path,
            json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
            root=self.vault,
        )
        self._save_runtime_state()

    def worker_pool_summary(self) -> Dict[str, Any]:
        pool = self.ctx.worker_pool
        if not pool:
            return {}

        phase_snapshot = self.ctx.metadata.get("worker_pool_phases", {}) or {}
        ordered_phase_names = [name for name in (self._execution_order or ["scan", "parse"]) if name in phase_snapshot]
        last_phase = phase_snapshot.get(ordered_phase_names[-1], {}) if ordered_phase_names else {}
        fallback_reason = None
        for item in self.ctx.metadata.get("worker_pool_fallback_history", []) or []:
            reason = item.get("fallback_reason")
            if reason:
                fallback_reason = reason
                break
        for name in ordered_phase_names:
            reason = (phase_snapshot.get(name) or {}).get("fallback_reason")
            if reason and not fallback_reason:
                fallback_reason = reason
        if not fallback_reason:
            for name in sorted(phase_snapshot):
                reason = (phase_snapshot.get(name) or {}).get("fallback_reason")
                if reason:
                    fallback_reason = reason
                    break

        return {
            "requested_mode": pool.mode,
            "fallback_mode": pool.fallback_mode,
            "workers": pool.workers,
            "timeout": pool.timeout,
            "last_mode": last_phase.get("last_mode") or pool.last_mode,
            "fallback_used": any(bool((phase_snapshot.get(name) or {}).get("fallback_used")) for name in phase_snapshot) or bool(pool.fallback_used),
            "fallback_reason": fallback_reason or pool.fallback_reason,
            "phases": {name: phase_snapshot[name] for name in sorted(phase_snapshot)},
        }

    def worker_pool_report(self) -> str:
        summary = self.worker_pool_summary()
        if not summary:
            return ""

        def _bool_label(value: Any) -> str:
            return "true" if bool(value) else "false"

        lines = [
            "[Worker Pool]",
            f"requested_mode: {summary.get('requested_mode')}",
            f"last_mode: {summary.get('last_mode')}",
            f"fallback_used: {_bool_label(summary.get('fallback_used'))}",
        ]
        if summary.get("fallback_reason"):
            lines.append(f"fallback_reason: {summary['fallback_reason']}")
        for phase_name, phase in summary.get("phases", {}).items():
            suffix = f"  reason={phase['fallback_reason']}" if phase.get("fallback_reason") else ""
            lines.append(
                f"- {phase_name}: last_mode={phase.get('last_mode')} fallback_used={_bool_label(phase.get('fallback_used'))}{suffix}"
            )
        return "\n".join(lines)

    def _load_runtime_state(self) -> dict:
        state_path = self.vault / ".distill" / "runtime-state.json"
        if state_path.exists():
            try:
                return json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_runtime_state(self):
        state_path = self.vault / ".distill" / "runtime-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            state_path,
            json.dumps({"timestamp": time.time()}, indent=2, ensure_ascii=False, sort_keys=True),
            root=self.vault,
        )

    def _staleness_payload(
        self,
        *,
        stale: bool,
        added: int = 0,
        removed: int = 0,
        modified: int = 0,
        last_index_time: float = 0,
        reason: str | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "stale": stale,
            "added": int(added),
            "removed": int(removed),
            "modified": int(modified),
            "total_changes": int(added) + int(removed) + int(modified),
            "last_index_time": last_index_time,
        }
        if reason:
            payload["reason"] = reason
        return payload
    
    def check_staleness(self) -> Dict[str, Any]:
        """Check if the current index is stale compared to filesystem.
        
        Inspired by GitNexus's staleness detection:
        compare last indexed commit hash with current HEAD.
        """
        runtime_state = self._load_runtime_state()
        checkpoint = self._load_checkpoint()
        if not checkpoint:
            return self._staleness_payload(
                stale=True,
                reason="no_checkpoint",
                last_index_time=runtime_state.get("timestamp", 0),
            )

        current_hashes = compute_file_hashes(self.vault, config=self.config)
        old_hashes = checkpoint.get("file_hashes", {})
        
        added = set(current_hashes) - set(old_hashes)
        removed = set(old_hashes) - set(current_hashes)
        modified = {
            k for k in set(current_hashes) & set(old_hashes)
            if current_hashes[k] != old_hashes[k]
        }

        return self._staleness_payload(
            stale=bool(added or removed or modified),
            added=len(added),
            removed=len(removed),
            modified=len(modified),
            last_index_time=runtime_state.get("timestamp", 0),
        )
    
    def report(self) -> str:
        lines = [
            "=" * 55,
            "  Pipeline Execution Report",
            "=" * 55,
        ]
        total_duration = 0
        total_objects = 0
        total_errors = 0
        
        for name in self._execution_order:
            phase = self.phases[name]
            status_icon = {"complete": "✓", "cached": "↺", "error": "✗", "pending": "○"}.get(
                phase.status, "?"
            )
            duration_label = "cached" if phase.cached else f"{phase.duration:6.3f}s"
            lines.append(
                f"  {status_icon} {name:20s} {duration_label:>6}  "
                f"({phase.objects_processed:4d} objects)"
            )
            for err in phase.errors:
                lines.append(f"    └─ ERROR: {err}")
            total_duration += phase.duration
            total_objects += phase.objects_processed
            total_errors += len(phase.errors)
        
        lines.append("-" * 55)
        lines.append(
            f"  Total: {total_duration:.3f}s | "
            f"{total_objects} objects | {total_errors} errors"
        )
        lines.append("=" * 55)
        return "\n".join(lines)

    def report_from_snapshot(self, phase_snapshot: Dict[str, Dict[str, Any]]) -> str:
        lines = [
            "=" * 55,
            "  Pipeline Checkpoint Summary",
            "=" * 55,
        ]
        total_objects = 0
        total_errors = 0

        order = list(self._execution_order)
        if not order and self.phases:
            order = self._topological_sort()
        if not order:
            order = list(phase_snapshot.keys())

        for name in order:
            if name not in phase_snapshot:
                continue
            result = phase_snapshot[name]
            errors = result.get("errors", []) or []
            objects_processed = int(result.get("objects", 0) or 0)
            status_icon = "✗" if errors else "✓"
            lines.append(
                f"  {status_icon} {name:20s} {'n/a':>6}  ({objects_processed:4d} objects)"
            )
            for err in errors:
                lines.append(f"    └─ ERROR: {err}")
            total_objects += objects_processed
            total_errors += len(errors)

        extra_names = [name for name in phase_snapshot if name not in order]
        for name in extra_names:
            result = phase_snapshot[name]
            errors = result.get("errors", []) or []
            objects_processed = int(result.get("objects", 0) or 0)
            status_icon = "✗" if errors else "✓"
            lines.append(
                f"  {status_icon} {name:20s} {'n/a':>6}  ({objects_processed:4d} objects)"
            )
            for err in errors:
                lines.append(f"    └─ ERROR: {err}")
            total_objects += objects_processed
            total_errors += len(errors)

        lines.append("-" * 55)
        lines.append(
            f"  Total: checkpoint | "
            f"{total_objects} objects | {total_errors} errors"
        )
        lines.append("=" * 55)
        return "\n".join(lines)
