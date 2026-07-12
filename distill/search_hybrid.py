"""Hybrid vault search with BM25-style keyword search and TF-IDF semantic ranking."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .index import VaultIndex

try:
    import numpy as _np  # type: ignore
except ImportError:  # pragma: no cover - runtime fallback is intentional
    _np = None


_WORD_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")


def _is_cjk_char(char: str) -> bool:
    return bool(_CJK_RE.fullmatch(char))


def tokenize_text(text: str) -> List[str]:
    """Tokenize mixed Chinese/whitespace text using simple rules.

    Strategy:
    - English / numbers: split by word boundaries, lower-cased.
    - Chinese: keep each character as an individual token.
    - Also keep whitespace-delimited chunks to preserve phrase-like matches.
    """
    if not text:
        return []

    tokens: List[str] = []
    lowered = text.lower()

    for chunk in _WHITESPACE_RE.split(lowered):
        chunk = chunk.strip()
        if not chunk:
            continue
        tokens.append(chunk)
        tokens.extend(_WORD_RE.findall(chunk))
        for char in chunk:
            if _is_cjk_char(char):
                tokens.append(char)

    return tokens


class BM25Search:
    """Pure Python BM25-style search over vault markdown files."""

    def __init__(self, vault_root: Path, index: Optional[VaultIndex] = None, k1: float = 1.5, b: float = 0.75):
        self.vault_root = Path(vault_root)
        self.index = index or VaultIndex(self.vault_root)
        if not self.index.objects:
            self.index.scan()
        self.k1 = k1
        self.b = b
        self.documents: List[Dict[str, object]] = []
        self.doc_term_freqs: List[Counter[str]] = []
        self.doc_lengths: List[int] = []
        self.doc_freqs: Dict[str, int] = defaultdict(int)
        self.idf: Dict[str, float] = {}
        self.avg_doc_length: float = 0.0
        self._build_index()

    def _build_index(self) -> None:
        total_length = 0
        for obj in self.index.objects:
            path_value = obj.get("path")
            if not path_value or not str(path_value).endswith(".md"):
                continue

            rel_path = Path(str(path_value))
            abs_path = self.vault_root / rel_path
            if not abs_path.exists():
                continue

            content = self._read_markdown(abs_path)
            title = str(obj.get("title") or rel_path.stem)
            combined = f"{title}\n{content}".strip()
            tokens = tokenize_text(combined)
            term_freq = Counter(tokens)

            self.documents.append(
                {
                    "path": str(rel_path),
                    "title": title,
                    "type": obj.get("type", "unknown"),
                    "status": obj.get("status", "unknown"),
                    "frontmatter": obj.get("frontmatter", {}),
                    "content": content,
                    "text": combined,
                }
            )
            self.doc_term_freqs.append(term_freq)
            doc_length = sum(term_freq.values())
            self.doc_lengths.append(doc_length)
            total_length += doc_length

            for token in term_freq:
                self.doc_freqs[token] += 1

        doc_count = len(self.documents)
        self.avg_doc_length = (total_length / doc_count) if doc_count else 0.0
        for token, freq in self.doc_freqs.items():
            self.idf[token] = math.log(1.0 + (doc_count - freq + 0.5) / (freq + 0.5)) if doc_count else 0.0

    def _read_markdown(self, path: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        return self._strip_frontmatter(raw)

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                return parts[2].strip()
        return text

    def _bm25_score(self, query_tokens: Iterable[str], doc_index: int) -> float:
        score = 0.0
        tf = self.doc_term_freqs[doc_index]
        doc_length = self.doc_lengths[doc_index] or 1

        for token in query_tokens:
            freq = tf.get(token, 0)
            if freq <= 0:
                continue
            idf = self.idf.get(token, 0.0)
            numerator = freq * (self.k1 + 1.0)
            denominator = freq + self.k1 * (1.0 - self.b + self.b * (doc_length / (self.avg_doc_length or 1.0)))
            score += idf * (numerator / denominator)

        return score

    @staticmethod
    def _make_excerpt(content: str, query: str, max_chars: int = 220) -> str:
        text = _HEADING_RE.sub("", content).replace("\n", " ").strip()
        if not text:
            return ""
        pos = text.lower().find(query.lower())
        if pos < 0:
            return text[:max_chars]
        start = max(0, pos - max_chars // 3)
        end = min(len(text), start + max_chars)
        excerpt = text[start:end]
        return f"...{excerpt}..." if start > 0 or end < len(text) else excerpt

    def search(self, query: str, limit: int = 10, obj_type: Optional[str] = None) -> List[Dict[str, object]]:
        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []

        scored: List[Dict[str, object]] = []
        for i, doc in enumerate(self.documents):
            if obj_type and doc.get("type") != obj_type:
                continue
            score = self._bm25_score(query_tokens, i)
            text_value = str(doc.get("text", "")).lower()
            title_value = str(doc.get("title", "")).lower()
            query_lower = query.lower()
            if query_lower and query_lower in title_value:
                score += 3.0
            if query_lower and query_lower in text_value:
                score += 1.0
            if score <= 0:
                continue
            scored.append(
                {
                    "path": doc["path"],
                    "title": doc["title"],
                    "type": doc.get("type", "unknown"),
                    "status": doc.get("status", "unknown"),
                    "score": score,
                    "excerpt": self._make_excerpt(str(doc.get("content", "")), query),
                    "source": "keyword",
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]


class HybridSearch:
    """Hybrid search combining BM25 and TF-IDF cosine similarity with RRF."""

    def __init__(self, vault_root: Path, index: Optional[VaultIndex] = None, rrf_k: int = 60):
        self.vault_root = Path(vault_root)
        self.index = index or VaultIndex(self.vault_root)
        if not self.index.objects:
            self.index.scan()
        self.rrf_k = rrf_k
        self.bm25 = BM25Search(self.vault_root, index=self.index)
        self.numpy_available = _np is not None
        self._vectorizer_ready = False
        self.vocabulary: Dict[str, int] = {}
        self.semantic_doc_vectors = None
        self.semantic_doc_norms: List[float] = []
        if self.numpy_available:
            self._build_semantic_index_numpy()
        else:
            self._build_semantic_index_python()

    def _build_semantic_index_numpy(self) -> None:
        doc_count = len(self.bm25.documents)
        if not doc_count:
            self.semantic_doc_vectors = _np.zeros((0, 0))
            self.semantic_doc_norms = []
            self._vectorizer_ready = True
            return

        tokens_by_doc = [list(tf.keys()) for tf in self.bm25.doc_term_freqs]
        vocab_terms = sorted({token for tokens in tokens_by_doc for token in tokens})
        self.vocabulary = {token: idx for idx, token in enumerate(vocab_terms)}
        term_count = len(self.vocabulary)
        matrix = _np.zeros((doc_count, term_count), dtype=float)

        for doc_idx, tf in enumerate(self.bm25.doc_term_freqs):
            for token, freq in tf.items():
                token_idx = self.vocabulary[token]
                matrix[doc_idx, token_idx] = float(freq) * self.bm25.idf.get(token, 0.0)

        norms = _np.linalg.norm(matrix, axis=1)
        self.semantic_doc_vectors = matrix
        self.semantic_doc_norms = norms.tolist()
        self._vectorizer_ready = True

    def _build_semantic_index_python(self) -> None:
        self.vocabulary = {token: idx for idx, token in enumerate(sorted(self.bm25.idf.keys()))}
        self._vectorizer_ready = True

    def _semantic_search_numpy(self, query: str, limit: int = 10, obj_type: Optional[str] = None) -> List[Dict[str, object]]:
        query_tokens = tokenize_text(query)
        if not query_tokens or self.semantic_doc_vectors is None or not self.vocabulary:
            return []

        query_tf = Counter(query_tokens)
        query_vector = _np.zeros(len(self.vocabulary), dtype=float)
        for token, freq in query_tf.items():
            token_idx = self.vocabulary.get(token)
            if token_idx is None:
                continue
            query_vector[token_idx] = float(freq) * self.bm25.idf.get(token, 0.0)

        query_norm = float(_np.linalg.norm(query_vector))
        if query_norm == 0.0:
            return []

        scores = self.semantic_doc_vectors.dot(query_vector)
        scored_results: List[Dict[str, object]] = []
        for idx, dot_value in enumerate(scores.tolist()):
            doc = self.bm25.documents[idx]
            if obj_type and doc.get("type") != obj_type:
                continue
            doc_norm = self.semantic_doc_norms[idx] or 0.0
            if doc_norm == 0.0:
                continue
            cosine = float(dot_value) / (doc_norm * query_norm)
            if cosine <= 0:
                continue
            scored_results.append(
                {
                    "path": doc["path"],
                    "title": doc["title"],
                    "type": doc.get("type", "unknown"),
                    "status": doc.get("status", "unknown"),
                    "score": cosine,
                    "excerpt": self.bm25._make_excerpt(str(doc.get("content", "")), query),
                    "source": "semantic",
                }
            )

        scored_results.sort(key=lambda item: item["score"], reverse=True)
        return scored_results[:limit]

    def _semantic_search_python(self, query: str, limit: int = 10, obj_type: Optional[str] = None) -> List[Dict[str, object]]:
        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []
        query_tf = Counter(query_tokens)
        query_weights = {
            token: float(freq) * self.bm25.idf.get(token, 0.0)
            for token, freq in query_tf.items()
            if token in self.bm25.idf
        }
        query_norm = math.sqrt(sum(weight * weight for weight in query_weights.values()))
        if query_norm == 0.0:
            return []

        results: List[Dict[str, object]] = []
        for idx, tf in enumerate(self.bm25.doc_term_freqs):
            doc = self.bm25.documents[idx]
            if obj_type and doc.get("type") != obj_type:
                continue
            dot_value = 0.0
            doc_norm_sq = 0.0
            for token, freq in tf.items():
                weight = float(freq) * self.bm25.idf.get(token, 0.0)
                doc_norm_sq += weight * weight
                if token in query_weights:
                    dot_value += weight * query_weights[token]
            doc_norm = math.sqrt(doc_norm_sq)
            if dot_value <= 0.0 or doc_norm == 0.0:
                continue
            cosine = dot_value / (doc_norm * query_norm)
            results.append(
                {
                    "path": doc["path"],
                    "title": doc["title"],
                    "type": doc.get("type", "unknown"),
                    "status": doc.get("status", "unknown"),
                    "score": cosine,
                    "excerpt": self.bm25._make_excerpt(str(doc.get("content", "")), query),
                    "source": "semantic",
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    def semantic_search(self, query: str, limit: int = 10, obj_type: Optional[str] = None) -> List[Dict[str, object]]:
        if not self._vectorizer_ready:
            return []
        if self.numpy_available:
            return self._semantic_search_numpy(query, limit=limit, obj_type=obj_type)
        return self._semantic_search_python(query, limit=limit, obj_type=obj_type)

    def hybrid_search(self, query: str, limit: int = 10, obj_type: Optional[str] = None) -> List[Dict[str, object]]:
        keyword_results = self.bm25.search(query, limit=max(limit * 3, 20), obj_type=obj_type)
        semantic_results = self.semantic_search(query, limit=max(limit * 3, 20), obj_type=obj_type)
        if not semantic_results:
            return keyword_results[:limit]

        combined: Dict[str, Dict[str, object]] = {}
        rank_sources = [("keyword", keyword_results), ("semantic", semantic_results)]
        for source_name, results in rank_sources:
            for rank, item in enumerate(results, start=1):
                path = str(item["path"])
                entry = combined.setdefault(
                    path,
                    {
                        "path": item["path"],
                        "title": item["title"],
                        "type": item.get("type", "unknown"),
                        "status": item.get("status", "unknown"),
                        "excerpt": item.get("excerpt", ""),
                        "score": 0.0,
                        "sources": [],
                    },
                )
                entry["score"] = float(entry["score"]) + 1.0 / (self.rrf_k + rank)
                if source_name not in entry["sources"]:
                    entry["sources"].append(source_name)
                if not entry.get("excerpt") and item.get("excerpt"):
                    entry["excerpt"] = item["excerpt"]

        fused = sorted(combined.values(), key=lambda item: float(item["score"]), reverse=True)
        for item in fused:
            item["source"] = "+".join(item.get("sources", [])) or "hybrid"
        return fused[:limit]

    def search(self, query: str, limit: int = 10, obj_type: Optional[str] = None, mode: str = "hybrid") -> List[Dict[str, object]]:
        mode = (mode or "hybrid").lower()
        if mode == "keyword":
            return self.bm25.search(query, limit=limit, obj_type=obj_type)
        if mode == "semantic":
            results = self.semantic_search(query, limit=limit, obj_type=obj_type)
            if results:
                return results
            return self.bm25.search(query, limit=limit, obj_type=obj_type)
        return self.hybrid_search(query, limit=limit, obj_type=obj_type)


class VaultSearch(HybridSearch):
    """Backwards-compatible alias for CLI integration."""

    pass
