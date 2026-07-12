"""Typed graph facade backed by the rebuildable SQLite vault projection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .snapshot import VaultSnapshot
from .sqlite_store import SQLiteVaultStore


class GraphIndex:
    """Compatibility facade for object/edge graph consumers.

    New code must use the typed methods. ``query`` only covers the legacy
    read-only queries needed during the v1 migration and is not a Cypher
    implementation.
    """

    def __init__(self, vault_root: Path, db_path: Path | None = None):
        self.vault = Path(vault_root).expanduser().resolve()
        self.store = SQLiteVaultStore(self.vault, db_path=db_path)
        self.db_path = self.store.db_path

    def build(self, snapshot: VaultSnapshot | None = None) -> dict[str, Any]:
        return self.store.rebuild(snapshot or VaultSnapshot.scan(self.vault))

    def has_data(self) -> bool:
        if not self.db_path.exists():
            return False
        try:
            with self.store.connect() as connection:
                row = connection.execute("SELECT COUNT(*) FROM objects").fetchone()
            return bool(row and row[0] >= 0)
        except Exception:
            return False

    def all_objects(self) -> list[dict[str, Any]]:
        return self.store.all_objects()

    def all_edges(self) -> list[dict[str, str]]:
        return self.store.all_edges()

    def incoming(self, path: str) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.path, o.title, o.type, e.relation
                FROM edges e
                JOIN objects o ON o.path = e.source_path
                WHERE e.target_path = ?
                ORDER BY o.path, e.relation
                """,
                (path,),
            ).fetchall()
        return [dict(row) for row in rows]

    def outgoing(self, path: str) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.path, o.title, o.type, e.relation
                FROM edges e
                JOIN objects o ON o.path = e.target_path
                WHERE e.source_path = ?
                ORDER BY o.path, e.relation
                """,
                (path,),
            ).fetchall()
        return [dict(row) for row in rows]

    def type_distribution(self) -> list[list[Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT type, COUNT(*) AS count FROM objects GROUP BY type ORDER BY type"
            ).fetchall()
        return [[row["type"], row["count"]] for row in rows]

    def persist_communities(self, communities: list[dict[str, Any]]) -> None:
        with self.store.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS communities(
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    density REAL NOT NULL,
                    keywords_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS community_members(
                    community_id TEXT NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
                    object_path TEXT NOT NULL REFERENCES objects(path) ON DELETE CASCADE,
                    PRIMARY KEY(community_id, object_path)
                );
                """
            )
            connection.execute("DELETE FROM community_members")
            connection.execute("DELETE FROM communities")
            for item in communities:
                connection.execute(
                    "INSERT INTO communities(id, label, size, density, keywords_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        item["id"],
                        item["label"],
                        int(item.get("size", 0)),
                        float(item.get("density", 0.0)),
                        json.dumps(item.get("keywords", []), ensure_ascii=False),
                    ),
                )
                connection.executemany(
                    "INSERT INTO community_members(community_id, object_path) VALUES (?, ?)",
                    [(item["id"], member) for member in item.get("members", [])],
                )

    def list_communities(self) -> list[dict[str, Any]]:
        try:
            with self.store.connect() as connection:
                rows = connection.execute(
                    "SELECT id, label, size, density, keywords_json FROM communities ORDER BY id"
                ).fetchall()
        except Exception:
            return []
        return [
            {
                "id": row["id"],
                "label": row["label"],
                "size": row["size"],
                "density": row["density"],
                "keywords": json.loads(row["keywords_json"]),
            }
            for row in rows
        ]

    def community_members(self, community_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.path, o.title, o.type
                FROM community_members m
                JOIN objects o ON o.path = m.object_path
                WHERE m.community_id = ?
                ORDER BY o.path
                """,
                (community_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def object_communities(self, path: str) -> list[dict[str, Any]]:
        try:
            with self.store.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT c.id, c.label, c.size, c.density, c.keywords_json
                    FROM community_members m
                    JOIN communities c ON c.id = m.community_id
                    WHERE m.object_path = ?
                    ORDER BY c.id
                    """,
                    (path,),
                ).fetchall()
        except Exception:
            return []
        return [
            {
                "id": row["id"],
                "label": row["label"],
                "size": row["size"],
                "density": row["density"],
                "keywords": json.loads(row["keywords_json"]),
            }
            for row in rows
        ]

    def query(self, statement: str) -> list[list[Any]]:
        """Run a limited read-only compatibility query.

        This intentionally supports only the former public smoke queries. New
        code must use typed methods so Distill does not grow a custom Cypher
        parser around an archived graph dependency.
        """
        normalized = re.sub(r"\s+", " ", statement.strip())
        if normalized == "MATCH (a:Object)-[r:Links]->(b:Object) RETURN a.path, r.link_type, b.path":
            return [
                [row["source_path"], row["relation"], row["target_path"]]
                for row in self.all_edges()
            ]
        if normalized == "MATCH (a:Object)-[r:Links]->(b:Object) RETURN a.path, b.path, r.link_type":
            return [
                [row["source_path"], row["target_path"], row["relation"]]
                for row in self.all_edges()
            ]
        if normalized == "MATCH (o:Object) RETURN o.path, o.title, o.type, o.status, o.word_count":
            return [
                [row["path"], row["title"], row["type"], row["status"], row["word_count"]]
                for row in self.all_objects()
            ]
        if re.fullmatch(r"MATCH \(n\) RETURN count\(n\)", normalized, flags=re.IGNORECASE):
            return [[len(self.all_objects())]]
        if normalized == "MATCH (o:Object) RETURN o.path LIMIT 1":
            objects = self.all_objects()
            return [[objects[0]["path"]]] if objects else []
        raise ValueError(
            "Cypher compatibility is limited in Distill v1; use typed graph tools instead"
        )
