"""Tests for config and init functionality."""

import tempfile
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from distill.cli import cli
from distill.config import (
    DEFAULT_CONFIG,
    infer_existing_vault_config,
    load_config,
    get_scan_dirs,
    get_ops_dir,
    resolve_path_type,
    resolve_type_status,
)
from distill.init_cmd import init_vault
from distill.index import VaultIndex
from distill.promote import PromotionPipeline


class TestConfig:
    def test_default_config_structure(self):
        assert "vault" in DEFAULT_CONFIG
        assert "objects" in DEFAULT_CONFIG
        assert "promote" in DEFAULT_CONFIG
        assert "search" in DEFAULT_CONFIG
        assert "graph" in DEFAULT_CONFIG

    def test_load_config_without_file(self, tmp_path):
        """Loading config from dir without distill.yaml returns defaults."""
        config = load_config(tmp_path)
        assert config["vault"]["knowledge_dirs"] == DEFAULT_CONFIG["vault"]["knowledge_dirs"]

    def test_load_config_with_yaml(self, tmp_path):
        """User distill.yaml overrides defaults."""
        yaml_content = "vault:\n  knowledge_dirs:\n    - my-knowledge\n"
        (tmp_path / "distill.yaml").write_text(yaml_content, encoding="utf-8")
        config = load_config(tmp_path)
        assert config["vault"]["knowledge_dirs"] == ["my-knowledge"]
        # Other defaults still present
        assert "objects" in config

    def test_get_scan_dirs_zh(self, tmp_path):
        """Finds Chinese knowledge dirs."""
        (tmp_path / "知识").mkdir()
        (tmp_path / "输出").mkdir()
        config = load_config(tmp_path)
        dirs = get_scan_dirs(config, tmp_path)
        assert len(dirs) >= 2
        assert any("知识" in str(d) for d in dirs)

    def test_get_scan_dirs_en(self, tmp_path):
        """Finds English knowledge dirs."""
        (tmp_path / "knowledge").mkdir()
        (tmp_path / "output").mkdir()
        config = load_config(tmp_path)
        dirs = get_scan_dirs(config, tmp_path)
        assert len(dirs) >= 2

    def test_get_ops_dir(self, tmp_path):
        config = load_config(tmp_path)
        ops = get_ops_dir(config, tmp_path)
        assert isinstance(ops, Path)

    def test_resolve_path_type(self):
        config = DEFAULT_CONFIG
        assert resolve_path_type("知识/项目/foo.md", config) == "project"
        assert resolve_path_type("knowledge/concept/bar.md", config) == "concept"
        assert resolve_path_type("random/file.md", config) in ("", "unknown")

    def test_resolve_type_status(self):
        config = DEFAULT_CONFIG
        assert resolve_type_status("entity", config) == "active"
        assert resolve_type_status("output", config) == "draft"

    def test_default_config_includes_skill_specs(self):
        config = DEFAULT_CONFIG
        assert "skill_spec" in config["objects"]["types"]
        assert resolve_type_status("skill_spec", config) == "active"


class TestExistingVaultOnboarding:
    def test_cli_status_accepts_existing_obsidian_vault_without_distill_yaml(self, tmp_path):
        vault = tmp_path / "existing-vault"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "Inbox.md").write_text("# Inbox\n\nLink to [[Plan]]\n", encoding="utf-8")
        (vault / "Projects").mkdir()
        (vault / "Projects" / "Plan.md").write_text("# Plan\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, ["--vault", str(vault), "status"])

        assert result.exit_code == 0
        assert "total_objects: 2" in result.output

    def test_cli_status_auto_detects_existing_obsidian_vault_from_cwd(self, tmp_path, monkeypatch):
        vault = tmp_path / "existing-vault"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "Inbox.md").write_text("# Inbox\n\nLink to [[Plan]]\n", encoding="utf-8")
        (vault / "Projects").mkdir()
        (vault / "Projects" / "Plan.md").write_text("# Plan\n", encoding="utf-8")
        monkeypatch.chdir(vault)

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "total_objects: 2" in result.output

    def test_cli_init_existing_bootstraps_distill_yaml_for_non_empty_vault(self, tmp_path):
        vault = tmp_path / "existing-vault"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "Areas").mkdir()
        (vault / "Areas" / "Strategy.md").write_text("# Strategy\n", encoding="utf-8")
        (vault / "README.md").write_text("keep me\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, ["init", str(vault), "--existing"])

        assert result.exit_code == 0
        config_text = (vault / "distill.yaml").read_text(encoding="utf-8")
        assert "knowledge_dirs:" in config_text
        assert "- Areas" in config_text
        assert (vault / "README.md").read_text(encoding="utf-8") == "keep me\n"

    def test_cli_init_existing_adds_runtime_gitignore_rules_without_clobbering_existing_content(self, tmp_path):
        vault = tmp_path / "existing-vault"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "Areas").mkdir()
        (vault / "Areas" / "Strategy.md").write_text("# Strategy\n", encoding="utf-8")
        (vault / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, ["init", str(vault), "--existing"])

        assert result.exit_code == 0
        gitignore = (vault / ".gitignore").read_text(encoding="utf-8")
        assert ".DS_Store" in gitignore
        assert ".distill/runtime-state.json" in gitignore
        assert ".distill/distill.db*" in gitignore
        assert ".distill/nodes.csv" in gitignore
        assert ".distill/edges.csv" in gitignore

    def test_infer_existing_vault_config_prefers_structured_dirs_over_root_markdown(self, tmp_path):
        vault = tmp_path / "mixed-layout-vault"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "soul.md").write_text("# root note\n", encoding="utf-8")
        (vault / ".claude").mkdir()
        (vault / ".claude" / "README.md").write_text("# agent docs\n", encoding="utf-8")
        (vault / "兼容层").mkdir()
        (vault / "兼容层" / "legacy.md").write_text("# legacy\n", encoding="utf-8")
        (vault / "知识" / "概念").mkdir(parents=True)
        (vault / "知识" / "概念" / "core.md").write_text("# core\n", encoding="utf-8")
        (vault / "输出" / "报告").mkdir(parents=True)
        (vault / "输出" / "报告" / "share.md").write_text("# share\n", encoding="utf-8")
        (vault / "运维" / "索引").mkdir(parents=True)
        (vault / "运维" / "索引" / "总索引.md").write_text("# index\n", encoding="utf-8")
        (vault / "系统" / "规范").mkdir(parents=True)
        (vault / "系统" / "规范" / "对象类型.md").write_text("# spec\n", encoding="utf-8")

        config = infer_existing_vault_config(vault)

        assert config["vault"]["knowledge_dirs"] == ["知识"]
        assert config["vault"]["output_dirs"] == ["输出"]
        assert config["vault"]["ops_dirs"] == ["运维"]
        assert config["vault"]["system_dirs"] == ["系统"]

    def test_cli_init_existing_keeps_status_surface_stable_for_mixed_layout_vault(self, tmp_path):
        vault = tmp_path / "mixed-layout-vault"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "soul.md").write_text("# root note\n", encoding="utf-8")
        (vault / ".claude").mkdir()
        (vault / ".claude" / "README.md").write_text("# agent docs\n", encoding="utf-8")
        (vault / "兼容层").mkdir()
        (vault / "兼容层" / "legacy.md").write_text("# legacy\n", encoding="utf-8")
        (vault / "知识" / "概念").mkdir(parents=True)
        (vault / "知识" / "概念" / "core.md").write_text("# core\n", encoding="utf-8")
        (vault / "输出" / "报告").mkdir(parents=True)
        (vault / "输出" / "报告" / "share.md").write_text("# share\n", encoding="utf-8")
        (vault / "运维" / "索引").mkdir(parents=True)
        (vault / "运维" / "索引" / "总索引.md").write_text("# index\n", encoding="utf-8")
        (vault / "系统" / "规范").mkdir(parents=True)
        (vault / "系统" / "规范" / "对象类型.md").write_text("# spec\n", encoding="utf-8")

        runner = CliRunner()
        before = runner.invoke(cli, ["--vault", str(vault), "status"])
        init_result = runner.invoke(cli, ["init", str(vault), "--existing"])
        after = runner.invoke(cli, ["--vault", str(vault), "status"])

        assert before.exit_code == 0
        assert init_result.exit_code == 0
        assert after.exit_code == 0
        assert "total_objects: 3" in before.output
        assert "total_objects: 3" in after.output
        assert "soul.md" not in before.output
        assert "soul.md" not in after.output
        assert ".claude/README.md" not in before.output
        assert ".claude/README.md" not in after.output
        assert "兼容层/legacy.md" not in before.output
        assert "兼容层/legacy.md" not in after.output

        config_text = (vault / "distill.yaml").read_text(encoding="utf-8")
        assert "- 知识" in config_text
        assert "- 输出" in config_text
        assert "- 运维" in config_text
        assert "- 系统" in config_text
        assert "- ." not in config_text

    def test_vault_index_deduplicates_overlapping_scan_dirs(self, tmp_path):
        vault = tmp_path / "overlap-vault"
        vault.mkdir()
        (vault / "输出").mkdir()
        (vault / "输出" / "report.md").write_text(
            "---\ntitle: report\ntype: output\nstatus: draft\n---\n\n# report\n",
            encoding="utf-8",
        )
        (vault / "distill.yaml").write_text(
            "vault:\n"
            "  knowledge_dirs:\n"
            "    - .\n"
            "  output_dirs:\n"
            "    - 输出\n"
            "  ops_dirs:\n"
            "    - .distill\n"
            "  system_dirs: []\n",
            encoding="utf-8",
        )

        idx = VaultIndex(vault)
        idx.scan()

        assert idx.stats["total_objects"] == 1
        assert [obj["path"] for obj in idx.objects] == ["输出/report.md"]

    def test_promotion_pipeline_uses_default_output_dir_when_config_has_empty_output_dirs(self, tmp_path):
        vault = tmp_path / "flat-vault"
        vault.mkdir()
        (vault / "Daily.md").write_text(
            "---\ntitle: Daily\ntype: source\nstatus: linked\nsource_type: daily\n---\n\nToday we shipped something.\n",
            encoding="utf-8",
        )

        pipe = PromotionPipeline(
            vault,
            config={
                "vault": {
                    "knowledge_dirs": ["."],
                    "output_dirs": [],
                    "ops_dirs": [".distill"],
                    "system_dirs": [],
                },
                "promote": DEFAULT_CONFIG["promote"],
                "objects": DEFAULT_CONFIG["objects"],
                "graph": DEFAULT_CONFIG["graph"],
                "search": DEFAULT_CONFIG["search"],
            },
        )
        pipe.scan()
        actions = pipe.plan()

        assert any(action["target"] == "输出/日志/Daily.md" for action in actions)


class TestInit:
    def test_init_zh_basic(self, tmp_path):
        """Init creates Chinese vault skeleton."""
        target = tmp_path / "my-vault"
        result = init_vault(str(target), lang="zh", with_examples=False)
        assert result["dirs_created"] > 0
        assert result["files_created"] > 0
        assert (target / "知识").is_dir()
        assert (target / "输出").is_dir()
        assert (target / "运维").is_dir()
        assert (target / "distill.yaml").exists()

    def test_init_en_basic(self, tmp_path):
        """Init creates English vault skeleton."""
        target = tmp_path / "my-vault"
        result = init_vault(str(target), lang="en", with_examples=False)
        assert result["dirs_created"] > 0
        assert (target / "knowledge").is_dir()
        assert (target / "output").is_dir()
        assert (target / "ops").is_dir()
        assert (target / "distill.yaml").exists()

    def test_init_with_examples(self, tmp_path):
        """Init with examples creates sample objects."""
        target = tmp_path / "my-vault"
        result = init_vault(str(target), lang="zh", with_examples=True)
        # Should have more files with examples
        assert result["files_created"] > 10
        # Should find at least some objects when scanned
        from distill.index import VaultIndex
        idx = VaultIndex(target)
        idx.scan()
        assert idx.stats["total_objects"] >= 5

    def test_init_idempotent(self, tmp_path):
        """Init on existing dir doesn't crash."""
        target = tmp_path / "my-vault"
        init_vault(str(target), lang="zh")
        # Second init should succeed (exist_ok)
        result = init_vault(str(target), lang="zh")
        assert result["dirs_created"] >= 0

    def test_init_en_with_examples(self, tmp_path):
        """English init with examples works."""
        target = tmp_path / "my-vault"
        result = init_vault(str(target), lang="en", with_examples=True)
        assert result["files_created"] > 10
        from distill.index import VaultIndex
        idx = VaultIndex(target)
        idx.scan()
        assert idx.stats["total_objects"] >= 5

    def test_init_creates_templates(self, tmp_path):
        """Each object type dir has a template file."""
        target = tmp_path / "my-vault"
        init_vault(str(target), lang="zh")
        # Check a few template files
        assert (target / "知识" / "项目" / "_模板.md").exists()
        assert (target / "知识" / "概念" / "_模板.md").exists()
        project_template = (target / "知识" / "项目" / "_模板.md").read_text(encoding="utf-8")
        concept_template = (target / "知识" / "概念" / "_模板.md").read_text(encoding="utf-8")
        assert "presentation: project-handbook-v1" in project_template
        assert "## 资产与系统地图" in project_template
        assert "presentation: knowledge-compounding-v1" in concept_template
        assert "## 知识生命周期" in concept_template
        # Template should have frontmatter
        import frontmatter
        try:
            post = frontmatter.load(str(target / "知识" / "项目" / "_模板.md"))
            assert "type" in post.metadata
        except Exception:
            # Template may have {{today}} placeholder that's not valid YAML
            content = (target / "知识" / "项目" / "_模板.md").read_text()
            assert "type:" in content

    def test_init_creates_root_readme_with_first_win_path(self, tmp_path):
        target = tmp_path / "my-vault"
        init_vault(str(target), lang="zh", with_examples=False)
        readme = (target / "README.md").read_text(encoding="utf-8")
        assert "distill status" in readme
        assert "distill lint" in readme
        assert "distill run" in readme
        assert "知识/概念/_模板.md" in readme
        assert "知识/" in readme
        assert "输出/" in readme
        assert "运维/" in readme
        assert "系统/规范/" in readme

    def test_init_creates_gitignore_with_runtime_artifact_rules(self, tmp_path):
        target = tmp_path / "my-vault"
        init_vault(str(target), lang="zh", with_examples=False)

        gitignore = (target / ".gitignore").read_text(encoding="utf-8")
        assert ".distill/runtime-state.json" in gitignore
        assert ".distill/distill.db*" in gitignore
        assert ".distill/nodes.csv" in gitignore
        assert ".distill/edges.csv" in gitignore

    def test_cli_init_output_points_to_readme_and_examples_path(self, tmp_path):
        target = tmp_path / "demo-vault"
        runner = CliRunner()
        result = runner.invoke(cli, ["init", str(target), "--lang", "zh", "--examples"])
        assert result.exit_code == 0
        assert "打开 README.md" in result.output
        assert "distill status" in result.output
        assert "distill lint" in result.output
        assert "distill run" in result.output
        assert "distill search \"知识库\" --mode hybrid" in result.output
