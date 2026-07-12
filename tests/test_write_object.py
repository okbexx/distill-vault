import json
from pathlib import Path
from hashlib import sha256

from click.testing import CliRunner
import pytest

from distill.cli import cli
from distill.write_object import write_object


def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "知识" / "决策").mkdir(parents=True)
    return tmp_path


def test_write_object_writes_markdown_inside_vault(tmp_path: Path):
    vault = _make_vault(tmp_path)
    content = "# Product\n"

    result = write_object(vault, "知识/决策/product.md", content)

    assert result.status == "written"
    assert result.path == "知识/决策/product.md"
    assert result.overwritten is False
    assert result.bytes_written == len(content.encode("utf-8"))
    assert result.sha256 == sha256(content.encode("utf-8")).hexdigest()
    assert (vault / "知识" / "决策" / "product.md").read_text(encoding="utf-8") == content


def test_write_object_rejects_invalid_targets_and_empty_content(tmp_path: Path):
    vault = _make_vault(tmp_path)

    invalid_targets = [
        "",
        "/tmp/outside.md",
        "C:\\tmp\\outside.md",
        "../outside.md",
        "知识/../outside.md",
        "知识/决策/product.txt",
    ]
    for target in invalid_targets:
        with pytest.raises(ValueError):
            write_object(vault, target, "# Product\n")

    with pytest.raises(ValueError):
        write_object(vault, "知识/决策/product.md", "")

    with pytest.raises(ValueError):
        write_object(vault, "知识/决策/product.md", "   \n")


def test_write_object_blocks_path_escape_through_symlink(tmp_path: Path):
    vault = _make_vault(tmp_path / "vault")
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / "知识" / "linked").symlink_to(outside)

    with pytest.raises(ValueError):
        write_object(vault, "知识/linked/escape.md", "# Escape\n")

    assert not (outside / "escape.md").exists()


def test_write_object_does_not_overwrite_without_flag(tmp_path: Path):
    vault = _make_vault(tmp_path)
    target = vault / "知识" / "决策" / "product.md"
    target.write_text("# Existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_object(vault, "知识/决策/product.md", "# Product\n")

    assert target.read_text(encoding="utf-8") == "# Existing\n"


def test_write_object_overwrites_with_flag(tmp_path: Path):
    vault = _make_vault(tmp_path)
    target = vault / "知识" / "决策" / "product.md"
    target.write_text("# Existing\n", encoding="utf-8")

    result = write_object(vault, "知识/决策/product.md", "# Product\n", overwrite=True)

    assert result.overwritten is True
    assert target.read_text(encoding="utf-8") == "# Product\n"


def test_cli_write_object_reads_stdin_and_returns_json(tmp_path: Path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--vault", str(vault), "write-object", "--target", "知识/决策/product.md", "--format", "json"],
        input="# Product\n",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "written"
    assert payload["path"] == "知识/决策/product.md"
    assert payload["bytes_written"] == len("# Product\n".encode("utf-8"))
    assert payload["sha256"] == sha256("# Product\n".encode("utf-8")).hexdigest()
    assert payload["overwritten"] is False
    assert (vault / "知识" / "决策" / "product.md").read_text(encoding="utf-8") == "# Product\n"


def test_cli_write_object_rejects_empty_target_and_stdin(tmp_path: Path):
    vault = _make_vault(tmp_path)
    runner = CliRunner()

    empty_target = runner.invoke(
        cli,
        ["--vault", str(vault), "write-object", "--target", "", "--format", "json"],
        input="# Product\n",
    )
    assert empty_target.exit_code != 0
    assert "target path is required" in empty_target.output

    empty_input = runner.invoke(
        cli,
        ["--vault", str(vault), "write-object", "--target", "知识/决策/product.md", "--format", "json"],
        input="",
    )
    assert empty_input.exit_code != 0
    assert "content is required" in empty_input.output
