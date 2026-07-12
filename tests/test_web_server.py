"""Tests for distill.web_server — HTTP protocol, API endpoints, static serving, security.

Uses http.server's ThreadingHTTPServer in a background thread with a real vault
(inited via distill.init_cmd) so that API handlers exercise real pipeline/graph/search code.
"""

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from distill.init_cmd import init_vault
from distill.web_server import DistillWebServer, _guess_content_type, _safe_int


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def live_vault(tmp_path):
    """Create a minimal vault with distill run executed."""
    vault = tmp_path / "vault"
    init_vault(str(vault), lang="en", with_examples=False)
    # Write a knowledge file so the vault has content
    knowledge_dir = vault / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "test-note.md").write_text(
        "---\ntype: concept\ntitle: Test Note\n---\nThis is a test note.\n",
        encoding="utf-8",
    )
    # Run the pipeline so graph data exists
    from distill.pipeline import PipelineDAG
    dag = PipelineDAG(vault)
    dag.run()
    return vault


@pytest.fixture()
def live_server(live_vault):
    """Start a real HTTP server on a free port, yield (server, port), then shut down."""
    server = DistillWebServer(live_vault, host="127.0.0.1", port=0)
    # Use port=0 to let OS pick a free port
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    server.port = port
    from http.server import ThreadingHTTPServer

    httpd = ThreadingHTTPServer(("127.0.0.1", port), server.make_handler())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)  # let server start

    yield server, port

    httpd.shutdown()


@pytest.fixture()
def conn(live_server):
    """Return an HTTPConnection to the live server."""
    _, port = live_server
    c = HTTPConnection("127.0.0.1", port, timeout=5)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# _safe_int, _guess_content_type (pure unit tests)
# ---------------------------------------------------------------------------


class TestSafeInt:
    def test_valid_integer(self):
        assert _safe_int("42", default=0) == 42

    def test_invalid_string(self):
        assert _safe_int("abc", default=7) == 7

    def test_none_value(self):
        assert _safe_int(None, default=3) == 3

    def test_float_string(self):
        assert _safe_int("3.14", default=0) == 0

    def test_negative(self):
        assert _safe_int("-5", default=0) == -5


class TestGuessContentType:
    def test_html(self):
        assert "text/html" in _guess_content_type(Path("a.html"))

    def test_js(self):
        assert "javascript" in _guess_content_type(Path("a.js"))

    def test_css(self):
        assert "text/css" in _guess_content_type(Path("a.css"))

    def test_json(self):
        assert "application/json" in _guess_content_type(Path("a.json"))

    def test_unknown(self):
        assert _guess_content_type(Path("a.bin")) == "application/octet-stream"

    def test_svg(self):
        assert _guess_content_type(Path("a.svg")) == "application/octet-stream"


# ---------------------------------------------------------------------------
# HTTP protocol layer (GET root, OPTIONS, 404)
# ---------------------------------------------------------------------------


class TestHTTPProtocol:
    def test_get_root_returns_html(self, conn):
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "<!DOCTYPE html>" in body or "<html" in body

    def test_options_returns_204(self, conn):
        conn.request("OPTIONS", "/api/status")
        resp = conn.getresponse()
        assert resp.status == 204

    def test_cors_headers_on_get(self, conn):
        conn.request("GET", "/api/status")
        resp = conn.getresponse()
        assert resp.getheader("Access-Control-Allow-Origin") == "*"

    def test_cors_headers_on_options(self, conn):
        conn.request("OPTIONS", "/anything")
        resp = conn.getresponse()
        assert resp.getheader("Access-Control-Allow-Methods") is not None

    def test_404_for_unknown_api(self, conn):
        conn.request("GET", "/api/nonexistent")
        resp = conn.getresponse()
        assert resp.status == 404
        body = json.loads(resp.read().decode("utf-8"))
        assert "error" in body

    def test_404_for_unknown_post(self, conn):
        conn.request("POST", "/api/nonexistent")
        resp = conn.getresponse()
        assert resp.status == 404

    def test_content_type_json_on_api(self, conn):
        conn.request("GET", "/api/status")
        resp = conn.getresponse()
        ct = resp.getheader("Content-Type")
        assert "application/json" in ct


# ---------------------------------------------------------------------------
# API endpoints — functional tests with live server + vault
# ---------------------------------------------------------------------------


class TestAPIStatus:
    def test_status_returns_vault_info(self, conn):
        conn.request("GET", "/api/status")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "vault" in data
        assert "stats" in data
        assert "graph" in data


class TestAPIGraph:
    def test_graph_returns_nodes_and_edges(self, conn):
        conn.request("GET", "/api/graph")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_graph_node_has_required_fields(self, conn):
        conn.request("GET", "/api/graph")
        data = json.loads(conn.getresponse().read().decode("utf-8"))
        if data["nodes"]:
            node = data["nodes"][0]
            for key in ("id", "label", "path", "type", "status", "size", "x", "y"):
                assert key in node, f"Missing key: {key}"


class TestAPISearch:
    def test_search_empty_query_returns_empty(self, conn):
        conn.request("GET", "/api/search?q=")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["results"] == []

    def test_search_with_query(self, conn):

        conn.request("GET", "/api/search?q=test&limit=5")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "query" in data
        assert "results" in data

    def test_search_limit_parameter(self, conn):
        conn.request("GET", "/api/search?q=test&limit=3")
        resp = conn.getresponse()
        assert resp.status == 200

    def test_search_invalid_limit_uses_default(self, conn):
        conn.request("GET", "/api/search?q=test&limit=invalid")
        resp = conn.getresponse()
        assert resp.status == 200


class TestAPIObject:
    def test_object_missing_path(self, conn):
        conn.request("GET", "/api/object")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "error" in data

    def test_object_not_found(self, conn):
        conn.request("GET", "/api/object?path=nonexistent.md")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "error" in data or "path" in data

    def test_object_found(self, conn):

        conn.request("GET", "/api/object?path=knowledge/test-note.md")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("title") == "Test Note"
        assert "content" in data
        assert "backlinks" in data
        assert "outlinks" in data


class TestAPICommunities:
    def test_communities_returns_data(self, conn):
        conn.request("GET", "/api/communities")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, dict) or isinstance(data, list)


class TestAPIImpact:
    def test_impact_missing_path(self, conn):
        conn.request("GET", "/api/impact")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "error" in data

    def test_impact_with_path(self, conn):
        conn.request("GET", "/api/impact?path=knowledge/test-note.md&direction=upstream")
        resp = conn.getresponse()
        assert resp.status == 200

    def test_impact_downstream(self, conn):
        conn.request("GET", "/api/impact?path=knowledge/test-note.md&direction=downstream&max_depth=2")
        resp = conn.getresponse()
        assert resp.status == 200


class TestAPIStaleness:
    def test_staleness_returns_data(self, conn):
        conn.request("GET", "/api/staleness")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# POST /api/pipeline
# ---------------------------------------------------------------------------


class TestAPIPipeline:
    def test_post_pipeline_starts(self, conn):
        body = json.dumps({"incremental": False}).encode("utf-8")
        conn.request("POST", "/api/pipeline", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("status") in ("started", "completed", "failed")

    def test_post_pipeline_empty_body(self, conn):
        conn.request("POST", "/api/pipeline", body="", headers={"Content-Length": "0"})
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "status" in data

    def test_post_pipeline_invalid_json(self, conn):
        conn.request("POST", "/api/pipeline", body="not json", headers={"Content-Type": "application/json", "Content-Length": "8"})
        resp = conn.getresponse()
        assert resp.status == 200

    def test_post_pipeline_incremental(self, conn):
        body = json.dumps({"incremental": True}).encode("utf-8")
        conn.request("POST", "/api/pipeline", body=body, headers={"Content-Type": "application/json", "Content-Length": str(len(body))})
        resp = conn.getresponse()
        assert resp.status == 200


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------


class TestStaticServing:
    def test_serve_index_html(self, conn):
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert len(body) > 100

    def test_serve_graph_js(self, conn):
        conn.request("GET", "/static/graph.js")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "sigma" in body.lower() or "graph" in body.lower()

    def test_static_404_for_missing_file(self, conn):
        conn.request("GET", "/static/nonexistent.js")
        resp = conn.getresponse()
        assert resp.status == 404

    def test_static_path_traversal_blocked(self, conn):
        """Static file serving should block path traversal attempts."""
        conn.request("GET", "/static/../../../etc/passwd")
        resp = conn.getresponse()
        # Should either be 400 (invalid path) or 404 (not found), not 200 with file content
        assert resp.status in (400, 404)

    def test_static_content_type_js(self, conn):
        conn.request("GET", "/static/graph.js")
        resp = conn.getresponse()
        ct = resp.getheader("Content-Type")
        assert "javascript" in ct

    def test_static_content_type_html(self, conn):
        conn.request("GET", "/")
        resp = conn.getresponse()
        ct = resp.getheader("Content-Type")
        assert "text/html" in ct


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_multiple_sequential_requests(self, conn):
        """Server should handle multiple requests on same connection."""
        for _ in range(5):
            conn.request("GET", "/api/status")
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()

    def test_query_with_special_characters(self, conn):
        conn.request("GET", "/api/search?q=%E4%B8%AD%E6%96%87")
        resp = conn.getresponse()
        assert resp.status == 200

    def test_empty_path_parameter(self, conn):
        conn.request("GET", "/api/object?path=")
        resp = conn.getresponse()
        assert resp.status == 200
