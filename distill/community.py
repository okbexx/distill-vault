"""Knowledge community detection backed by the SQLite graph projection.

Implements a small Louvain-like modularity optimization in pure Python without
external graph/community packages. Communities can be persisted back into the
same graph database as Community nodes plus MEMBER_OF relationships.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Tuple

try:
    import frontmatter
except Exception:  # pragma: no cover - optional at import time
    frontmatter = None

from .config import load_config


TOKEN_RE = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]+")
DEFAULT_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
    "have", "has", "had", "not", "you", "your", "our", "their", "agent", "note",
    "notes", "vault", "distill", "knowledge", "output", "unknown", "status", "type",
    "项目", "知识", "来源", "输出", "相关", "一个", "一些", "以及", "我们", "你们",
    "他们", "进行", "用于", "基于", "关于", "节点", "社区", "内容", "文档", "文件",
}


@dataclass
class _NodeRecord:
    path: str
    title: str
    obj_type: str
    status: str
    word_count: int


class CommunityDetector:
    """Detect graph communities from a :class:`distill.graph_index.GraphIndex`."""

    def __init__(self, graph_index, max_iter: int = 20, min_gain: float = 1e-6, config=None):
        self.graph = graph_index
        self.max_iter = max_iter
        self.min_gain = min_gain
        self.vault = Path(getattr(graph_index, "vault", "."))
        self.config = config or load_config(self.vault)
        configured = self.config.get("search", {}).get("chinese_stopwords", [])
        self.stopwords = set(DEFAULT_STOPWORDS) | set(configured)
        self._node_cache: Optional[Dict[str, _NodeRecord]] = None

    def detect(self, persist: bool = True) -> dict:
        nodes = self._load_nodes()
        adjacency = self._load_adjacency(nodes)
        communities, modularity = self._run_louvain_like(adjacency)
        result = self._build_result(communities, adjacency, modularity, nodes)
        if persist:
            self._persist_communities(result)
        return result

    def _load_nodes(self) -> Dict[str, _NodeRecord]:
        if self._node_cache is not None:
            return self._node_cache

        rows = self.graph.all_objects()
        nodes: Dict[str, _NodeRecord] = {}
        for row in rows:
            path = row["path"]
            title = row["title"]
            obj_type = row["type"]
            status = row["status"]
            word_count = row["word_count"]
            nodes[path] = _NodeRecord(
                path=str(path),
                title=str(title or ""),
                obj_type=str(obj_type or "unknown"),
                status=str(status or "unknown"),
                word_count=int(word_count or 0),
            )
        self._node_cache = nodes
        return nodes

    def _load_adjacency(self, nodes: Dict[str, _NodeRecord]) -> Dict[str, Dict[str, float]]:
        adjacency: DefaultDict[str, Dict[str, float]] = defaultdict(dict)
        for path in nodes:
            adjacency[path] = {}

        rows = self.graph.all_edges()
        for row in rows:
            src = str(row["source_path"])
            dst = str(row["target_path"])
            if src not in nodes or dst not in nodes or src == dst:
                continue
            adjacency[src][dst] = adjacency[src].get(dst, 0.0) + 1.0
            adjacency[dst][src] = adjacency[dst].get(src, 0.0) + 1.0
        return dict(adjacency)

    def _run_louvain_like(
        self, adjacency: Dict[str, Dict[str, float]]
    ) -> Tuple[Dict[str, int], float]:
        nodes = list(adjacency.keys())
        if not nodes:
            return {}, 0.0

        m2 = sum(sum(neighbors.values()) for neighbors in adjacency.values())
        if m2 == 0:
            communities = {node: idx for idx, node in enumerate(nodes)}
            return communities, 0.0

        communities = {node: idx for idx, node in enumerate(nodes)}
        current_modularity = self._modularity(adjacency, communities)

        for _ in range(self.max_iter):
            moved = False
            improved = False
            for node in sorted(nodes):
                current_comm = communities[node]
                candidate_comms = {communities[neighbor] for neighbor in adjacency[node]}
                candidate_comms.add(current_comm)
                best_comm = current_comm
                best_modularity = current_modularity

                for comm in candidate_comms:
                    if comm == current_comm:
                        continue
                    trial = dict(communities)
                    trial[node] = comm
                    modularity = self._modularity(adjacency, trial)
                    if modularity > best_modularity + self.min_gain:
                        best_modularity = modularity
                        best_comm = comm

                if best_comm != current_comm:
                    communities[node] = best_comm
                    current_modularity = best_modularity
                    moved = True
                    improved = True

            communities = self._renumber_communities(communities)
            new_modularity = self._modularity(adjacency, communities)
            if not moved or new_modularity - current_modularity <= self.min_gain:
                current_modularity = new_modularity
                if not improved:
                    break
            else:
                current_modularity = new_modularity

        return communities, current_modularity

    def _modularity(self, adjacency: Dict[str, Dict[str, float]], communities: Dict[str, int]) -> float:
        m2 = sum(sum(neighbors.values()) for neighbors in adjacency.values())
        if m2 == 0:
            return 0.0

        degrees = {node: sum(neighbors.values()) for node, neighbors in adjacency.items()}
        community_nodes: DefaultDict[int, List[str]] = defaultdict(list)
        for node, comm in communities.items():
            community_nodes[comm].append(node)

        modularity = 0.0
        for members in community_nodes.values():
            internal_weight_twice = 0.0
            degree_sum = 0.0
            member_set = set(members)
            for node in members:
                degree_sum += degrees[node]
                for neighbor, weight in adjacency[node].items():
                    if neighbor in member_set:
                        internal_weight_twice += weight
            modularity += (internal_weight_twice / m2) - (degree_sum / m2) ** 2
        return modularity

    def _renumber_communities(self, communities: Dict[str, int]) -> Dict[str, int]:
        mapping: Dict[int, int] = {}
        next_id = 0
        normalized: Dict[str, int] = {}
        for node, comm in sorted(communities.items()):
            if comm not in mapping:
                mapping[comm] = next_id
                next_id += 1
            normalized[node] = mapping[comm]
        return normalized

    def _build_result(
        self,
        communities: Dict[str, int],
        adjacency: Dict[str, Dict[str, float]],
        modularity: float,
        nodes: Dict[str, _NodeRecord],
    ) -> dict:
        grouped: DefaultDict[int, List[str]] = defaultdict(list)
        for node, comm in communities.items():
            grouped[comm].append(node)

        community_items = []
        for comm_id, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            members = sorted(members)
            keywords = self._extract_keywords(members, nodes)
            label = self._build_label(keywords, members, nodes)
            density = self._community_density(members, adjacency)
            community_items.append(
                {
                    "id": f"comm_{comm_id}",
                    "label": label,
                    "size": len(members),
                    "density": round(density, 4),
                    "members": members,
                    "keywords": keywords,
                }
            )

        return {
            "communities": community_items,
            "modularity": round(modularity, 4),
            "total_communities": len(community_items),
        }

    def _community_density(self, members: List[str], adjacency: Dict[str, Dict[str, float]]) -> float:
        size = len(members)
        if size <= 1:
            return 0.0
        member_set = set(members)
        edge_count = 0
        for node in members:
            for neighbor in adjacency.get(node, {}):
                if neighbor in member_set and node < neighbor:
                    edge_count += 1
        possible = size * (size - 1) / 2
        return edge_count / possible if possible else 0.0

    def _extract_keywords(self, members: List[str], nodes: Dict[str, _NodeRecord], top_n: int = 3) -> List[str]:
        counter: Counter = Counter()
        for path in members:
            record = nodes[path]
            text_chunks = [record.title, record.obj_type, record.status, Path(path).stem]
            file_text = self._read_member_text(path)
            if file_text:
                text_chunks.append(file_text[:4000])
            for token in self._tokenize(" ".join(text_chunks)):
                counter[token] += 1
        keywords = [token for token, _ in counter.most_common(top_n) if token]
        if len(keywords) < top_n:
            for path in members:
                stem = Path(path).stem
                if stem not in keywords:
                    keywords.append(stem)
                if len(keywords) >= top_n:
                    break
        return keywords[:top_n]

    def _build_label(self, keywords: List[str], members: List[str], nodes: Dict[str, _NodeRecord]) -> str:
        if keywords:
            if len(keywords) >= 2:
                return "".join(keywords[:2])
            return keywords[0]
        if members:
            first = members[0]
            title = nodes[first].title.strip()
            return title or Path(first).stem
        return "未命名社区"

    def _read_member_text(self, rel_path: str) -> str:
        path = self.vault / rel_path
        if not path.exists():
            return ""
        try:
            if frontmatter is not None:
                post = frontmatter.load(str(path))
                return post.content if hasattr(post, "content") else str(post)
        except Exception:
            pass
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _tokenize(self, text: str) -> Iterable[str]:
        for raw in TOKEN_RE.findall((text or "").lower()):
            token = raw.strip("_-")
            if len(token) <= 1:
                continue
            if token.isdigit():
                continue
            if token in self.stopwords:
                continue
            yield token

    def _persist_communities(self, result: dict) -> None:
        self.graph.persist_communities(result.get("communities", []))
