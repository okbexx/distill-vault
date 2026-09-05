"""MCP tool definitions and handlers for distill-vault.

Provides a lightweight tool registry inspired by GitNexus layering:
- Discovery
- Query
- Analysis
- Action
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .atomic_io import atomic_write_text
from .capabilities import CapabilityPayload, collect_capabilities
from .community import CommunityDetector
from .graph_index import GraphIndex
from .impact import ImpactAnalyzer
from .index import VaultIndex
from .instance_upgrade import DoctorPayload, UpgradePlanPayload, build_upgrade_plan, doctor_instance
from .lint import VaultLinter
from .next_steps import guidance_from_index, guidance_from_lint
from .phases import build_pipeline
from .pipeline import PipelineDAG
from .promote import PromotionApplyPayload, PromotionReviewPayload, apply_promotion, review_promotion
from .search_hybrid import HybridSearch
from .routing import ApplyPayload, PlanPayload, RoutePayload, build_apply_payload, capture_progress_update, route_intent, route_plan
from .worker_pool import WorkerPool


class MCPToolError(Exception):
    """Raised when a tool call cannot be completed."""


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]

    def as_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class DistillMCPTools:
    """Registry and implementations for distill-vault MCP tools."""

    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root).expanduser().resolve()
        self._tools: Dict[str, MCPTool] = {}
        self._register_tools()
        self._register("source_record", "Save arbitrary text and optional file attachments as a raw inbox source; no project or fact required.", {
            "type": "object", "properties": {
                "text": {"type": "string"},
                "attachments": {"type": "array", "items": {"type": "string"}},
            }, "required": ["text"], "additionalProperties": False,
        }, self.source_record)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.as_schema() for tool in self._tools.values()]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise MCPToolError(f"Unknown tool: {name}")
        args = arguments or {}
        try:
            return tool.handler(**args)
        except TypeError as exc:
            raise MCPToolError(f"Invalid arguments for tool '{name}': {exc}") from exc
        except Exception as exc:  # pragma: no cover - runtime safety wrapper
            raise MCPToolError(str(exc)) from exc

    def _register(self, name: str, description: str, input_schema: Dict[str, Any], handler: Callable[..., Any]) -> None:
        self._tools[name] = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )

    def _register_tools(self) -> None:
        self._register(
            "vault_status",
            "Return vault overview, object counts, distributions, and health signals.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.vault_status,
        )
        self._register(
            "runtime_capabilities",
            "Return the engine capability surface exposed by this distill runtime.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.runtime_capabilities,
        )
        self._register(
            "instance_doctor",
            "Audit engine-to-instance runtime adoption for the current vault.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.instance_doctor,
        )
        self._register(
            "instance_upgrade_plan",
            "Return the engine-to-instance upgrade plan for the current vault.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.instance_upgrade_plan,
        )
        self._register(
            "vault_staleness",
            "Check whether the current vault index/checkpoint is stale.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.vault_staleness,
        )
        self._register(
            "search",
            "Hybrid vault search supporting keyword, semantic, and hybrid modes.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "default": 5},
                    "mode": {"type": "string", "enum": ["keyword", "semantic", "hybrid"], "default": "hybrid"},
                    "obj_type": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            self.search,
        )
        self._register(
            "projection_route",
            "Plan the minimal read/write surface for a knowledge task.",
            {
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "project_hint": {"type": "string"},
                },
                "required": ["intent"],
                "additionalProperties": False,
            },
            self.projection_route,
        )
        self._register(
            "projection_plan",
            "Return the full action plan for a knowledge task.",
            {
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "project_hint": {"type": "string"},
                },
                "required": ["intent"],
                "additionalProperties": False,
            },
            self.projection_plan,
        )
        self._register(
            "projection_apply",
            "Capture a short completed fact in its source and project dossier.",
            {
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "project_hint": {"type": "string"},
                },
                "required": ["intent"],
                "additionalProperties": False,
            },
            self.projection_apply,
        )
        self._register(
            "promotion_review",
            "Validate and deduplicate an agent-authored concept, decision, or constraint proposal without writing.",
            {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["source", "target", "content"],
                "additionalProperties": False,
            },
            self.promotion_review,
        )
        self._register(
            "promotion_apply",
            "Apply a reviewed semantic proposal and add the deterministic source backlink.",
            {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["source", "target", "content"],
                "additionalProperties": False,
            },
            self.promotion_apply,
        )
        self._register(
            "cypher_query",
            "Deprecated read-only compatibility query. Only legacy smoke queries are supported; use typed graph tools for new clients.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "rebuild": {"type": "boolean", "default": False},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            self.cypher_query,
        )
        self._register(
            "object_context",
            "Return object properties plus bounded incoming/outgoing links and communities.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "relation_limit": {"type": "integer", "minimum": 0, "default": 12},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            self.object_context,
        )
        self._register(
            "list_objects",
            "List objects filtered by type and/or status.",
            {
                "type": "object",
                "properties": {
                    "obj_type": {"type": "string"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "default": 100},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                },
                "additionalProperties": False,
            },
            self.list_objects,
        )
        self._register(
            "impact_upstream",
            "Analyze upstream impact: which objects depend on the target object.",
            {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "max_depth": {"type": "integer", "minimum": 1, "default": 3},
                    "edge_types": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
            self.impact_upstream,
        )
        self._register(
            "impact_downstream",
            "Analyze downstream dependencies: which objects the target depends on.",
            {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "max_depth": {"type": "integer", "minimum": 1, "default": 3},
                    "edge_types": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
            self.impact_downstream,
        )
        self._register(
            "detect_changes",
            "Analyze blast radius for a list of changed files.",
            {
                "type": "object",
                "properties": {
                    "changed_files": {"type": "array", "items": {"type": "string"}},
                    "max_depth": {"type": "integer", "minimum": 1, "default": 3},
                    "edge_types": {"type": "array", "items": {"type": "string"}},
                    "direction": {"type": "string", "enum": ["upstream", "downstream"], "default": "upstream"},
                },
                "required": ["changed_files"],
                "additionalProperties": False,
            },
            self.detect_changes,
        )
        self._register(
            "community_detect",
            "Run graph community detection and optionally persist the result.",
            {
                "type": "object",
                "properties": {
                    "persist": {"type": "boolean", "default": True},
                },
                "additionalProperties": False,
            },
            self.community_detect,
        )
        self._register(
            "community_info",
            "Return details for all communities or a single community by id.",
            {
                "type": "object",
                "properties": {
                    "community_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
            self.community_info,
        )
        self._register(
            "rename",
            "Graph-assisted rename preview or apply for object titles / link references across markdown files.",
            {
                "type": "object",
                "properties": {
                    "old_name": {"type": "string"},
                    "new_name": {"type": "string"},
                    "apply": {"type": "boolean", "default": False},
                },
                "required": ["old_name", "new_name"],
                "additionalProperties": False,
            },
            self.rename,
        )
        self._register(
            "lint_check",
            "Run vault lint checks without modifying files.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.lint_check,
        )
        self._register(
            "lint_fix",
            "Run vault lint checks and apply automatic fixes where supported.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.lint_fix,
        )
        self._register(
            "pipeline_run",
            "Run the main vault pipeline and return checkpoint-backed results.",
            {
                "type": "object",
                "properties": {
                    "incremental": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
            self.pipeline_run,
        )
        self._register(
            "pipeline_status",
            "Return main-pipeline checkpoint and staleness summary.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            self.pipeline_status,
        )

    def source_record(self, text: str, attachments: Optional[List[str]] = None) -> Dict[str, Any]:
        from .source_record import record_source
        return record_source(self.vault_root, text, attachments=attachments)

    def _make_index(self) -> VaultIndex:
        index = VaultIndex(self.vault_root)
        index.scan()
        return index

    def _make_graph(self, rebuild: bool = False) -> GraphIndex:
        graph = GraphIndex(self.vault_root)
        if rebuild or not graph.has_data():
            graph.build()
        return graph

    def _make_pipeline(self) -> PipelineDAG:
        return build_pipeline(self.vault_root, worker_pool=WorkerPool(mode="auto"))

    def _health_summary(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        broken_links = int(stats.get("broken_links", 0))
        orphan_objects = int(stats.get("orphan_objects", 0))
        true_orphans = int(stats.get("true_orphans", orphan_objects))
        system_docs = int(stats.get("system_docs", 0))
        if broken_links == 0 and true_orphans == 0:
            level = "healthy"
            reason = "clean_runtime"
        elif broken_links <= 10 and true_orphans <= 5:
            level = "warning"
            reason = "minor_runtime_issues"
        else:
            level = "critical"
            reason = "blocking_runtime_issues"
        return {
            "level": level,
            "reason": reason,
            "signals": {
                "broken_links": broken_links,
                "orphan_objects": orphan_objects,
                "true_orphans": true_orphans,
                "system_docs": system_docs,
            },
            "broken_links": broken_links,
            "orphan_objects": orphan_objects,
            "true_orphans": true_orphans,
            "system_docs": system_docs,
        }

    def vault_status(self) -> Dict[str, Any]:
        index = self._make_index()
        payload = index.status_payload()
        return {
            "vault_root": str(self.vault_root),
            "stats": index.stats,
            "health": self._health_summary(index.stats),
            **payload,
        }

    def runtime_capabilities(self) -> CapabilityPayload:
        return collect_capabilities()

    def instance_doctor(self) -> DoctorPayload:
        return doctor_instance(self.vault_root)

    def instance_upgrade_plan(self) -> UpgradePlanPayload:
        return build_upgrade_plan(self.vault_root)

    def vault_staleness(self) -> Dict[str, Any]:
        pipeline = self._make_pipeline()
        return pipeline.check_staleness()

    def search(self, query: str, limit: int = 5, mode: str = "hybrid", obj_type: Optional[str] = None) -> Dict[str, Any]:
        engine = HybridSearch(self.vault_root)
        results = engine.search(query=query, limit=limit, mode=mode, obj_type=obj_type)
        return {
            "query": query,
            "mode": mode,
            "limit": limit,
            "results": results,
            "total": len(results),
        }

    def projection_route(self, intent: str, project_hint: Optional[str] = None) -> RoutePayload:
        return route_intent(self.vault_root, intent, project_hint=project_hint)

    def projection_plan(self, intent: str, project_hint: Optional[str] = None) -> PlanPayload:
        return route_plan(self.vault_root, intent, project_hint=project_hint)

    def projection_apply(self, intent: str, project_hint: Optional[str] = None) -> ApplyPayload:
        result = capture_progress_update(self.vault_root, intent, project_hint=project_hint)
        return build_apply_payload(result)

    def promotion_review(self, source: str, target: str, content: str) -> PromotionReviewPayload:
        return review_promotion(self.vault_root, source=source, target=target, content=content)

    def promotion_apply(self, source: str, target: str, content: str) -> PromotionApplyPayload:
        return apply_promotion(self.vault_root, source=source, target=target, content=content)

    def cypher_query(self, query: str, rebuild: bool = False) -> Dict[str, Any]:
        graph = self._make_graph(rebuild=rebuild)
        rows = graph.query(query)
        return {
            "query": query,
            "rows": rows,
            "row_count": len(rows),
            "deprecated": True,
            "replacement": "Use object_context, list_objects, impact_upstream, impact_downstream, or community_info.",
        }

    def object_context(self, path: str, relation_limit: int = 12) -> Dict[str, Any]:
        index = self._make_index()
        normalized_path = self._normalize_object_path(path, index)
        target = next((obj for obj in index.objects if obj["path"] == normalized_path), None)
        if target is None:
            raise MCPToolError(f"Object not found: {path}")

        graph = self._make_graph(rebuild=False)
        incoming = self._format_link_rows(graph.incoming(normalized_path))
        outgoing = self._format_link_rows(graph.outgoing(normalized_path))

        return {
            "object": target,
            "incoming": incoming[:relation_limit],
            "outgoing": outgoing[:relation_limit],
            "relation_counts": {
                "incoming": len(incoming),
                "outgoing": len(outgoing),
            },
            "truncated": {
                "incoming": len(incoming) > relation_limit,
                "outgoing": len(outgoing) > relation_limit,
            },
            "communities": graph.object_communities(normalized_path),
        }

    def list_objects(self, obj_type: Optional[str] = None, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        index = self._make_index()
        filtered = []
        for obj in index.objects:
            if obj_type and obj.get("type") != obj_type:
                continue
            if status and obj.get("status") != status:
                continue
            filtered.append(obj)
        total = len(filtered)
        items = filtered[offset: offset + limit]
        return {
            "filters": {"obj_type": obj_type, "status": status},
            "offset": offset,
            "limit": limit,
            "total": total,
            "items": items,
        }

    def impact_upstream(self, target: str, max_depth: int = 3, edge_types: Optional[List[str]] = None) -> Dict[str, Any]:
        graph = self._make_graph(rebuild=False)
        analyzer = ImpactAnalyzer(graph)
        target_path = self._normalize_object_path(target, self._make_index())
        return analyzer.upstream(target=target_path, max_depth=max_depth, edge_types=edge_types)

    def impact_downstream(self, target: str, max_depth: int = 3, edge_types: Optional[List[str]] = None) -> Dict[str, Any]:
        graph = self._make_graph(rebuild=False)
        analyzer = ImpactAnalyzer(graph)
        target_path = self._normalize_object_path(target, self._make_index())
        return analyzer.downstream(target=target_path, max_depth=max_depth, edge_types=edge_types)

    def detect_changes(
        self,
        changed_files: List[str],
        max_depth: int = 3,
        edge_types: Optional[List[str]] = None,
        direction: str = "upstream",
    ) -> Dict[str, Any]:
        graph = self._make_graph(rebuild=False)
        analyzer = ImpactAnalyzer(graph)
        index = self._make_index()
        normalized = [self._normalize_object_path(path, index, strict=False) for path in changed_files]
        return analyzer.detect_changes(
            changed_paths=normalized,
            max_depth=max_depth,
            edge_types=edge_types,
            direction=direction,
        )

    def community_detect(self, persist: bool = True) -> Dict[str, Any]:
        graph = self._make_graph(rebuild=False)
        detector = CommunityDetector(graph)
        return detector.detect(persist=persist)

    def community_info(self, community_id: Optional[str] = None) -> Dict[str, Any]:
        graph = self._make_graph(rebuild=False)
        communities = []
        for community in graph.list_communities():
            item = dict(community)
            if community_id and item["id"] != community_id:
                continue
            item["members"] = graph.community_members(item["id"])
            communities.append(item)

        if community_id:
            if not communities:
                raise MCPToolError(f"Community not found: {community_id}")
            return communities[0]
        return {
            "total": len(communities),
            "communities": communities,
        }

    def rename(self, old_name: str, new_name: str, apply: bool = False) -> Dict[str, Any]:
        index = self._make_index()
        target_obj = next((obj for obj in index.objects if obj.get("title") == old_name), None)
        if target_obj is None:
            raise MCPToolError(f"Object title not found: {old_name}")

        target_path = target_obj["path"]
        graph = self._make_graph(rebuild=False)
        candidate_files = {target_path}
        candidate_files.update(row["path"] for row in graph.incoming(target_path))

        replacements = []
        link_pattern = re.compile(rf"\[\[{re.escape(old_name)}(\|[^\]]+)?\]\]")
        for rel_path in sorted(candidate_files):
            abs_path = self.vault_root / rel_path
            if not abs_path.exists():
                continue
            content = abs_path.read_text(encoding="utf-8")
            new_content = content
            changed = False

            if rel_path == target_path:
                new_content = re.sub(
                    r"^(title:\s*).*$",
                    rf"\1{new_name}",
                    new_content,
                    flags=re.MULTILINE,
                )
                changed = new_content != content or changed

            replaced_content = link_pattern.sub(lambda m: f"[[{new_name}{m.group(1) or ''}]]", new_content)
            if replaced_content != new_content:
                new_content = replaced_content
                changed = True

            if changed:
                replacements.append(
                    {
                        "file": rel_path,
                        "applied": apply,
                    }
                )
                if apply:
                    atomic_write_text(abs_path, new_content, root=self.vault_root)

        return {
            "old_name": old_name,
            "new_name": new_name,
            "target_path": target_path,
            "apply": apply,
            "changed_files": replacements,
            "total_changed": len(replacements),
        }

    def lint_check(self) -> Dict[str, Any]:
        linter = VaultLinter(self.vault_root)
        linter.scan()
        issues = linter.lint(fix=False)
        payload = linter.index.status_payload()
        return {
            **payload,
            "issue_count": len(issues),
            "issues": issues,
            "next_steps": guidance_from_lint(issues, vault_root=self.vault_root),
        }

    def lint_fix(self) -> Dict[str, Any]:
        linter = VaultLinter(self.vault_root)
        linter.scan()
        issues = linter.lint(fix=True)
        payload = linter.index.status_payload()
        return {
            **payload,
            "issue_count": len(issues),
            "issues": issues,
            "fix_report": linter.get_fix_report(),
            "next_steps": guidance_from_lint(issues, vault_root=self.vault_root),
        }

    def pipeline_run(self, incremental: bool = False) -> Dict[str, Any]:
        pipeline = self._make_pipeline()
        results = pipeline.run(incremental=incremental)
        return {
            "incremental": incremental,
            "results": results,
            "report": pipeline.report(),
            "worker_pool": pipeline.worker_pool_summary(),
        }

    def pipeline_status(self) -> Dict[str, Any]:
        pipeline = self._make_pipeline()
        checkpoint = pipeline._load_checkpoint()
        staleness = pipeline.check_staleness()
        phase_snapshot = checkpoint.get("phases", {}) if isinstance(checkpoint, dict) else {}
        report = pipeline.report_from_snapshot(phase_snapshot) if phase_snapshot else pipeline.report()
        return {
            "checkpoint": checkpoint,
            "staleness": staleness,
            "report": report,
            "worker_pool": checkpoint.get("worker_pool", pipeline.worker_pool_summary()) if isinstance(checkpoint, dict) else pipeline.worker_pool_summary(),
        }

    def _format_link_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "path": row["path"],
                "title": row["title"],
                "type": row["type"],
                "link_type": row["relation"],
            }
            for row in rows
        ]

    def _normalize_object_path(self, value: str, index: VaultIndex, strict: bool = True) -> str:
        if value in index._path_index:
            return value
        if value in index._title_index:
            return index._title_index[value]
        candidate = value if value.endswith(".md") else f"{value}.md"
        if candidate in index._path_index:
            return candidate
        for obj in index.objects:
            if obj["path"].endswith("/" + candidate):
                return obj["path"]
        if strict:
            raise MCPToolError(f"Object not found: {value}")
        return value

__all__ = ["MCPTool", "MCPToolError", "DistillMCPTools"]
