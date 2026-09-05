"""Raw evidence is searchable, but never promoted into curated metadata/edges."""
import json
import subprocess
from pathlib import Path

import frontmatter
import pytest
import yaml
from click.testing import CliRunner

from distill.cli import cli as main
from distill.config import load_config
from distill.index import VaultIndex
from distill.lint import VaultLinter
from distill.schema import validate_snapshot
from distill.snapshot import VaultSnapshot
from distill.source_record import record_source
from distill.sqlite_store import SQLiteVaultStore


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    root = tmp_path / "vault"
    root.mkdir()
    for name in ("知识", "收件箱"):
        (root / name).mkdir()
    (root / "distill.yaml").write_text(yaml.safe_dump({
        "vault": {"knowledge_dirs": ["知识", "收件箱"], "output_dirs": [],
                  "system_dirs": [], "ops_dirs": ["运维"]},
        "capture": {"source_dir": "收件箱"},
        "schema": {"path": "schema.json", "include_globs": ["知识/**", "收件箱/**"]},
    }), encoding="utf-8")
    (root / "schema.json").write_text(json.dumps({"type": "object", "required": ["id", "title", "type", "status"]}))
    return root


def put(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def errors(root):
    linter = VaultLinter(root)
    linter.scan()
    return [i for i in linter.lint() if i["severity"] == "error"]


def test_plain_desktop_note_is_raw_and_searchable_without_rewrite(vault):
    note = put(vault, "收件箱/desktop.md", "# Desktop\nrawneedle [[unprocessed reference]]\n")
    original = note.read_bytes()
    snapshot = VaultSnapshot.scan(vault)
    obj = snapshot.by_path["收件箱/desktop.md"]
    assert (obj.type, obj.status, obj.links) == ("source", "raw", ())
    assert not errors(vault)
    assert not validate_snapshot(snapshot, load_config(vault))
    store = SQLiteVaultStore(vault)
    store.rebuild(snapshot)
    assert store.search("rawneedle")[0]["path"] == obj.path
    assert note.read_bytes() == original


@pytest.mark.parametrize("metadata", ["type: concept\nstatus: active", "type: project", "status: active"])
def test_stable_inbox_objects_do_not_receive_raw_exemption(vault, metadata):
    put(vault, "收件箱/stable.md", f"---\n{metadata}\n---\n[[missing stable target]]")
    found = errors(vault)
    assert any(i["rule"] == "broken-wikilink" for i in found)
    assert any(i["rule"] == "schema-validation" for i in found)


def test_legacy_source_directory_remains_validated(vault):
    put(vault, "知识/来源/legacy.md", "[[legacy missing]]")
    assert {i["rule"] for i in errors(vault)} >= {"broken-wikilink", "schema-validation"}


@pytest.mark.parametrize("header", ["id: stolen\ntype: concept\nstatus: active\nprojects: ['[[missing project]]']", "bad: [unterminated"])
def test_markdown_attachment_is_opaque_searchable_evidence(vault, tmp_path, header):
    payload = ("---\r\n" + header.replace("\n", "\r\n") + "\r\n---\r\nattachmentneedle [[missing]]\r\n").encode()
    source = tmp_path / "article.md"
    source.write_bytes(payload)
    result = record_source(vault, "raw text", attachments=[str(source)])
    path = result["attachment_paths"][0]
    metadata = frontmatter.load(vault / result["source_path"]).metadata
    assert metadata["attachments"] == [(vault / path).name]
    snapshot = VaultSnapshot.scan(vault)
    assert not snapshot.diagnostics
    obj = snapshot.by_path[path]
    assert obj.type == "source" and obj.status == "raw"
    assert "stolen" not in snapshot.by_id
    assert "projects" not in obj.frontmatter
    assert obj.links == ()
    assert obj.content.encode() == payload
    assert not errors(vault)
    store = SQLiteVaultStore(vault)
    store.rebuild(snapshot)
    assert path in [r["path"] for r in store.search("attachmentneedle")]
    assert (vault / path).read_bytes() == payload


def test_from_objects_discards_preextracted_raw_links(vault):
    for metadata in ({}, {"type": "source", "status": "raw"}):
        snapshot = VaultSnapshot.from_objects(vault, [{"path": "收件箱/plain.md", "frontmatter": metadata,
            "content": "needle [[missing]]", "wikilinks": ["missing"]}])
        obj = snapshot.objects[0]
        assert (obj.type, obj.status, obj.links) == ("source", "raw", ())


def test_from_objects_attachment_metadata_is_not_trusted(vault, tmp_path):
    original = tmp_path / "article.md"
    original.write_text("---\nid: stolen\n---\noriginalneedle [[missing]]")
    result = record_source(vault, "capture", attachments=[str(original)])
    snapshot = VaultSnapshot.from_objects(vault, [{"path": result["attachment_paths"][0],
        "frontmatter": {"id": "stolen"}, "content": "originalneedle [[missing]]", "wikilinks": ["missing"]}])
    obj = snapshot.objects[0]
    assert "id" not in obj.frontmatter
    assert obj.content == original.read_text()
    assert obj.links == ()


def test_old_bundle_compatibility_requires_writer_shape_and_link(vault, tmp_path):
    original = tmp_path / "old.md"
    original.write_text("---\nbad: [oops\n---\noldneedle [[missing]]")
    result = record_source(vault, "capture", attachments=[str(original)])
    source = vault / result["source_path"]
    post = frontmatter.load(source)
    post.metadata.pop("attachments", None)
    source.write_text(frontmatter.dumps(post))
    snapshot = VaultSnapshot.scan(vault)
    assert not snapshot.diagnostics
    assert snapshot.by_path[result["attachment_paths"][0]].links == ()
    sibling = put(vault, str(source.parent.relative_to(vault) / "2-unlisted.md"), "---\ntype: concept\nstatus: active\n---\n[[missing]]")
    assert VaultSnapshot.scan(vault).by_path[str(sibling.relative_to(vault))].links == ("missing",)


def test_attachment_manifest_cannot_claim_outside_bundle_or_follow_symlink(vault, tmp_path):
    stable = put(vault, "知识/stable.md", "---\ntype: concept\nstatus: active\n---\n[[missing]]")
    secret = tmp_path / "secret.md"
    secret.write_text("secretboundaryneedle")
    result = record_source(vault, "capture")
    source = vault / result["source_path"]
    post = frontmatter.load(source)
    post["attachments"] = ["../../知识/stable.md", str(secret), "1-secret.md"]
    source.write_text(frontmatter.dumps(post))
    (source.parent / "1-secret.md").symlink_to(secret)
    snapshot = VaultSnapshot.scan(vault)
    assert snapshot.by_path["知识/stable.md"].links == ("missing",)
    assert all("secretboundaryneedle" not in obj.content for obj in snapshot.objects)
    from distill.phases import build_pipeline
    dag = build_pipeline(vault)
    dag.run()
    assert all("secretboundaryneedle" not in obj.content for obj in dag.ctx.get("snapshot").objects)
    assert str((source.parent / "1-secret.md").relative_to(vault)) not in dag.ctx.get("file_hashes")


def test_plain_raw_body_does_not_create_sqlite_edges(vault):
    put(vault, "知识/target.md", "---\nid: target\ntitle: Target\ntype: concept\nstatus: active\n---\n")
    put(vault, "收件箱/raw.md", "[[Target]] rawneedle")
    store = SQLiteVaultStore(vault)
    store.rebuild(VaultSnapshot.scan(vault))
    assert store.outgoing("收件箱/raw.md") == []


def test_raw_note_can_be_committed_with_real_scoped_cli(vault):
    put(vault, "收件箱/desktop.md", "commitneedle [[unprocessed]]")
    for args in (["init"], ["config", "user.email", "test@example.invalid"], ["config", "user.name", "Test"]):
        subprocess.run(["git", *args], cwd=vault, check=True, capture_output=True)
    result = CliRunner().invoke(main, ["-v", str(vault), "commit", "raw capture", "--paths", "收件箱/desktop.md", "--skip-run"])
    assert result.exit_code == 0, result.output
    committed = subprocess.run(["git", "show", "HEAD:收件箱/desktop.md"], cwd=vault, check=True, capture_output=True, text=True)
    assert "commitneedle" in committed.stdout


def test_lint_fix_preserves_raw_original_bytes(vault, tmp_path):
    source = tmp_path / "original.md"
    original = b"---\r\ntype: concept\r\n---\r\n[[Target|Alias]] [[file.pdf]]\r\n"
    source.write_bytes(original)
    result = record_source(vault, "[[Target|Alias]]", attachments=[str(source)])
    plain = put(vault, "收件箱/desktop.md", "[[Target|Alias]] [[file.pdf]]")
    before = {path: (vault / path).read_bytes() for path in result["touched_paths"]}
    before["收件箱/desktop.md"] = plain.read_bytes()
    linter = VaultLinter(vault)
    linter.scan()
    linter.lint(fix=True)
    assert all((vault / path).read_bytes() == value for path, value in before.items())


@pytest.mark.parametrize("mode", [None, "serial", "thread"])
def test_pipeline_uses_same_raw_semantics_before_worker_parse(vault, tmp_path, mode):
    from distill.phases import build_pipeline
    from distill.worker_pool import WorkerPool

    source = tmp_path / "original.md"
    source.write_bytes(b"---\r\nbad: [unterminated\r\n---\r\nattachmentneedle [[missing]]")
    result = record_source(vault, "rawneedle [[missing]]", attachments=[str(source)])
    put(vault, "收件箱/desktop.md", "desktopneedle [[missing]]")
    dag = build_pipeline(vault, worker_pool=WorkerPool(mode=mode) if mode else None)
    dag.run()
    assert not dag.ctx.get("parse_failures")
    snapshot = dag.ctx.get("snapshot")
    expected = VaultSnapshot.scan(vault)
    assert snapshot.by_path == expected.by_path
    assert all(not obj.links for obj in snapshot.objects)
    store = SQLiteVaultStore(vault)
    assert store.search("attachmentneedle")[0]["path"] == result["attachment_paths"][0]
    assert store.all_edges() == []


def test_raw_metadata_relations_remain_validated(vault):
    put(vault, "收件箱/related.md", "---\ntype: source\nstatus: raw\nprojects: ['[[missing project]]']\n---\n[[unprocessed body]]")
    found = errors(vault)
    assert [i["link"] for i in found if i["rule"] == "broken-wikilink"] == ["missing project"]


def test_from_objects_preserves_stable_top_level_title_fallback(vault):
    snapshot = VaultSnapshot.from_objects(vault, [{
        "path": "知识/stable.md", "title": "Stable display title", "type": "concept",
        "status": "active", "frontmatter": {}, "content": "[[missing]]",
    }])
    obj = snapshot.objects[0]
    assert obj.title == "Stable display title"
    assert obj.type == "concept" and obj.status == "active"
    assert obj.links == ("missing",)
    assert "title" not in obj.frontmatter


def test_old_arbitrary_source_bundle_does_not_claim_siblings(vault):
    put(vault, "知识/来源/legacy/source.md", "---\ntype: source\nstatus: raw\n---\n[Attachment](1-stable.md)")
    put(vault, "知识/来源/legacy/original.txt", "raw")
    stable = put(vault, "知识/来源/legacy/1-stable.md", "---\ntype: concept\nstatus: active\n---\n[[missing]]")
    obj = VaultSnapshot.scan(vault).by_path[stable.relative_to(vault).as_posix()]
    assert obj.links == ("missing",)
    assert obj.type == "concept"
