"""Configuration loader for distill-vault."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml


DEFAULT_CONFIG = {
    "vault": {
        "knowledge_dirs": ["知识", "knowledge"],
        "output_dirs": ["输出", "output"],
        "ops_dirs": ["运维", "ops"],
        "system_dirs": ["系统", "system"],
    },
    "objects": {
        "types": [
            "source",
            "project",
            "concept",
            "entity",
            "decision",
            "constraint",
            "output",
            "analysis",
            "skill_spec",
        ],
        "statuses": ["active", "draft", "archived", "linked", "unknown"],
        "path_type_map": {
            "知识/来源/": "source",
            "知识/项目/": "project",
            "知识/实体/": "entity",
            "知识/概念/": "concept",
            "知识/决策/": "decision",
            "知识/约束/": "constraint",
            "知识/分析/": "analysis",
            "输出/": "output",
            "knowledge/source/": "source",
            "knowledge/sources/": "source",
            "knowledge/project/": "project",
            "knowledge/projects/": "project",
            "knowledge/entity/": "entity",
            "knowledge/entities/": "entity",
            "knowledge/concept/": "concept",
            "knowledge/concepts/": "concept",
            "knowledge/decision/": "decision",
            "knowledge/decisions/": "decision",
            "knowledge/constraint/": "constraint",
            "knowledge/constraints/": "constraint",
            "knowledge/analysis/": "analysis",
            "output/": "output",
        },
        "type_status_map": {
            "entity": "active",
            "source": "linked",
            "project": "active",
            "concept": "active",
            "decision": "active",
            "constraint": "active",
            "output": "draft",
            "analysis": "draft",
            "skill_spec": "active",
        },
    },
    "promote": {
        "exclude_types": ["daily", "weekly", "note"],
        "min_backlinks": 2,
        "min_words": 100,
    },
    "exports": {
        "index_path": None,
        "health_path": None,
    },
    "runtime": {
        "engine_version": None,
        "editable_source_path": None,
    },
    "search": {
        "chinese_stopwords": [
            "项目",
            "知识",
            "来源",
            "输出",
            "相关",
            "一个",
            "一些",
            "以及",
            "我们",
            "你们",
            "它们",
            "可以",
            "已经",
            "但是",
            "因为",
            "所以",
            "如果",
            "虽然",
            "不过",
        ]
    },
    "graph": {
        "relation_prefixes": [
            "知识/概念",
            "知识/项目",
            "知识/来源",
            "知识/实体",
            "知识/决策",
            "知识/约束",
            "知识/分析",
            "输出",
        ],
        "relation_prefixes_en": [
            "knowledge/concept",
            "knowledge/concepts",
            "knowledge/project",
            "knowledge/projects",
            "knowledge/source",
            "knowledge/sources",
            "knowledge/entity",
            "knowledge/entities",
            "knowledge/decision",
            "knowledge/decisions",
            "knowledge/constraint",
            "knowledge/constraints",
            "knowledge/analysis",
            "output",
        ],
    },
}

IGNORED_DISCOVERY_DIRS = {
    ".obsidian",
    ".git",
    ".distill",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
}
KNOWLEDGE_DIR_NAMES = {"知识", "knowledge"}
OUTPUT_DIR_NAMES = {"输出", "output"}
OPS_DIR_NAMES = {"运维", "ops", ".distill"}
SYSTEM_DIR_NAMES = {"系统", "system"}
STRUCTURED_VAULT_DIR_NAMES = KNOWLEDGE_DIR_NAMES | OUTPUT_DIR_NAMES | OPS_DIR_NAMES | SYSTEM_DIR_NAMES
ROOT_DISCOVERY_IGNORED_FILENAMES = {"README.md", "readme.md", "AGENTS.md", "CLAUDE.md", "SKILL.md"}


def _iter_markdown_files(vault_root: Path):
    vault_root = Path(vault_root)
    for path in vault_root.rglob("*.md"):
        rel_parts = path.relative_to(vault_root).parts
        parent_parts = rel_parts[:-1]
        if any(part in IGNORED_DISCOVERY_DIRS for part in parent_parts):
            continue
        yield path


def looks_like_obsidian_vault(vault_root: Path, *, allow_markdown_fallback: bool = False) -> bool:
    vault_root = Path(vault_root)
    if not vault_root.exists() or not vault_root.is_dir():
        return False
    if (vault_root / ".obsidian").exists():
        return True
    if (vault_root / "distill.yaml").exists():
        return True
    if (vault_root / "知识").exists() or (vault_root / "knowledge").exists():
        return True
    if not allow_markdown_fallback:
        return False
    return any(
        len(path.relative_to(vault_root).parts) > 1 or path.name not in ROOT_DISCOVERY_IGNORED_FILENAMES
        for path in _iter_markdown_files(vault_root)
    )


def infer_existing_vault_config(vault_root: Path) -> dict:
    vault_root = Path(vault_root)
    config = deepcopy(DEFAULT_CONFIG)

    root_has_markdown = False
    top_level_dirs: set[str] = set()
    for path in _iter_markdown_files(vault_root):
        rel_parts = path.relative_to(vault_root).parts
        if len(rel_parts) == 1:
            if path.name not in ROOT_DISCOVERY_IGNORED_FILENAMES:
                root_has_markdown = True
            continue
        top_level_dirs.add(rel_parts[0])

    has_structured_dirs = any(rel_dir in STRUCTURED_VAULT_DIR_NAMES for rel_dir in top_level_dirs)
    if has_structured_dirs:
        config["vault"]["knowledge_dirs"] = sorted(rel_dir for rel_dir in top_level_dirs if rel_dir in KNOWLEDGE_DIR_NAMES)
        config["vault"]["output_dirs"] = sorted(rel_dir for rel_dir in top_level_dirs if rel_dir in OUTPUT_DIR_NAMES)
        config["vault"]["system_dirs"] = sorted(rel_dir for rel_dir in top_level_dirs if rel_dir in SYSTEM_DIR_NAMES)
        inferred_ops = sorted(rel_dir for rel_dir in top_level_dirs if rel_dir in OPS_DIR_NAMES)
        config["vault"]["ops_dirs"] = inferred_ops or [".distill"]
        return config

    if root_has_markdown:
        config["vault"]["knowledge_dirs"] = ["."]
        config["vault"]["output_dirs"] = []
        config["vault"]["system_dirs"] = []
        config["vault"]["ops_dirs"] = [".distill"]
        return config

    knowledge_dirs: list[str] = []
    output_dirs: list[str] = []
    system_dirs: list[str] = []
    ops_dirs: list[str] = []

    for rel_dir in sorted(top_level_dirs):
        if rel_dir in OUTPUT_DIR_NAMES:
            output_dirs.append(rel_dir)
        elif rel_dir in SYSTEM_DIR_NAMES:
            system_dirs.append(rel_dir)
        elif rel_dir in OPS_DIR_NAMES:
            ops_dirs.append(rel_dir)
        else:
            knowledge_dirs.append(rel_dir)

    if knowledge_dirs:
        config["vault"]["knowledge_dirs"] = knowledge_dirs
    else:
        config["vault"]["knowledge_dirs"] = []
    config["vault"]["output_dirs"] = output_dirs
    config["vault"]["system_dirs"] = system_dirs
    config["vault"]["ops_dirs"] = ops_dirs or [".distill"]
    return config


_IGNORED_INFER_DIRS = {
    ".obsidian",
    ".git",
    ".distill",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
}

_IGNORED_ROOT_MARKDOWN = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "SKILL.md",
}

_CANONICAL_LAYOUT = {
    "knowledge_dirs": ["知识", "knowledge"],
    "output_dirs": ["输出", "output"],
    "ops_dirs": ["运维", "ops"],
    "system_dirs": ["系统", "system"],
}


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Deep-merge two dictionaries, preferring override values."""
    merged = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_user_config(user_config: dict) -> dict:
    normalized = deepcopy(user_config)
    vault_cfg = dict(normalized.get("vault", {}) or {})

    legacy_map = {
        "knowledge_dir": "knowledge_dirs",
        "output_dir": "output_dirs",
        "ops_dir": "ops_dirs",
        "system_dir": "system_dirs",
    }
    for old_key, new_key in legacy_map.items():
        if old_key in vault_cfg and new_key not in vault_cfg:
            vault_cfg[new_key] = _as_list(vault_cfg.pop(old_key))

    for key in ("knowledge_dirs", "output_dirs", "ops_dirs", "system_dirs"):
        if key in vault_cfg:
            vault_cfg[key] = _as_list(vault_cfg[key])

    normalized["vault"] = vault_cfg
    return normalized


def _first_existing_dir(vault_root: Path, candidates: list[str]) -> str | None:
    for rel_dir in candidates:
        path = vault_root / rel_dir
        if path.exists() and path.is_dir():
            return rel_dir
    return None


def _dir_contains_markdown(path: Path) -> bool:
    return any(path.rglob("*.md"))


def _has_meaningful_root_markdown(vault_root: Path) -> bool:
    for md_path in vault_root.glob("*.md"):
        if md_path.name not in _IGNORED_ROOT_MARKDOWN:
            return True
    return False


def infer_existing_vault_config(vault_root: Path) -> dict:
    """Infer conservative scan roots for an existing Obsidian vault."""
    vault_root = Path(vault_root)

    canonical = {
        key: _first_existing_dir(vault_root, candidates)
        for key, candidates in _CANONICAL_LAYOUT.items()
    }

    if canonical["knowledge_dirs"] or canonical["output_dirs"] or canonical["ops_dirs"] or canonical["system_dirs"]:
        knowledge_dirs = [canonical["knowledge_dirs"]] if canonical["knowledge_dirs"] else []
        if not knowledge_dirs and _has_meaningful_root_markdown(vault_root):
            knowledge_dirs = ["."]
        return {
            "vault": {
                "knowledge_dirs": knowledge_dirs,
                "output_dirs": [canonical["output_dirs"]] if canonical["output_dirs"] else [],
                "ops_dirs": [canonical["ops_dirs"]] if canonical["ops_dirs"] else [".distill"],
                "system_dirs": [canonical["system_dirs"]] if canonical["system_dirs"] else [],
            }
        }

    markdown_dirs: list[str] = []
    for child in sorted(vault_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if child.name in _IGNORED_INFER_DIRS:
            continue
        if _dir_contains_markdown(child):
            markdown_dirs.append(child.name)

    if _has_meaningful_root_markdown(vault_root):
        knowledge_dirs = ["."]
    else:
        knowledge_dirs = markdown_dirs

    return {
        "vault": {
            "knowledge_dirs": knowledge_dirs,
            "output_dirs": [],
            "ops_dirs": [".distill"],
            "system_dirs": [],
        }
    }


def load_config(vault_root: Path) -> dict:
    """Load distill.yaml and deep-merge it with defaults."""
    vault_root = Path(vault_root)
    config = deepcopy(DEFAULT_CONFIG)
    config_path = vault_root / "distill.yaml"

    if not config_path.exists():
        if (
            (vault_root / "知识").exists()
            or (vault_root / "knowledge").exists()
            or (vault_root / "输出").exists()
            or (vault_root / "output").exists()
            or (vault_root / "系统").exists()
            or (vault_root / "system").exists()
            or (vault_root / "运维").exists()
            or (vault_root / "ops").exists()
        ):
            return config
        if looks_like_obsidian_vault(vault_root, allow_markdown_fallback=True):
            return _deep_merge(config, infer_existing_vault_config(vault_root))
        return config

    with config_path.open("r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}

    if not isinstance(user_config, dict):
        raise ValueError("distill.yaml must contain a top-level mapping")

    return _deep_merge(config, _normalize_user_config(user_config))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def get_scan_dirs(config: dict, vault_root: Path) -> list[Path]:
    """Return all configured existing directories to scan, deduplicated by ancestry."""
    vault_root = Path(vault_root)
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _add_existing_dirs(vault_cfg: dict) -> None:
        for section in ("knowledge_dirs", "output_dirs", "ops_dirs", "system_dirs"):
            for rel_dir in vault_cfg.get(section, []):
                path = (vault_root / rel_dir).resolve()
                if path.exists() and path.is_dir() and path not in seen:
                    seen.add(path)
                    candidates.append(path)

    _add_existing_dirs(config.get("vault", {}))

    if not candidates:
        inferred = infer_existing_vault_config(vault_root)
        _add_existing_dirs(inferred.get("vault", {}))

    drop: set[int] = set()
    for idx, path in enumerate(candidates):
        for other_idx, other in enumerate(candidates):
            if idx == other_idx:
                continue
            if _is_relative_to(other, path):
                drop.add(other_idx)

    return [path for idx, path in enumerate(candidates) if idx not in drop]


def get_ops_dir(config: dict, vault_root: Path) -> Path:
    """Return the preferred ops directory, using the first existing one or a safe default."""
    vault_root = Path(vault_root)
    ops_dirs = config.get("vault", {}).get("ops_dirs", [])

    for rel_dir in ops_dirs:
        path = vault_root / rel_dir
        if path.exists() and path.is_dir():
            return path

    if ops_dirs:
        return vault_root / ops_dirs[0]

    legacy_state = vault_root / ".distill"
    if legacy_state.exists() and legacy_state.is_dir():
        return legacy_state

    return vault_root / "ops"


def resolve_path_type(path: str, config: dict) -> str:
    """Resolve object type from configured path prefixes."""
    normalized_path = path.replace("\\", "/")
    path_type_map = config.get("objects", {}).get("path_type_map", {})

    for prefix in sorted(path_type_map, key=len, reverse=True):
        if normalized_path.startswith(prefix):
            return path_type_map[prefix]

    return "unknown"


def resolve_type_status(obj_type: str, config: dict) -> str:
    """Resolve default status for an object type."""
    return config.get("objects", {}).get("type_status_map", {}).get(obj_type, "unknown")
