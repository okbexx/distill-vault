"""Shared vault parsing and link resolution semantics.

Centralizes wikilink extraction and link resolution so index, graph, and
pipeline flows stay consistent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
H2_RE = re.compile(r"^##[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
PROJECT_PRESENTATION = "project-handbook-v1"
KNOWLEDGE_PRESENTATION = "knowledge-compounding-v1"
PRESENTATION_SECTIONS = {
    PROJECT_PRESENTATION: {
        "zh": ("一页结论", "资产与系统地图", "如何使用或运行", "配置与访问", "已验证事实", "决策与约束", "验证与证据"),
        "en": ("At a Glance", "Asset and System Map", "How to Use or Run", "Configuration and Access", "Verified Facts", "Decisions and Constraints", "Validation and Evidence"),
    },
    KNOWLEDGE_PRESENTATION: {
        "zh": ("一句话结论", "知识生命周期", "适用与复用", "证据与演化"),
        "en": ("One-sentence Conclusion", "Knowledge Lifecycle", "Application and Reuse", "Evidence and Evolution"),
    },
}
PSEUDO_LINK_PREFIXES = (
    "GitHub:",
    "npm:",
    "官网:",
    "源码:",
    "站点:",
    "报告:",
    "横评:",
    "学习卡片:",
)
OBSIDIAN_ATTACHMENT_EXTENSIONS = (
    ".html",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".ogg",
    ".pptx",
    ".docx",
    ".xlsx",
    ".zip",
)
OBSIDIAN_VIEW_EXTENSIONS = (".base",)
SYSTEM_DOC_PATH_PREFIXES = (
    "系统/规范/",
    "系统/技能/",
    "系统/运行时/",
    "system/spec/",
    "system/skills/",
    "system/runtime/",
)
SYSTEM_DOC_FILENAMES = (
    "AGENTS.md",
    "CLAUDE.md",
    "SKILL.md",
)
IGNORED_BROKEN_LINK_PREFIXES = (
    "兼容层/",
    "运维/",
    *PSEUDO_LINK_PREFIXES,
)
FRONTMATTER_RELATION_FIELDS = [
    "projects",
    "concepts",
    "entities",
    "sources",
    "outputs",
    "key_outputs",
    "related_projects",
    "related_concepts",
    "related_entities",
    "related_sources",
    "related_outputs",
    "source_basis",
    "decisions",
    "constraints",
]
FRONTMATTER_EDGE_TYPES = {
    "concepts": "has_concept",
    "projects": "has_project",
    "entities": "has_entity",
    "decisions": "has_decision",
    "constraints": "has_constraint",
    "key_outputs": "has_key_output",
    "source_basis": "source_basis",
}


def is_raw_source(metadata) -> bool:
    """Raw evidence has no curated body edges (explicit relations still count)."""
    return metadata.get("type") == "source" and metadata.get("status") == "raw"


def is_plain_inbox_source(path: str, metadata, root: Path, config: dict) -> bool:
    """Only an explicitly configured inbox opts unclassified notes into raw."""
    configured = config.get("capture", {}).get("source_dir")
    if not configured:
        return False
    inbox = root / str(configured)
    resolved = inbox.resolve()
    # A symlinked or out-of-vault inbox must not widen the evidence boundary.
    if not resolved.is_relative_to(root) or resolved != inbox.absolute():
        return False
    candidate = root / path
    if not candidate.resolve().is_relative_to(resolved):
        return False
    return (metadata.get("type") in (None, "", "unknown", "source")
            and metadata.get("status") in (None, "", "unknown", "raw"))


def source_attachment_owners(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """Resolve explicit sibling manifests, with a narrow old-writer fallback.

    No directory-wide exemptions, arbitrary Markdown links, traversal or symlinks.
    Legacy recognition requires the writer UUID/id, original.txt and exact numbered
    Attachment links. An explicit (even empty) manifest disables legacy fallback.
    """
    import frontmatter
    from urllib.parse import unquote

    owners = {}
    parents = {Path(path).parent for path in paths}
    for parent in sorted(parents):
        directory = root / parent
        source = directory / "source.md"
        if directory.resolve() != directory.absolute() or not directory.resolve().is_relative_to(root):
            continue
        if not source.is_file() or source.is_symlink():
            continue
        try:
            post = frontmatter.load(source)
        except Exception:
            continue
        if not is_raw_source(post.metadata):
            continue
        names = post.metadata.get("attachments")
        if "attachments" not in post.metadata:
            if (not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{32}", parent.name)
                    or post.get("id") != "source-" + parent.name
                    or not (directory / "original.txt").is_file()
                    or (directory / "original.txt").is_symlink()):
                continue
            names = [unquote(name) for name in re.findall(r"^\[Attachment\]\(([^\n]+)\)$", post.content, re.MULTILINE)]
        if not isinstance(names, list):
            continue
        for name in names:
            if (not isinstance(name, str) or not re.fullmatch(r"[1-9][0-9]*-[^/\\\n]+", name)
                    or Path(name).name != name):
                continue
            candidate = directory / name
            if not candidate.is_file() or candidate.is_symlink() or candidate.resolve() != candidate.absolute():
                continue
            owners[candidate.relative_to(root).as_posix()] = source.relative_to(root).as_posix()
    return owners


def listify(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_wikilinks(text: str | None) -> list[str]:
    if not text:
        return []
    return [normalize_wikilink_target(link) for link in WIKILINK_RE.findall(text)]


def extract_h2_headings(text: str | None) -> set[str]:
    """Return exact level-two Markdown headings without matching level three."""
    return {match.group("title").strip() for match in H2_RE.finditer(text or "")}


def extract_frontmatter_links(
    metadata: dict | None,
    relation_fields: Iterable[str] | None = None,
    *,
    include_plain_strings: bool = False,
) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    fields = list(relation_fields or FRONTMATTER_RELATION_FIELDS)
    links: list[str] = []
    for key in fields:
        for item in _flatten(listify(metadata.get(key))):
            if not isinstance(item, str):
                continue
            extracted = extract_wikilinks(item)
            if extracted:
                links.extend(extracted)
            elif include_plain_strings and _is_plain_relation_candidate(item):
                links.append(item.strip())
    return links


def normalize_wikilink_target(link: str | None) -> str:
    if not isinstance(link, str):
        return ""
    target = link.split("|", 1)[0].strip()
    return target


def is_pseudo_link(link: str | None) -> bool:
    target = normalize_wikilink_target(link)
    return any(target.startswith(prefix) for prefix in PSEUDO_LINK_PREFIXES)


def _is_plain_relation_candidate(value: str) -> bool:
    target = value.strip()
    if not target or is_pseudo_link(target):
        return False
    if target.startswith(("http://", "https://", "/", "~/")):
        return False
    if "。" in target or "\n" in target:
        return False
    return True


def should_ignore_broken_link(link: str | None) -> bool:
    target = normalize_wikilink_target(link)
    if any(target.startswith(prefix) for prefix in IGNORED_BROKEN_LINK_PREFIXES):
        return True
    lowered = target.lower()
    return any(lowered.endswith(ext) for ext in OBSIDIAN_ATTACHMENT_EXTENSIONS)


def resolve_existing_vault_asset(link: str | None, vault_root: Path | str) -> str | None:
    """Resolve supported Obsidian assets that are intentionally not graph objects."""
    target = normalize_wikilink_target(link)
    if not target or not target.lower().endswith(OBSIDIAN_VIEW_EXTENSIONS):
        return None

    root = Path(vault_root).expanduser().resolve()
    candidate = (root / target).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate.relative_to(root).as_posix()


def classify_orphan_path(path: str | None, frontmatter: dict | None = None) -> str:
    normalized = (path or "").replace("\\", "/")
    name = Path(normalized).name
    if any(normalized.startswith(prefix) for prefix in SYSTEM_DOC_PATH_PREFIXES):
        return "system_doc"
    if name in SYSTEM_DOC_FILENAMES:
        return "system_doc"
    metadata = frontmatter or {}
    if metadata.get("type") == "source" and metadata.get("status") == "raw":
        return "raw_inbox"
    if (
        metadata.get("type") == "output"
        and metadata.get("output_type") in {"log", "daily", "daily_log"}
    ):
        return "timeline_archive"
    return "true_orphan"


def build_lookup_indexes(objects: list[dict]) -> tuple[dict[str, dict], dict[str, str], dict[str, dict]]:
    path_index = {obj["path"]: obj for obj in objects}
    title_index = {obj["title"]: obj["path"] for obj in objects if obj.get("title")}
    filename_index: dict[str, dict] = {}
    for obj in objects:
        filename_index.setdefault(Path(obj["path"]).stem, obj)
    return path_index, title_index, filename_index


def resolve_link_target(
    link: str | None,
    *,
    path_index: dict[str, dict],
    title_index: dict[str, str],
    relation_prefixes: Iterable[str] | None = None,
    filename_index: dict[str, dict] | None = None,
) -> str | None:
    target = normalize_wikilink_target(link)
    if not target:
        return None

    if target in title_index:
        return title_index[target]

    candidate = target if target.endswith(".md") else f"{target}.md"
    if candidate in path_index:
        return candidate

    if "/" in target:
        for obj_path in path_index:
            if obj_path == candidate or obj_path.endswith(f"/{candidate}"):
                return obj_path

    if filename_index and target in filename_index:
        return filename_index[target]["path"]

    for prefix in relation_prefixes or []:
        full = f"{prefix}/{candidate}"
        if full in path_index:
            return full

    return None


def _flatten(values):
    for value in values:
        if isinstance(value, list):
            yield from _flatten(value)
        else:
            yield value
