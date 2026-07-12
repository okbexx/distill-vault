"""Skill spec parsing and platform renderer support for distill-vault."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import hashlib
import re

import frontmatter

SUPPORTED_SKILL_TARGETS = ("hermes", "codex", "claude")
DEFAULT_INSTALL_DIRS = {
    "hermes": "~/.hermes/skills",
    "codex": "~/.codex/skills",
    "claude": "~/.claude/skills",
}


@dataclass
class SkillSpec:
    name: str
    title: str
    description: str
    triggers: list[str]
    purpose: str
    instruction_priority: list[str]
    workflow: list[str]
    verification_checklist: list[str]
    platform_notes: dict[str, str]
    path: Path
    lang: str
    raw_body: str


@dataclass
class SkillVerificationResult:
    target: str
    path: Path
    exists: bool
    matches: bool
    expected_sha256: str
    actual_sha256: str | None

    @property
    def status(self) -> str:
        if not self.exists:
            return "missing"
        if not self.matches:
            return "drift"
        return "ok"


def verification_result_payload(skill_name: str, result: SkillVerificationResult) -> dict:
    return {
        "skill": skill_name,
        "target": result.target,
        "status": result.status,
        "path": str(result.path),
        "exists": result.exists,
        "matches": result.matches,
        "expected_sha256": result.expected_sha256,
        "actual_sha256": result.actual_sha256,
    }


def doctor_payload(skill_name: str, results: list[SkillVerificationResult]) -> dict:
    targets = [verification_result_payload(skill_name, item) for item in results]
    summary = {"ok": 0, "drift": 0, "missing": 0}
    for item in results:
        summary[item.status] += 1
    return {
        "skill": skill_name,
        "summary": summary,
        "targets": targets,
    }


def verify_many_payload(skill_name: str, results: list[SkillVerificationResult]) -> dict:
    return {
        "skill": skill_name,
        "mode": "verify",
        "results": [verification_result_payload(skill_name, item) for item in results],
    }


@dataclass
class SkillReconcileResult:
    skill: str
    target: str
    path: Path
    before: SkillVerificationResult
    after: SkillVerificationResult
    action: str
    changed: bool


def reconcile_result_payload(result: SkillReconcileResult) -> dict:
    payload = {
        "skill": result.skill,
        "target": result.target,
        "path": str(result.path),
        "action": result.action,
        "changed": result.changed,
        "before": verification_result_payload(result.skill, result.before),
    }
    if result.changed:
        payload["after"] = verification_result_payload(result.skill, result.after)
    else:
        payload["desired_after"] = verification_result_payload(result.skill, result.after)
    return payload


LANG_SKILL_SPECS = {
    "zh": {
        "skills_dir": "技能",
        "readme_title": "# 技能规范",
        "readme_body": "这里存放 distill 的 canonical skill specs。平台产物应由 distill skill export 生成，而不是手写镜像。",
        "sample_name": "vault-distill-ops",
        "sample_title": "Vault Distill Ops",
        "sample_description": "用于指导 AI agent 如何安全、一致地在 distill vault 中工作。",
        "sample_triggers": [
            "用户要求查看、更新、维护 distill vault",
            "需要在知识库内执行 lint / run / health / export 等操作",
            "用户要求向 vault 记录、写入、投影内容（如'记到知识库''录一下''记住'）",
            "执行知识库 ingest / projection 操作",
        ],
        "sample_purpose": "确保 agent 在操作 vault 时遵守 distill 驱动、先校验后修改、修改后复核的统一契约。包括查询、写入、投影在内的所有 vault 操作都必须走 distill-first 流程：先查重（distill search）再动手，改完跑验证。",
        "sample_instruction_priority": [
            "优先遵守 vault 内已有规范与运行时文档",
            "所有操作（包括写入/投影）前先用 distill search 查重，不能用 ripgrep/grep 代替",
            "所有结构性修改前先获取 vault 上下文与健康状态",
            "所有修改后必须重新运行 distill 验证",
        ],
        "sample_workflow": [
            "进入 vault 前先确认仓库是最新状态（git pull），并识别 distill.yaml 与关键目录。",
            "写入/投影前必须先执行 distill search 查重，确认是否存在同名对象、别名或间接引用。distill search 是知识图谱级别查重，ripgrep 只是文本搜索，两者不可互相替代。",
            "查看 distill status / lint / run 所需上下文，再决定内容修改还是运行时修复。",
            "优先通过 distill 的内建命令验证，不要只靠主观判断。",
            "项目更新进入 Project Handbook 的已验证事实；概念、决策和约束必须呈现来源、验证、复用、复利与演化状态。",
            "完成修改后重新执行 distill run + lint，并汇总真实结果。",
        ],
        "sample_verification": [
            "确认当前 vault 可被 distill 正常识别",
            "确认写入前已通过 distill search 完成查重，无重复对象",
            "确认修改后 lint / run / health 输出符合预期",
            "确认没有引入新的 broken links 或结构性问题",
            "确认 Project Handbook 或 Knowledge Compounding 页面契约完整",
        ],
        "sample_platform_notes": {
            "hermes": "导出为 Hermes SKILL.md，可直接放入 ~/.hermes/skills/<name>/SKILL.md",
            "codex": "导出为 Codex skill 文档，保持运行时指导完整自包含",
            "claude": "导出为 Claude Code skill 文档，供运行时直接消费",
        },
        "sections": {
            "triggers": "触发条件",
            "purpose": "目标",
            "instruction_priority": "指令优先级",
            "workflow": "工作流",
            "verification_checklist": "验证清单",
            "platform_notes": "平台说明",
        },
    },
    "en": {
        "skills_dir": "skills",
        "readme_title": "# Skill Specs",
        "readme_body": "This directory stores canonical distill skill specs. Platform outputs should be generated via distill skill export instead of copied by hand.",
        "sample_name": "vault-distill-ops",
        "sample_title": "Vault Distill Ops",
        "sample_description": "Guide AI agents to operate safely and consistently inside a distill-managed vault.",
        "sample_triggers": [
            "The user asks to inspect, update, or maintain a distill vault",
            "The task requires lint / run / health / export operations inside the vault",
            "The user asks to record, write, or project content into the vault (e.g. 'remember this', 'save to knowledge base', 'record it')",
            "Performing vault ingest / projection operations",
        ],
        "sample_purpose": "Ensure the agent follows a distill-first workflow: inspect before editing, deduplicate before writing, validate after changes, and preserve vault semantics. All vault operations—including writes and projections—must go through distill search for deduplication first, then verification after.",
        "sample_instruction_priority": [
            "Respect vault-native runtime and specification docs first",
            "Always run distill search for deduplication before any write/projection—never substitute with ripgrep/grep",
            "Gather vault health and structure context before structural changes",
            "Re-run distill verification after every material modification",
        ],
        "sample_workflow": [
            "Confirm the repo is up to date (git pull) and locate distill.yaml plus key directories.",
            "Before any write or projection, run distill search to check for existing objects, aliases, or indirect references. distill search is graph-level deduplication; ripgrep is text-only search—they are not interchangeable.",
            "Review status/lint/run context before deciding whether the issue is content-level or runtime-level.",
            "Use distill commands as the primary source of truth instead of intuition.",
            "Write project updates into Project Handbook verified facts; make sources, validation, reuse, compounding, and evolution visible for concepts, decisions, and constraints.",
            "After changes, re-run distill run + lint and report the grounded results.",
        ],
        "sample_verification": [
            "Verify the vault is discoverable by distill",
            "Verify distill search was run before writing and no duplicate objects exist",
            "Verify lint / run / health output after the change",
            "Verify no new broken links or structural regressions were introduced",
            "Verify the Project Handbook or Knowledge Compounding presentation contract is complete",
        ],
        "sample_platform_notes": {
            "hermes": "Render as a Hermes SKILL.md artifact for ~/.hermes/skills/<name>/SKILL.md",
            "codex": "Render as a Codex skill artifact with self-contained runtime guidance",
            "claude": "Render as a Claude Code skill artifact for runtime consumption",
        },
        "sections": {
            "triggers": "Triggers",
            "purpose": "Purpose",
            "instruction_priority": "Instruction Priority",
            "workflow": "Workflow",
            "verification_checklist": "Verification Checklist",
            "platform_notes": "Platform Notes",
        },
    },
}


def build_skill_scaffold(lang: str) -> dict[str, str]:
    spec = LANG_SKILL_SPECS[lang]
    sample_name = spec["sample_name"]
    return {
        "README.md": f"{spec['readme_title']}\n\n{spec['readme_body']}\n",
        f"{sample_name}.md": _build_sample_skill_spec(lang),
    }


def _build_sample_skill_spec(lang: str) -> str:
    spec = LANG_SKILL_SPECS[lang]
    lines = [
        "---",
        "type: skill_spec",
        "status: active",
        f"name: {spec['sample_name']}",
        f'title: "{spec["sample_title"]}"',
        f'description: "{spec["sample_description"]}"',
        f"lang: {lang}",
        "triggers:",
    ]
    lines.extend(f"  - {item}" for item in spec["sample_triggers"])
    lines.extend([
        f'purpose: "{spec["sample_purpose"]}"',
        "instruction_priority:",
    ])
    lines.extend(f"  - {item}" for item in spec["sample_instruction_priority"])
    lines.extend([
        "verification_checklist:",
    ])
    lines.extend(f"  - {item}" for item in spec["sample_verification"])
    lines.extend([
        "platform_notes:",
    ])
    for platform, note in spec["sample_platform_notes"].items():
        lines.append(f"  {platform}: {note}")
    lines.extend([
        "---",
        "",
        f"# {spec['sample_title']}",
        "",
        f"## {spec['sections']['triggers']}",
        "",
    ])
    lines.extend(f"- {item}" for item in spec["sample_triggers"])
    lines.extend([
        "",
        f"## {spec['sections']['purpose']}",
        "",
        spec["sample_purpose"],
        "",
        f"## {spec['sections']['instruction_priority']}",
        "",
    ])
    lines.extend(f"1. {item}" for item in spec["sample_instruction_priority"])
    lines.extend([
        "",
        f"## {spec['sections']['workflow']}",
        "",
    ])
    lines.extend(f"1. {item}" for item in spec["sample_workflow"])
    lines.extend([
        "",
        f"## {spec['sections']['verification_checklist']}",
        "",
    ])
    lines.extend(f"- {item}" for item in spec["sample_verification"])
    lines.extend([
        "",
        f"## {spec['sections']['platform_notes']}",
        "",
    ])
    lines.extend(f"- **{platform}**: {note}" for platform, note in spec["sample_platform_notes"].items())
    lines.append("")
    return "\n".join(lines)


def discover_skill_specs(vault_root: Path) -> list[SkillSpec]:
    candidates = []
    for lang, lang_spec in LANG_SKILL_SPECS.items():
        skills_dir = _skill_dir(vault_root, lang)
        if not skills_dir.exists():
            continue
        for path in sorted(skills_dir.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            post = frontmatter.load(path)
            if post.metadata.get("type") != "skill_spec":
                continue
            candidates.append(_to_skill_spec(path, post, lang))
    return candidates


def get_skill_spec(vault_root: Path, name: str) -> SkillSpec:
    for spec in discover_skill_specs(vault_root):
        if spec.name == name:
            return spec
    raise FileNotFoundError(f"Skill spec '{name}' not found")


def render_skill(spec: SkillSpec, target: str) -> str:
    target = target.lower()
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    dispatch = {
        "hermes": _render_hermes,
        "codex": _render_codex,
        "claude": _render_claude,
    }
    return dispatch[target](spec)


def _localized_headings(lang: str) -> dict[str, str]:
    return {
        "zh": {
            "when": "适用场景",
            "purpose": "目标",
            "priority": "指令优先级",
            "workflow": "工作流",
            "verification": "验证清单",
            "platform_notes": "平台说明",
        },
        "en": {
            "when": "When to Use",
            "purpose": "Purpose",
            "priority": "Instruction Priority",
            "workflow": "Workflow",
            "verification": "Verification Checklist",
            "platform_notes": "Platform Notes",
        },
    }[lang]


def _render_hermes(spec: SkillSpec) -> str:
    """Hermes SKILL.md: YAML frontmatter + localized markdown sections."""
    headings = _localized_headings(spec.lang)
    lines = [
        "---",
        f"name: {spec.name}",
        f'description: "{spec.description}"',
        "version: 1.0.0",
        "author: distill-vault",
        "license: MIT",
        "---",
        "",
        f"# {spec.title}",
        "",
        f"## {headings['when']}",
        "",
    ]
    lines.extend(f"- {item}" for item in spec.triggers)
    lines.extend([
        "",
        f"## {headings['purpose']}",
        "",
        spec.purpose,
        "",
        f"## {headings['priority']}",
        "",
    ])
    lines.extend(f"1. {item}" for item in spec.instruction_priority)
    lines.extend([
        "",
        f"## {headings['workflow']}",
        "",
    ])
    lines.extend(f"1. {item}" for item in spec.workflow)
    lines.extend([
        "",
        f"## {headings['verification']}",
        "",
    ])
    lines.extend(f"- {item}" for item in spec.verification_checklist)
    lines.extend([
        "",
        f"## {headings['platform_notes']}",
        "",
    ])
    lines.extend(f"- **{platform}**: {note}" for platform, note in spec.platform_notes.items())
    lines.append("")
    return "\n".join(lines)


def _render_codex(spec: SkillSpec) -> str:
    """Codex instruction markdown: no frontmatter, instruction-first style."""
    lines = [
        f"# {spec.title}",
        "",
        f"<!-- Codex skill: {spec.name} -->",
        "",
        f"{spec.description}",
        "",
        "## When to Use",
        "",
    ]
    lines.extend(f"- {item}" for item in spec.triggers)
    lines.extend([
        "",
        "## Instructions",
        "",
        spec.purpose,
        "",
    ])
    lines.extend(f"1. {item}" for item in spec.instruction_priority)
    lines.extend([
        "",
        "## Workflow",
        "",
    ])
    lines.extend(f"1. {item}" for item in spec.workflow)
    lines.extend([
        "",
        "## Verification",
        "",
    ])
    lines.extend(f"- {item}" for item in spec.verification_checklist)
    lines.extend([
        "",
        "## Platform Notes",
        "",
    ])
    lines.extend(f"- **{platform}**: {note}" for platform, note in spec.platform_notes.items())
    lines.append("")
    return "\n".join(lines)


def _render_claude(spec: SkillSpec) -> str:
    """Claude Code instruction: @-metadata comments + concise numbered rules."""
    lines = [
        f"<!-- @name {spec.name} -->",
        f"<!-- @description {spec.description} -->",
        "",
        f"# {spec.title}",
        "",
        "## Triggers",
        "",
    ]
    lines.extend(f"- {item}" for item in spec.triggers)
    lines.extend([
        "",
        "## Purpose",
        "",
        spec.purpose,
        "",
        "## Rules",
        "",
    ])
    lines.extend(f"{i+1}. {item}" for i, item in enumerate(spec.instruction_priority))
    lines.extend([
        "",
        "## Workflow",
        "",
    ])
    lines.extend(f"{i+1}. {item}" for i, item in enumerate(spec.workflow))
    lines.extend([
        "",
        "## Checklist",
        "",
    ])
    lines.extend(f"- {item}" for item in spec.verification_checklist)
    lines.extend([
        "",
        "## Platform Notes",
        "",
    ])
    lines.extend(f"- **{platform}**: {note}" for platform, note in spec.platform_notes.items())
    lines.append("")
    return "\n".join(lines)


def export_skill(spec: SkillSpec, target: str, output_dir: Path) -> Path:
    target = target.lower()
    content = render_skill(spec, target)
    skill_dir = output_dir / target / spec.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    output_path = skill_dir / "SKILL.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def install_skill(spec: SkillSpec, target: str, target_dir: Path | None = None) -> Path:
    target = target.lower()
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    base_dir = target_dir.expanduser() if target_dir is not None else Path(DEFAULT_INSTALL_DIRS[target]).expanduser()
    skill_dir = base_dir / spec.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    output_path = skill_dir / "SKILL.md"
    output_path.write_text(render_skill(spec, target), encoding="utf-8")
    return output_path


def verify_installed_skill(spec: SkillSpec, target: str, target_dir: Path | None = None) -> SkillVerificationResult:
    target = target.lower()
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    base_dir = target_dir.expanduser() if target_dir is not None else Path(DEFAULT_INSTALL_DIRS[target]).expanduser()
    skill_path = base_dir / spec.name / "SKILL.md"
    expected = render_skill(spec, target)
    expected_sha256 = _sha256_text(expected)
    if not skill_path.exists():
        return SkillVerificationResult(
            target=target,
            path=skill_path,
            exists=False,
            matches=False,
            expected_sha256=expected_sha256,
            actual_sha256=None,
        )
    actual = skill_path.read_text(encoding="utf-8")
    actual_sha256 = _sha256_text(actual)
    return SkillVerificationResult(
        target=target,
        path=skill_path,
        exists=True,
        matches=actual == expected,
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
    )


def reconcile_installed_skill(spec: SkillSpec, target: str, target_dir: Path | None = None, dry_run: bool = False) -> SkillReconcileResult:
    before = verify_installed_skill(spec, target, target_dir=target_dir)
    target = target.lower()
    if not before.exists:
        action = "install" if dry_run else "installed"
        changed = not dry_run
        if not dry_run:
            path = install_skill(spec, target, target_dir=target_dir)
            after = verify_installed_skill(spec, target, target_dir=target_dir)
            return SkillReconcileResult(
                skill=spec.name,
                target=target,
                path=path,
                before=before,
                after=after,
                action=action,
                changed=changed,
            )
        path = before.path
        after = SkillVerificationResult(
            target=target,
            path=path,
            exists=True,
            matches=True,
            expected_sha256=before.expected_sha256,
            actual_sha256=before.expected_sha256,
        )
        return SkillReconcileResult(
            skill=spec.name,
            target=target,
            path=path,
            before=before,
            after=after,
            action=action,
            changed=changed,
        )

    if before.matches:
        return SkillReconcileResult(
            skill=spec.name,
            target=target,
            path=before.path,
            before=before,
            after=before,
            action="noop",
            changed=False,
        )

    action = "update" if dry_run else "updated"
    changed = not dry_run
    if not dry_run:
        path = install_skill(spec, target, target_dir=target_dir)
        after = verify_installed_skill(spec, target, target_dir=target_dir)
        return SkillReconcileResult(
            skill=spec.name,
            target=target,
            path=path,
            before=before,
            after=after,
            action=action,
            changed=changed,
        )
    after = SkillVerificationResult(
        target=target,
        path=before.path,
        exists=True,
        matches=True,
        expected_sha256=before.expected_sha256,
        actual_sha256=before.expected_sha256,
    )
    return SkillReconcileResult(
        skill=spec.name,
        target=target,
        path=before.path,
        before=before,
        after=after,
        action=action,
        changed=changed,
    )


def export_targets(target: str) -> Iterable[str]:
    if target == "all":
        return SUPPORTED_SKILL_TARGETS
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    return (target,)


def _skill_dir(vault_root: Path, lang: str) -> Path:
    system_dir = "系统" if lang == "zh" else "system"
    return vault_root / system_dir / LANG_SKILL_SPECS[lang]["skills_dir"]


def _to_skill_spec(path: Path, post: frontmatter.Post, lang: str) -> SkillSpec:
    return SkillSpec(
        name=post.metadata["name"],
        title=post.metadata["title"],
        description=post.metadata["description"],
        triggers=list(post.metadata.get("triggers", [])),
        purpose=post.metadata.get("purpose", ""),
        instruction_priority=list(post.metadata.get("instruction_priority", [])),
        workflow=_extract_section_list(post.content, LANG_SKILL_SPECS[lang]["sections"]["workflow"]),
        verification_checklist=list(post.metadata.get("verification_checklist", [])),
        platform_notes=dict(post.metadata.get("platform_notes", {})),
        path=path,
        lang=lang,
        raw_body=post.content,
    )


def _extract_section_list(body: str, heading: str) -> list[str]:
    lines = body.splitlines()
    in_section = False
    items: list[str] = []
    heading_pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$")
    bullet_pattern = re.compile(r"^(?:[-*]|\d+[.)])\s+(.*)$")
    for line in lines:
        stripped = line.strip()
        if heading_pattern.match(stripped):
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section:
            match = bullet_pattern.match(stripped)
            if match:
                items.append(match.group(1))
    return items


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
