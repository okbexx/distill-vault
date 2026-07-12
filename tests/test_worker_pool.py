from pathlib import Path

import pytest

from distill.worker_pool import WorkerPool


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_files(tmp_path: Path) -> tuple[list[Path], Path]:
    vault = tmp_path
    files = [
        vault / "知识" / "概念" / "foo.md",
        vault / "知识" / "来源" / "bar.md",
    ]
    _write_md(files[0], "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n[[Bar]]")
    _write_md(files[1], "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]")
    return files, vault


def test_worker_pool_auto_prefers_thread_mode(tmp_path):
    files, vault = _make_files(tmp_path)
    pool = WorkerPool(mode="auto", workers=2)

    hashes = pool.hash_files(files, vault)

    assert set(hashes) == {"知识/概念/foo.md", "知识/来源/bar.md"}
    assert pool.last_mode == "thread"
    assert pool.fallback_used is False


def test_worker_pool_serial_mode_parses_files(tmp_path):
    files, vault = _make_files(tmp_path)
    pool = WorkerPool(mode="serial", workers=1)

    objects = pool.parse_files(files, vault)

    assert sorted(obj["title"] for obj in objects) == ["Bar", "Foo"]
    assert pool.last_mode == "serial"


def test_worker_pool_process_falls_back_to_thread(tmp_path, monkeypatch):
    files, vault = _make_files(tmp_path)
    pool = WorkerPool(mode="process", fallback_mode="thread", workers=2)

    original_execute = pool._execute_mode

    def fake_execute(mode, normalized, root, worker_fn, progress_callback):
        if mode == "process":
            raise RuntimeError("simulated process crash")
        return original_execute(mode, normalized, root, worker_fn, progress_callback)

    monkeypatch.setattr(pool, "_execute_mode", fake_execute)

    hashes = pool.hash_files(files, vault)

    assert set(hashes) == {"知识/概念/foo.md", "知识/来源/bar.md"}
    assert pool.last_mode == "thread"
    assert pool.fallback_used is True
    assert "simulated process crash" in (pool.fallback_reason or "")


def test_worker_pool_rejects_invalid_mode():
    with pytest.raises(ValueError, match="Unsupported worker mode"):
        WorkerPool(mode="bogus")
