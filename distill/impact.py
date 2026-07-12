"""Graph-based change impact analysis for distill vault objects."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Deque, Dict, List, Optional, Sequence, Set, Tuple

from .graph_index import GraphIndex


class ImpactAnalyzer:
    """Analyze upstream/downstream dependency impact over GraphIndex links."""

    def __init__(self, graph: GraphIndex):
        self.graph = graph

    def upstream(
        self,
        target: str,
        max_depth: int = 3,
        edge_types: Optional[Sequence[str]] = None,
    ) -> Dict[str, object]:
        """Find all objects that depend on the target object."""
        return self._traverse(
            target=target,
            direction="upstream",
            max_depth=max_depth,
            edge_types=edge_types,
        )

    def downstream(
        self,
        target: str,
        max_depth: int = 3,
        edge_types: Optional[Sequence[str]] = None,
    ) -> Dict[str, object]:
        """Find all objects that the target object depends on."""
        return self._traverse(
            target=target,
            direction="downstream",
            max_depth=max_depth,
            edge_types=edge_types,
        )

    def detect_changes(
        self,
        changed_paths: Sequence[str],
        max_depth: int = 3,
        edge_types: Optional[Sequence[str]] = None,
        direction: str = "upstream",
    ) -> Dict[str, object]:
        """Analyze impact for a batch of changed files and merge affected objects."""
        normalized_changes = [path for path in changed_paths if path]
        impacts: Dict[str, Dict[str, object]] = {}
        merged: Dict[str, Dict[str, object]] = {}
        merged_types: Counter[str] = Counter()
        max_depth_reached = 0

        for path in normalized_changes:
            impact = self._traverse(
                target=path,
                direction=direction,
                max_depth=max_depth,
                edge_types=edge_types,
            )
            impacts[path] = impact
            max_depth_reached = max(max_depth_reached, int(impact["max_depth_reached"]))

            for depth_key, nodes in impact["by_depth"].items():
                for node in nodes:
                    existing = merged.get(node["path"])
                    if existing is None:
                        merged[node["path"]] = {
                            "path": node["path"],
                            "title": node["title"],
                            "type": node["type"],
                            "edges": list(node["edges"]),
                            "depths": [depth_key],
                            "sources": [path],
                        }
                        merged_types[node["type"]] += 1
                    else:
                        existing["edges"] = sorted(set(existing["edges"]) | set(node["edges"]))
                        if depth_key not in existing["depths"]:
                            existing["depths"].append(depth_key)
                        if path not in existing["sources"]:
                            existing["sources"].append(path)

        merged_affected = sorted(merged.values(), key=lambda item: item["path"])
        return {
            "changed_paths": normalized_changes,
            "direction": direction,
            "edge_types": list(edge_types) if edge_types else None,
            "impacts": impacts,
            "merged_affected": merged_affected,
            "affected_types": dict(merged_types),
            "total_affected": len(merged_affected),
            "risk": self._risk_for_count(len(merged_affected)),
            "max_depth_reached": max_depth_reached,
        }

    def _traverse(
        self,
        target: str,
        direction: str,
        max_depth: int,
        edge_types: Optional[Sequence[str]],
    ) -> Dict[str, object]:
        if direction not in {"upstream", "downstream"}:
            raise ValueError("direction must be 'upstream' or 'downstream'")
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")

        edge_filter = self._normalize_edge_types(edge_types)
        visited: Set[str] = {target}
        queue: Deque[Tuple[str, int]] = deque([(target, 0)])
        by_depth: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        aggregated: Dict[str, Dict[str, object]] = {}
        max_depth_reached = 0

        while queue:
            current_path, depth = queue.popleft()
            if depth >= max_depth:
                continue

            neighbors = self._fetch_neighbors(
                current_path=current_path,
                direction=direction,
                edge_types=edge_filter,
            )
            next_depth = depth + 1

            for neighbor in neighbors:
                neighbor_path = neighbor["path"]
                if neighbor_path in visited:
                    existing = aggregated.get(neighbor_path)
                    if existing is not None:
                        existing["edges"] = sorted(set(existing["edges"]) | set(neighbor["edges"]))
                    continue

                visited.add(neighbor_path)
                node = {
                    "path": neighbor_path,
                    "title": neighbor["title"],
                    "type": neighbor["type"],
                    "edges": list(neighbor["edges"]),
                }
                aggregated[neighbor_path] = node
                by_depth[f"d={next_depth}"].append(node)
                max_depth_reached = max(max_depth_reached, next_depth)
                queue.append((neighbor_path, next_depth))

        affected_types = Counter(node["type"] for node in aggregated.values())
        return {
            "target": target,
            "direction": direction,
            "risk": self._risk_for_count(len(aggregated)),
            "by_depth": {key: value for key, value in sorted(by_depth.items())},
            "affected_types": dict(affected_types),
            "total_affected": len(aggregated),
            "max_depth_reached": max_depth_reached,
        }

    def _fetch_neighbors(
        self,
        current_path: str,
        direction: str,
        edge_types: Optional[Sequence[str]],
    ) -> List[Dict[str, object]]:
        rows = self.graph.incoming(current_path) if direction == "upstream" else self.graph.outgoing(current_path)
        allowed_edges = set(edge_types or [])
        grouped: Dict[str, Dict[str, object]] = {}
        for row in rows:
            path = row["path"]
            title = row["title"]
            obj_type = row["type"]
            link_type = row["relation"]
            if allowed_edges and link_type not in allowed_edges:
                continue
            entry = grouped.setdefault(
                path,
                {
                    "path": path,
                    "title": title,
                    "type": obj_type,
                    "edges": set(),
                },
            )
            if link_type:
                entry["edges"].add(link_type)

        results = []
        for entry in grouped.values():
            results.append(
                {
                    "path": entry["path"],
                    "title": entry["title"],
                    "type": entry["type"],
                    "edges": sorted(entry["edges"]),
                }
            )
        return sorted(results, key=lambda item: item["path"])

    def _normalize_edge_types(self, edge_types: Optional[Sequence[str]]) -> Optional[List[str]]:
        if edge_types is None:
            return None
        normalized = [edge_type for edge_type in edge_types if edge_type]
        return normalized or None

    def _risk_for_count(self, count: int) -> str:
        if count >= 20:
            return "CRITICAL"
        if count >= 10:
            return "HIGH"
        if count >= 4:
            return "MEDIUM"
        return "LOW"
