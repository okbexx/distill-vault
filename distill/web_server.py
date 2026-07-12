"""Lightweight Web UI server for distill-vault."""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .community import CommunityDetector
from .graph_index import GraphIndex
from .impact import ImpactAnalyzer
from .index import VaultIndex
from .pipeline import PipelineDAG
from .search_hybrid import VaultSearch


class DistillWebServer:
    """Small HTTP server exposing vault data and a static SPA."""

    def __init__(self, vault_root: Path, host: str = "127.0.0.1", port: int = 8420):
        self.vault = Path(vault_root).expanduser().resolve()
        self.host = host
        self.port = int(port)
        self.static_dir = Path(__file__).parent / "web_static"

    def make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_cors_headers()
                self.end_headers()

            def do_GET(self):
                try:
                    parsed = urlparse(self.path)
                    path = parsed.path
                    params = parse_qs(parsed.query)

                    if path == "/":
                        return self._serve_static_file(server.static_dir / "index.html", content_type="text/html; charset=utf-8")
                    if path.startswith("/static/"):
                        rel = path[len("/static/"):]
                        return self._serve_static_asset(rel)
                    if path == "/api/status":
                        return self._json_response(server.get_status())
                    if path == "/api/graph":
                        return self._json_response(server.get_graph())
                    if path == "/api/search":
                        query = params.get("q", [""])[0]
                        limit = _safe_int(params.get("limit", ["25"])[0], default=25)
                        return self._json_response(server.search(query=query, limit=limit))
                    if path == "/api/object":
                        obj_path = params.get("path", [""])[0]
                        return self._json_response(server.get_object(obj_path))
                    if path == "/api/communities":
                        return self._json_response(server.get_communities())
                    if path == "/api/impact":
                        obj_path = params.get("path", [""])[0]
                        direction = params.get("direction", ["upstream"])[0]
                        max_depth = _safe_int(params.get("max_depth", ["3"])[0], default=3)
                        return self._json_response(server.get_impact(obj_path, direction=direction, max_depth=max_depth))
                    if path == "/api/staleness":
                        return self._json_response(server.get_staleness())

                    return self._json_response({"error": f"Not found: {path}"}, status=HTTPStatus.NOT_FOUND)
                except Exception as exc:
                    return self._json_response({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

            def do_POST(self):
                try:
                    parsed = urlparse(self.path)
                    if parsed.path == "/api/pipeline":
                        payload = self._read_json_body()
                        incremental = bool(payload.get("incremental", False)) if isinstance(payload, dict) else False
                        return self._json_response(server.run_pipeline(incremental=incremental))
                    return self._json_response({"error": f"Not found: {parsed.path}"}, status=HTTPStatus.NOT_FOUND)
                except Exception as exc:
                    return self._json_response({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

            def log_message(self, fmt: str, *args):
                return

            def _serve_static_asset(self, rel_path: str):
                rel_path = unquote(rel_path).lstrip("/")
                candidate = (server.static_dir / rel_path).resolve()
                try:
                    candidate.relative_to(server.static_dir.resolve())
                except ValueError:
                    return self._json_response({"error": "Invalid static path"}, status=HTTPStatus.BAD_REQUEST)
                content_type = _guess_content_type(candidate)
                return self._serve_static_file(candidate, content_type=content_type)

            def _serve_static_file(self, path: Path, content_type: str):
                if not path.exists() or not path.is_file():
                    return self._json_response({"error": f"File not found: {path.name}"}, status=HTTPStatus.NOT_FOUND)
                data = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self._send_cors_headers()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _read_json_body(self) -> Dict[str, Any]:
                length = _safe_int(self.headers.get("Content-Length", "0"), default=0)
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                if not raw:
                    return {}
                try:
                    return json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    return {}

            def _json_response(self, payload: Dict[str, Any], status: int = HTTPStatus.OK):
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

        return Handler

    def serve_forever(self):
        httpd = ThreadingHTTPServer((self.host, self.port), self.make_handler())
        print(f"Distill Web UI running at http://{self.host}:{self.port}")
        httpd.serve_forever()

    def get_status(self) -> Dict[str, Any]:
        idx = VaultIndex(self.vault)
        idx.scan()
        graph_data = self.get_graph()
        return {
            "vault": str(self.vault),
            "stats": idx.stats,
            "graph": {
                "nodes": len(graph_data.get("nodes", [])),
                "edges": len(graph_data.get("edges", [])),
            },
            "staleness": self.get_staleness(),
        }

    def get_graph(self) -> Dict[str, Any]:
        graph = self._load_graph_index()
        node_rows = graph.all_objects()
        edge_rows = graph.all_edges()

        nodes = []
        for index, row in enumerate(node_rows):
            path = row["path"]
            title = row["title"]
            obj_type = row["type"]
            status = row["status"]
            word_count = row["word_count"]
            nodes.append(
                {
                    "id": str(path),
                    "label": str(title or Path(str(path)).stem),
                    "path": str(path),
                    "type": str(obj_type or "unknown"),
                    "status": str(status or "unknown"),
                    "word_count": int(word_count or 0),
                    "x": float((index % 12) * 10),
                    "y": float((index // 12) * 10),
                    "size": max(6, min(18, 6 + int(word_count or 0) // 120)),
                }
            )

        edges = []
        for idx, row in enumerate(edge_rows):
            source = row["source_path"]
            target = row["target_path"]
            link_type = row["relation"]
            edges.append(
                {
                    "id": f"e{idx}",
                    "source": str(source),
                    "target": str(target),
                    "type": str(link_type or "wikilink"),
                }
            )

        return {"nodes": nodes, "edges": edges}

    def search(self, query: str, limit: int = 25) -> Dict[str, Any]:
        if not query.strip():
            return {"query": query, "results": []}
        searcher = VaultSearch(self.vault)
        return {
            "query": query,
            "results": searcher.search(query, limit=limit, mode="hybrid"),
        }

    def get_object(self, obj_path: str) -> Dict[str, Any]:
        if not obj_path:
            return {"error": "Missing 'path' parameter"}

        idx = VaultIndex(self.vault)
        idx.scan()
        obj = next((item for item in idx.objects if item.get("path") == obj_path), None)
        if obj is None:
            return {"error": f"Object not found: {obj_path}", "path": obj_path}

        backlinks = sorted(idx.backlinks.get(obj_path, []))
        outlinks = sorted(idx.wikilinks.get(obj_path, []))
        file_path = self.vault / obj_path
        content = ""
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                content = file_path.read_text(encoding="utf-8", errors="ignore")

        return {
            "path": obj_path,
            "title": obj.get("title"),
            "type": obj.get("type"),
            "status": obj.get("status"),
            "frontmatter": obj.get("frontmatter", {}),
            "backlinks": backlinks,
            "outlinks": outlinks,
            "content": content,
        }

    def get_communities(self) -> Dict[str, Any]:
        graph = self._load_graph_index()
        detector = CommunityDetector(graph)
        return detector.detect(persist=False)

    def get_impact(self, obj_path: str, direction: str = "upstream", max_depth: int = 3) -> Dict[str, Any]:
        if not obj_path:
            return {"error": "Missing 'path' parameter"}
        graph = self._load_graph_index()
        analyzer = ImpactAnalyzer(graph)
        if direction == "downstream":
            return analyzer.downstream(obj_path, max_depth=max_depth)
        return analyzer.upstream(obj_path, max_depth=max_depth)

    def get_staleness(self) -> Dict[str, Any]:
        dag = PipelineDAG(self.vault)
        return dag.check_staleness()

    def run_pipeline(self, incremental: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "started",
            "incremental": incremental,
        }

        def _runner():
            try:
                cmd = ["python3", "-m", "distill.cli", "--vault", str(self.vault), "run"]
                if incremental:
                    cmd.append("--incremental")
                completed = subprocess.run(
                    cmd,
                    cwd=str(self.vault),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                result.update(
                    {
                        "status": "completed" if completed.returncode == 0 else "failed",
                        "returncode": completed.returncode,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    }
                )
            except Exception as exc:
                result.update({"status": "failed", "error": str(exc)})

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return result

    def _load_graph_index(self) -> GraphIndex:
        graph = GraphIndex(self.vault)
        if not graph.has_data():
            graph.build()
        return graph


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "application/octet-stream"


def main(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description="Run the distill-vault Web UI server")
    parser.add_argument("--vault", default=".", help="Vault root path")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8420, help="Bind port")
    args = parser.parse_args(argv)

    server = DistillWebServer(Path(args.vault), host=args.host, port=args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
