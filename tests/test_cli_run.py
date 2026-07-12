from pathlib import Path
import json

from click.testing import CliRunner

from distill.cli import cli
from distill.worker_pool import WorkerPool


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "概念").mkdir(parents=True)
    (tmp_path / "知识" / "来源").mkdir(parents=True)
    (tmp_path / "输出").mkdir(parents=True)
    _write_md(
        tmp_path / "知识" / "概念" / "foo.md",
        "---\ntype: concept\ntitle: Foo\nstatus: active\n---\n# Foo",
    )
    _write_md(
        tmp_path / "知识" / "来源" / "bar.md",
        "---\ntype: source\ntitle: Bar\nstatus: linked\n---\n[[Foo]]",
    )
    return tmp_path


def test_run_json_output_is_machine_readable(tmp_path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "run", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "scan" in payload
    assert "worker_pool" in payload
    assert payload["worker_pool"]["requested_mode"] == "auto"
    assert "scan" in payload["worker_pool"]["phases"]
    assert "parse" in payload["worker_pool"]["phases"]
    assert result.output.lstrip().startswith("{")


def test_run_incremental_report_marks_cached_phases(tmp_path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    first = runner.invoke(cli, ["--vault", str(vault), "run"])
    second = runner.invoke(cli, ["--vault", str(vault), "run", "--incremental"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "cached" in second.output
    assert "↺" in second.output


def test_run_accepts_explicit_worker_mode(tmp_path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "run", "--worker-mode", "serial", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "scan" in payload
    assert payload["worker_pool"]["requested_mode"] == "serial"
    assert payload["worker_pool"]["last_mode"] == "serial"


def test_run_markdown_surfaces_worker_pool_summary(tmp_path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "run", "--worker-mode", "serial"])

    assert result.exit_code == 0
    assert "[Worker Pool]" in result.output
    assert "requested_mode: serial" in result.output
    assert "last_mode: serial" in result.output
    assert "fallback_used: false" in result.output
    assert "- scan: last_mode=serial fallback_used=false" in result.output
    assert "- parse: last_mode=serial fallback_used=false" in result.output


def test_run_process_mode_falls_back_without_crashing(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    runner = CliRunner()
    original_hash_files = WorkerPool.hash_files
    marker = {"triggered": False}

    def fake_hash_files(self, file_paths, vault_root, progress_callback=None):
        if self.mode == "process" and not marker["triggered"]:
            marker["triggered"] = True
            self.fallback_used = True
            self.fallback_reason = "simulated process crash"
            self.last_mode = "thread"
            clone = WorkerPool(workers=self.workers, timeout=self.timeout, mode="thread")
            return original_hash_files(clone, file_paths, vault_root, progress_callback)
        return original_hash_files(self, file_paths, vault_root, progress_callback)

    monkeypatch.setattr(WorkerPool, "hash_files", fake_hash_files)

    result = runner.invoke(cli, ["--vault", str(vault), "run", "--worker-mode", "process"])

    assert result.exit_code == 0
    assert marker["triggered"] is True
    assert "Pipeline Execution Report" in result.output
    assert "[Worker Pool]" in result.output
    assert "requested_mode: process" in result.output
    assert "fallback_used: true" in result.output
    assert "fallback_reason: simulated process crash" in result.output


def test_run_json_output_surfaces_process_fallback_metadata(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    runner = CliRunner()
    original_execute_mode = WorkerPool._execute_mode

    def fake_execute_mode(self, mode, normalized, root, worker_fn, progress_callback):
        if mode == "process":
            raise RuntimeError("simulated process crash")
        return original_execute_mode(self, mode, normalized, root, worker_fn, progress_callback)

    monkeypatch.setattr(WorkerPool, "_execute_mode", fake_execute_mode)

    result = runner.invoke(cli, ["--vault", str(vault), "run", "--worker-mode", "process", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["worker_pool"]["requested_mode"] == "process"
    assert payload["worker_pool"]["fallback_used"] is True
    assert "simulated process crash" in payload["worker_pool"]["fallback_reason"]
    assert payload["worker_pool"]["last_mode"] == "thread"
    assert payload["worker_pool"]["phases"]["scan"]["fallback_used"] is True
    assert payload["worker_pool"]["phases"]["parse"]["fallback_used"] is True


def test_status_markdown_surfaces_runtime_stage_and_layout(tmp_path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--vault", str(vault), "status"])

    assert result.exit_code == 0
    assert "runtime_stage: preflight" in result.output
    assert "[Vault Layout]" in result.output
    assert "knowledge_dirs" in result.output
    assert "scan_roots" in result.output
