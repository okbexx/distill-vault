import json

from distill.config import load_config
from distill.schema import validate_snapshot
from distill.snapshot import VaultSnapshot
from distill.sqlite_store import SQLiteVaultStore


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_snapshot_parses_each_object_and_sqlite_projects_graph_and_fts(tmp_path):
    _write(
        tmp_path / "知识" / "项目" / "alpha.md",
        "---\nid: project-alpha\ntitle: Alpha\ntype: project\nstatus: active\n---\n\nLinks [[知识/来源/source]]\n",
    )
    _write(
        tmp_path / "知识" / "来源" / "source.md",
        "---\nid: source-alpha\ntitle: Source\ntype: source\nstatus: active\n---\n\nSQLite migration evidence.\n",
    )

    snapshot = VaultSnapshot.scan(tmp_path)
    assert [obj.path for obj in snapshot.objects] == [
        "知识/来源/source.md",
        "知识/项目/alpha.md",
    ]

    store = SQLiteVaultStore(tmp_path)
    result = store.rebuild(snapshot)

    assert result["nodes"] == 2
    assert result["edges"] == 1
    assert store.outgoing("知识/项目/alpha.md")[0]["target_path"] == "知识/来源/source.md"
    assert store.search("migration")[0]["path"] == "知识/来源/source.md"


def test_snapshot_validation_uses_instance_json_schema(tmp_path):
    _write(
        tmp_path / "知识" / "项目" / "alpha.md",
        "---\ntitle: Alpha\ntype: project\nstatus: active\n---\n\n# Alpha\n",
    )
    schema_path = tmp_path / "系统" / "规范" / "object.schema.json"
    _write(
        schema_path,
        json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["id", "title", "type", "status"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "title": {"type": "string"},
                "type": {"type": "string"},
                "status": {"type": "string"},
            },
        }, ensure_ascii=False),
    )
    (tmp_path / "distill.yaml").write_text(
        "vault:\n  knowledge_dirs: [知识]\n  system_dirs: [系统]\n  output_dirs: []\n  ops_dirs: [.distill]\nschema:\n  path: 系统/规范/object.schema.json\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)
    issues = validate_snapshot(VaultSnapshot.scan(tmp_path, config=config), config)

    assert len(issues) == 1
    assert issues[0].path == "知识/项目/alpha.md"
    assert "'id' is a required property" in issues[0].message
