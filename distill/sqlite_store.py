"""Rebuildable SQLite/FTS5 projection for vault objects and relations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .snapshot import VaultSnapshot
from .vault_semantics import (
    FRONTMATTER_EDGE_TYPES,
    build_lookup_indexes,
    extract_frontmatter_links,
    extract_wikilinks,
    resolve_link_target,
)


SCHEMA_VERSION = 1


class SQLiteVaultStore:
    def __init__(self, vault_root: Path | str, db_path: Path | None = None):
        self.vault = Path(vault_root).expanduser().resolve()
        self.db_path = db_path or (self.vault / ".distill" / "distill.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def rebuild(self, snapshot: VaultSnapshot) -> dict[str, Any]:
        objects = [obj.as_dict(include_content=True) for obj in snapshot.objects]
        path_index, title_index, filename_index = build_lookup_indexes(objects)
        edges: set[tuple[str, str, str]] = set()

        for obj in snapshot.objects:
            for link in extract_wikilinks(obj.content):
                target = resolve_link_target(
                    link,
                    path_index=path_index,
                    title_index=title_index,
                    filename_index=filename_index,
                )
                if target:
                    edges.add((obj.path, target, "wikilink"))
            for field, relation in FRONTMATTER_EDGE_TYPES.items():
                for link in extract_frontmatter_links(
                    dict(obj.frontmatter),
                    relation_fields=[field],
                    include_plain_strings=True,
                ):
                    target = resolve_link_target(
                        link,
                        path_index=path_index,
                        title_index=title_index,
                        filename_index=filename_index,
                    )
                    if target:
                        edges.add((obj.path, target, relation))
            for link in extract_frontmatter_links(
                dict(obj.frontmatter),
                include_plain_strings=True,
            ):
                target = resolve_link_target(
                    link,
                    path_index=path_index,
                    title_index=title_index,
                    filename_index=filename_index,
                )
                if target:
                    edges.add((obj.path, target, "wikilink"))

        with self.connect() as connection:
            self._create_schema(connection)
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM objects")
            connection.execute("DELETE FROM object_fts")
            connection.executemany(
                """
                INSERT INTO objects(path, object_id, title, type, status, content, frontmatter_json, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        obj.path,
                        obj.frontmatter.get("id"),
                        obj.title,
                        obj.type,
                        obj.status,
                        obj.content,
                        json.dumps(dict(obj.frontmatter), ensure_ascii=False, sort_keys=True, default=str),
                        len(obj.content.split()),
                    )
                    for obj in snapshot.objects
                ],
            )
            connection.executemany(
                "INSERT INTO edges(source_path, target_path, relation) VALUES (?, ?, ?)",
                sorted(edges),
            )
            connection.executemany(
                "INSERT INTO object_fts(path, title, content) VALUES (?, ?, ?)",
                [(obj.path, obj.title, obj.content) for obj in snapshot.objects],
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

        return {
            "nodes": len(snapshot.objects),
            "edges": len(edges),
            "db_path": str(self.db_path),
            "schema_version": SCHEMA_VERSION,
        }

    def all_objects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT path, object_id, title, type, status, word_count FROM objects ORDER BY path"
            ).fetchall()
        return [dict(row) for row in rows]

    def all_edges(self) -> list[dict[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT source_path, target_path, relation FROM edges ORDER BY source_path, target_path, relation"
            ).fetchall()
        return [dict(row) for row in rows]

    def incoming(self, path: str) -> list[dict[str, str]]:
        return self._adjacent("target_path", path)

    def outgoing(self, path: str) -> list[dict[str, str]]:
        return self._adjacent("source_path", path)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.path, o.title, o.type, o.status, bm25(object_fts) AS score,
                       snippet(object_fts, 2, '', '', ' … ', 24) AS excerpt
                FROM object_fts
                JOIN objects o ON o.path = object_fts.path
                WHERE object_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _adjacent(self, column: str, path: str) -> list[dict[str, str]]:
        if column not in {"source_path", "target_path"}:
            raise ValueError(f"invalid adjacency column: {column}")
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT source_path, target_path, relation FROM edges WHERE {column} = ? ORDER BY source_path, target_path",
                (path,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS objects(
                path TEXT PRIMARY KEY,
                object_id TEXT UNIQUE,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                content TEXT NOT NULL,
                frontmatter_json TEXT NOT NULL,
                word_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges(
                source_path TEXT NOT NULL REFERENCES objects(path) ON DELETE CASCADE,
                target_path TEXT NOT NULL REFERENCES objects(path) ON DELETE CASCADE,
                relation TEXT NOT NULL,
                PRIMARY KEY(source_path, target_path, relation)
            );
            CREATE INDEX IF NOT EXISTS edges_target_idx ON edges(target_path);
            CREATE VIRTUAL TABLE IF NOT EXISTS object_fts USING fts5(
                path UNINDEXED,
                title,
                content,
                tokenize='unicode61'
            );
            """
        )
