"""Vault scaffolding for `distill init`."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

from .config import infer_existing_vault_config
from .skill_specs import build_skill_scaffold, LANG_SKILL_SPECS

DISTILL_RUNTIME_GITIGNORE_LINES = [
    "# distill-vault runtime artifacts",
    ".distill/runtime-state.json",
    ".distill/checkpoint.json",
    ".distill/distill.db*",
    ".distill/nodes.csv",
    ".distill/edges.csv",
]

OBJECT_TYPES = [
    "project",
    "concept",
    "entity",
    "source",
    "decision",
    "constraint",
    "analysis",
    "output",
    "note",
]

LANG_SPECS = {
    "zh": {
        "vault_comment": "# distill-vault 配置文件",
        "dirs": {
            "knowledge": "知识",
            "output": "输出",
            "ops": "运维",
            "system": "系统",
            "skills": "技能",
            "index": "索引",
            "health": "健康检查",
            "spec": "规范",
        },
        "object_dirs": {
            "project": "项目",
            "concept": "概念",
            "entity": "实体",
            "source": "来源",
            "decision": "决策",
            "constraint": "约束",
            "analysis": "分析",
        },
        "template_name": "_模板.md",
        "status": "active",
        "template_titles": {
            "project": "示例项目",
            "concept": "示例概念",
            "entity": "示例实体",
            "source": "示例来源",
            "decision": "示例决策",
            "constraint": "示例约束",
            "analysis": "示例分析",
        },
        "template_headings": {
            "project": "项目名称",
            "concept": "概念名称",
            "entity": "实体名称",
            "source": "来源标题",
            "decision": "决策标题",
            "constraint": "约束标题",
            "analysis": "分析标题",
        },
        "template_intro": {
            "project": "这是一个项目档案模板。在这里概括已经完成的成果、里程碑和证据...",
            "concept": "这是一个概念对象的模板。在这里解释核心概念、边界和适用场景...",
            "entity": "这是一个实体对象的模板。在这里记录关键实体、系统、组织或工具的信息...",
            "source": "这是一个来源对象的模板。在这里整理文献、文章、访谈或会议记录...",
            "decision": "这是一个决策对象的模板。在这里写明为什么做出这个决定，以及它的影响...",
            "constraint": "这是一个约束对象的模板。在这里说明不可违反的条件、限制或政策...",
            "analysis": "这是一个分析对象的模板。在这里沉淀推理过程、比较结论和下一步建议...",
        },
        "sections": {
            "project": ["一页结论", "资产与系统地图", "如何使用或运行", "配置与访问", "已验证事实", "决策与约束", "验证与证据"],
            "concept": ["一句话结论", "知识生命周期", "适用与复用", "证据与演化"],
            "entity": ["简介", "关键属性", "相关链接"],
            "source": ["摘要", "关键信息", "相关链接"],
            "decision": ["一句话结论", "知识生命周期", "适用与复用", "证据与演化"],
            "constraint": ["一句话结论", "知识生命周期", "适用与复用", "证据与演化"],
            "analysis": ["问题", "分析过程", "结论", "相关链接"],
        },
        "object_type_doc": """# 对象类型说明\n\nDistill 将知识库里的内容组织为 9 类对象。对象类型不是为了限制写作，而是为了让后续的索引、分析、检索和自动化处理更稳定。\n\n## 1. 项目（project）\n用于记录一个正在推进或已经完成的目标性工作，例如产品、课题、计划或行动流。项目对象通常包含目标、范围、里程碑、关键决策和相关成果。\n\n## 2. 概念（concept）\n用于解释一个抽象概念、方法论、术语或模型。概念对象强调定义、边界、适用条件以及它与其他概念的关系。\n\n## 3. 实体（entity）\n用于描述一个具体存在的对象，例如公司、团队、人物、软件、平台、数据库、模型或 API。实体对象适合承载关键属性、角色定位和上下游关系。\n\n## 4. 来源（source）\n用于承载外部材料或一手资料，例如文章、论文、会议纪要、访谈、播客、网页、截图摘要等。来源对象应该尽量保留出处、日期、摘要和可信度信息。\n\n## 5. 决策（decision）\n用于记录明确做出的选择以及原因。决策对象适合说明背景、备选方案、最终结论、影响范围，以及之后复盘时需要关注的假设。\n\n## 6. 约束（constraint）\n用于记录不可忽略的限制条件，例如预算、时间、政策、合规、性能、资源或组织边界。约束对象可以帮助系统理解为什么某些方案不可行。\n\n## 7. 分析（analysis）\n用于沉淀推理过程、比较过程、诊断结论或评估报告。分析对象强调“如何得出结论”，而不仅是结论本身。\n\n## 8. 输出（output）\n用于表示面向外部或面向执行的产物，例如报告、规范、提案、交付物、邮件草稿或发布材料。输出对象通常由多个知识对象投影而来。\n\n## 9. 笔记（note）\n用于容纳尚未归类的原始记录、临时想法或采集中间态内容。笔记对象可以作为后续提升（promote）和结构化整理的原料。\n\n## 使用建议\n- 每个对象尽量只承载一个核心主题。\n- 优先使用 wikilink（如 `[[对象名]]`）连接对象。\n- 在 frontmatter 中稳定填写 `type`、`status`、`title`、`tags`、`date`。\n- 当内容从零散记录逐步成熟时，可以从 note 演化为 concept、decision、analysis 或 output。\n""",
        "projection_doc": """# 投影规则\n\n投影（Projection）指的是：把自然语言笔记、来源材料或会议记录，转成更稳定、可索引、可引用的结构化对象。\n\n## 为什么需要投影\n原始笔记通常带有上下文噪声、时间性和个人写作习惯，不适合直接作为知识图谱里的稳定节点。通过投影，我们可以把高价值信息抽取出来，变成结构清晰的项目、概念、决策、约束、分析或输出。\n\n## 基本原则\n1. **一个对象一个核心主题**：不要把多个主题混在同一条对象里。\n2. **保留来源链路**：结构化对象应尽量链接回相关 `[[来源]]` 或 `[[笔记]]`。\n3. **显式表达关系**：用 wikilink 连接项目、概念、实体、决策和约束。\n4. **结论与过程分开**：结论适合进入 decision / output，推理过程适合进入 analysis。\n5. **稳定命名**：对象标题应尽量可复用、可搜索、可被其他对象引用。\n\n## 常见投影路径\n- 会议记录 / 阅读摘录 → `来源`\n- 原始想法 / 临时笔记 → `笔记`\n- 多条笔记汇总后的抽象定义 → `概念`\n- 围绕某项工作形成的持续页面 → `项目`\n- 对方案优劣的比较与推理 → `分析`\n- 已拍板的选择 → `决策`\n- 无法绕开的边界条件 → `约束`\n- 面向执行或分享的最终文档 → `输出`\n\n## 推荐步骤\n1. 先快速记录原始内容，不强求一开始就完全结构化。\n2. 识别其中的“事实、概念、选择、限制、结论”分别属于什么对象。\n3. 为每个稳定主题新建对象，并填入基础 frontmatter。\n4. 用 `[[wikilink]]` 把新对象连接到项目、来源和上下游概念。\n5. 将可执行结论沉淀为 output，将推理过程保留在 analysis。\n\n## 判断标准\n如果一条笔记满足以下至少两项，就值得投影为对象：\n- 会被多次引用\n- 会影响决策或执行\n- 需要与其他对象建立关系\n- 需要在后续搜索或自动化中稳定出现\n\n投影不是复制粘贴，而是压缩噪声、提炼结构、强化连接。\n\n## 回刷目标对象\n\n投影不是单向写入。每次投影动作完成后，**必须回刷目标对象的 `updated` 字段为当前日期**。\n\n具体规则：\n- 任何投影到项目、概念、实体、决策、约束等对象的动作，完成后必须将目标对象的 `updated` 刷新为当天日期。\n- 若投影内容改变了目标对象的 `current_focus` 或 `next_step`，一并更新。判断依据：来源中是否包含项目进展、状态变化、阶段完成、新阻塞等信号。\n- 若投影为目标对象新增了 `sources`/`decisions`/`constraints`/`outputs` 条目，同步追加到 frontmatter 对应列表。\n- 这是强制步骤，不是可选优化。跳过此步会导致对象过期堆积——来源层持续增长但项目/概念层停滞不动。\n""",
    },
    "en": {
        "vault_comment": "# distill-vault configuration",
        "dirs": {
            "knowledge": "knowledge",
            "output": "output",
            "ops": "ops",
            "system": "system",
            "skills": "skills",
            "index": "index",
            "health": "health-checks",
            "spec": "specs",
        },
        "object_dirs": {
            "project": "projects",
            "concept": "concepts",
            "entity": "entities",
            "source": "sources",
            "decision": "decisions",
            "constraint": "constraints",
            "analysis": "analysis",
        },
        "template_name": "_template.md",
        "status": "active",
        "template_titles": {
            "project": "Example Project",
            "concept": "Example Concept",
            "entity": "Example Entity",
            "source": "Example Source",
            "decision": "Example Decision",
            "constraint": "Example Constraint",
            "analysis": "Example Analysis",
        },
        "template_headings": {
            "project": "Project Name",
            "concept": "Concept Name",
            "entity": "Entity Name",
            "source": "Source Title",
            "decision": "Decision Title",
            "constraint": "Constraint Title",
            "analysis": "Analysis Title",
        },
        "template_intro": {
            "project": "This is a project dossier template. Summarize completed outcomes, milestones, and evidence...",
            "concept": "This is a template for a concept object. Explain the concept, its boundaries, and when it applies...",
            "entity": "This is a template for an entity object. Capture key details about a tool, team, person, system, or organization...",
            "source": "This is a template for a source object. Summarize an article, interview, meeting note, paper, or other reference material...",
            "decision": "This is a template for a decision object. Explain why the decision was made and what it affects...",
            "constraint": "This is a template for a constraint object. Describe the boundary, rule, or limitation that cannot be ignored...",
            "analysis": "This is a template for an analysis object. Capture reasoning, comparisons, conclusions, and next steps...",
        },
        "sections": {
            "project": ["At a Glance", "Asset and System Map", "How to Use or Run", "Configuration and Access", "Verified Facts", "Decisions and Constraints", "Validation and Evidence"],
            "concept": ["One-sentence Conclusion", "Knowledge Lifecycle", "Application and Reuse", "Evidence and Evolution"],
            "entity": ["Overview", "Key Attributes", "Related Links"],
            "source": ["Summary", "Key Takeaways", "Related Links"],
            "decision": ["One-sentence Conclusion", "Knowledge Lifecycle", "Application and Reuse", "Evidence and Evolution"],
            "constraint": ["One-sentence Conclusion", "Knowledge Lifecycle", "Application and Reuse", "Evidence and Evolution"],
            "analysis": ["Question", "Reasoning", "Conclusion", "Related Links"],
        },
        "object_type_doc": """# Object Types\n\nDistill organizes a vault into 9 object types. The goal is not to restrict how you write, but to make indexing, search, graph analysis, and automation more reliable.\n\n## 1. Project\nA goal-oriented effort such as a product, initiative, research thread, or operational plan. Project objects usually contain goals, scope, milestones, decisions, and outputs.\n\n## 2. Concept\nAn abstract idea, term, method, or model. Concept objects focus on definition, boundaries, assumptions, and relationships to other concepts.\n\n## 3. Entity\nA concrete thing that exists in the world: a company, team, person, product, model, database, API, or software tool. Entity objects are good places for key properties and relationships.\n\n## 4. Source\nReference material such as articles, papers, meeting notes, interviews, podcasts, screenshots, or raw research excerpts. Source objects should preserve provenance, dates, summaries, and confidence where possible.\n\n## 5. Decision\nA choice that was made intentionally. Decision objects explain the context, alternatives, final choice, and expected impact, so the reasoning stays legible later.\n\n## 6. Constraint\nA limitation or non-negotiable condition such as budget, deadline, policy, compliance, performance, resource, or organizational boundary. Constraints explain why some options are not viable.\n\n## 7. Analysis\nA reasoning artifact: comparison, diagnosis, evaluation, synthesis, or investigation. Analysis objects focus on how a conclusion was reached, not just the conclusion itself.\n\n## 8. Output\nA deliverable meant for action or sharing: report, proposal, spec, memo, draft, or published artifact. Outputs are often projected from several upstream objects.\n\n## 9. Note\nAn unstructured or intermediate record such as a scratch note, captured thought, or raw observation. Notes are often the staging area for later promotion into more structured object types.\n\n## Usage guidance\n- Keep one core topic per object whenever possible.\n- Prefer wikilinks like `[[Object Name]]` to connect related objects.\n- Fill in stable frontmatter keys such as `type`, `status`, `title`, `tags`, and `date`.\n- As ideas mature, promote notes into projects, concepts, analyses, decisions, or outputs.\n""",
        "projection_doc": """# Projection Rules\n\nProjection is the process of turning natural-language notes, captured material, or meeting records into stable, structured objects that work well inside the vault.\n\n## Why projection matters\nRaw notes usually contain context noise, personal shorthand, and time-bound details. They are useful to capture, but not always ideal as durable graph nodes. Projection extracts the durable signal and turns it into clear projects, concepts, decisions, constraints, analyses, and outputs.\n\n## Core principles\n1. **One object, one core topic**: avoid mixing several ideas into one object.\n2. **Preserve provenance**: structured objects should link back to relevant `[[sources]]` or `[[notes]]`.\n3. **Make relationships explicit**: use wikilinks to connect projects, concepts, entities, decisions, and constraints.\n4. **Separate reasoning from conclusions**: put reasoning in analysis, and durable conclusions in decisions or outputs.\n5. **Use stable names**: object titles should be reusable, searchable, and easy to reference.\n\n## Common projection paths\n- Meeting notes or reading excerpts → `source`\n- Raw thoughts or temporary captures → `note`\n- Synthesized definitions from multiple notes → `concept`\n- An ongoing page for a concrete initiative → `project`\n- Tradeoff exploration and reasoning → `analysis`\n- A committed choice → `decision`\n- A hard boundary condition → `constraint`\n- A shareable or executable artifact → `output`\n\n## Recommended workflow\n1. Capture raw material quickly without forcing structure too early.\n2. Identify the durable facts, concepts, choices, constraints, and conclusions.\n3. Create one structured object per stable topic and add frontmatter.\n4. Link the new object to projects, sources, and neighboring concepts with `[[wikilinks]]`.\n5. Move execution-ready conclusions into outputs while keeping supporting reasoning in analysis.\n\n## A simple heuristic\nA note is worth projecting into a structured object if at least two of these are true:\n- it will be referenced repeatedly\n- it affects decisions or execution\n- it needs explicit relationships to other objects\n- it should appear reliably in future search or automation\n\nProjection is not copy-paste. It is the act of compressing noise, extracting structure, and strengthening links.\n\n## Back-brush target objects\n\nProjection is not one-way. After each projection action, **you must back-brush the target object's `updated` field to the current date**.\n\nRules:\n- Any projection onto projects, concepts, entities, decisions, or constraints must refresh the target's `updated` field to today.\n- If the projection changes the target's `current_focus` or `next_step`, update those too. Look for signals like: project progress, status changes, milestone completions, new blockers.\n- If the projection adds entries to the target's `sources`/`decisions`/`constraints`/`outputs`, append them to the corresponding frontmatter list.\n- This is a mandatory step, not an optional optimization. Skipping it causes object staleness — sources keep growing while projects/concepts stay frozen.\n""",
    },
}


def init_vault(target_dir: str, lang: str = "zh", with_examples: bool = False) -> dict:
    """Create a new distill vault skeleton."""
    spec = LANG_SPECS.get(lang.lower())
    if spec is None:
        raise ValueError("lang must be 'zh' or 'en'")

    root = Path(target_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    dirs_created = 0
    files_created = 0

    def ensure_dir(path: Path) -> None:
        nonlocal dirs_created
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            dirs_created += 1

    def write_text(path: Path, content: str) -> None:
        nonlocal files_created
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        path.write_text(content, encoding="utf-8")
        if not existed:
            files_created += 1

    def ensure_runtime_gitignore() -> None:
        nonlocal files_created
        if _ensure_runtime_gitignore(root):
            files_created += 1

    dirs = spec["dirs"]
    knowledge_dir = root / dirs["knowledge"]
    output_dir = root / dirs["output"]
    ops_dir = root / dirs["ops"]
    system_dir = root / dirs["system"]
    spec_dir = system_dir / dirs["spec"]
    skills_dir = system_dir / dirs["skills"]

    required_dirs = [
        knowledge_dir,
        output_dir,
        ops_dir,
        ops_dir / dirs["index"],
        ops_dir / dirs["health"],
        system_dir,
        spec_dir,
        skills_dir,
    ]
    required_dirs.extend(knowledge_dir / folder for folder in spec["object_dirs"].values())

    for path in required_dirs:
        ensure_dir(path)

    write_text(root / "distill.yaml", _build_config(spec))
    write_text(root / "README.md", _build_root_readme(lang.lower(), with_examples))
    ensure_runtime_gitignore()

    for obj_type, folder in spec["object_dirs"].items():
        template_path = knowledge_dir / folder / spec["template_name"]
        write_text(template_path, _build_template(spec, obj_type))

    if lang.lower() == "zh":
        object_doc_name = "对象类型.md"
        projection_doc_name = "投影规则.md"
    else:
        object_doc_name = "object-types.md"
        projection_doc_name = "projection-rules.md"

    write_text(spec_dir / object_doc_name, _v2_object_type_doc(spec["object_type_doc"], lang.lower()))
    write_text(spec_dir / projection_doc_name, _v2_projection_doc(spec["projection_doc"], lang.lower()))

    for relative_path, content in build_skill_scaffold(lang.lower()).items():
        write_text(skills_dir / relative_path, content)

    if with_examples:
        for relative_path, content in _build_examples(lang.lower()):
            write_text(root / relative_path, content)

    return {"path": str(root), "dirs_created": dirs_created, "files_created": files_created}


def init_existing_vault(target_dir: str, lang: str = "zh") -> dict:
    """Write a starter distill.yaml for an existing vault without overwriting notes."""
    spec = LANG_SPECS.get(lang.lower())
    if spec is None:
        raise ValueError("lang must be 'zh' or 'en'")

    root = Path(target_dir).expanduser()
    if not root.exists() or not root.is_dir():
        raise ValueError("target_dir must be an existing directory")

    config_path = root / "distill.yaml"
    if config_path.exists():
        raise ValueError("distill.yaml already exists")

    inferred = infer_existing_vault_config(root)
    config_path.write_text(_render_vault_config(inferred["vault"], spec["vault_comment"]), encoding="utf-8")
    gitignore_changed = _ensure_runtime_gitignore(root)
    return {"path": str(root), "dirs_created": 0, "files_created": 1 + int(gitignore_changed)}


def bootstrap_existing_vault(target_dir: str, lang: str = "zh") -> dict:
    """Backward-compatible alias for existing-vault bootstrap."""
    return init_existing_vault(target_dir, lang=lang)


def _ensure_runtime_gitignore(root: Path) -> bool:
    gitignore_path = root / ".gitignore"
    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    existing_lines = existing.splitlines()
    missing_lines = [line for line in DISTILL_RUNTIME_GITIGNORE_LINES if line not in existing_lines]
    if not missing_lines:
        return False

    parts = []
    if existing:
        parts.append(existing.rstrip("\n"))
    parts.append("\n".join(missing_lines))
    gitignore_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return True


def _build_config(spec: dict) -> str:
    dirs = spec["dirs"]
    return _render_vault_config(
        {
            "knowledge_dirs": [dirs["knowledge"]],
            "output_dirs": [dirs["output"]],
            "ops_dirs": [dirs["ops"]],
            "system_dirs": [dirs["system"]],
        },
        spec["vault_comment"],
    )


def _render_vault_config(vault_cfg: dict, comment: str) -> str:
    lines = [comment, "vault:"]
    for key in ("knowledge_dirs", "output_dirs", "ops_dirs", "system_dirs"):
        values = vault_cfg.get(key, []) or []
        if not values:
            lines.append(f"  {key}: []")
            continue
        lines.append(f"  {key}:")
        for value in values:
            lines.append(f"    - {value}")
    return "\n".join(lines) + "\n"


def _build_template(spec: dict, obj_type: str) -> str:
    title = spec["template_titles"][obj_type]
    heading = spec["template_headings"][obj_type]
    intro = spec["template_intro"][obj_type]
    sections = spec["sections"][obj_type]

    body = [
        "---",
        f"type: {obj_type}",
        f"status: {spec['status']}",
        f'title: "{title}"',
        *(
            ["presentation: project-handbook-v1"]
            if obj_type == "project"
            else ["presentation: knowledge-compounding-v1"]
            if obj_type in {"concept", "decision", "constraint"}
            else []
        ),
        "tags: []",
        "date: {{today}}",
        "---",
        "",
        f"# {heading}",
        "",
        f"> {intro}",
        "",
    ]

    for section in sections[:-1]:
        body.extend([f"## {section}", ""])

    body.extend([f"## {sections[-1]}", "- [[]]", ""])
    return "\n".join(body)


def _v2_object_type_doc(text: str, lang: str) -> str:
    replacements = {
        "zh": {
            "用于记录一个正在推进或已经完成的目标性工作，例如产品、课题、计划或行动流。项目对象通常包含目标、范围、里程碑、关键决策和相关成果。":
                "用于汇总一项工作的已完成成果、已验证里程碑、关键决策、约束和证据。下一步、待办、优先级和截止时间属于日程工具。",
        },
        "en": {
            "A goal-oriented effort such as a product, initiative, research thread, or operational plan. Project objects usually contain goals, scope, milestones, decisions, and outputs.":
                "A completed-work dossier for a product, initiative, research thread, or operational effort. It summarizes verified outcomes, milestones, decisions, constraints, selected outputs, and evidence; plans and next steps belong in scheduling tools.",
        },
    }
    for previous, replacement in replacements[lang].items():
        text = text.replace(previous, replacement)
    return text


def _v2_projection_doc(text: str, lang: str) -> str:
    replacements = {
        "zh": {
            "围绕某项工作形成的持续页面": "围绕某项工作形成的已完成成果档案",
            "若投影内容改变了目标对象的 `current_focus` 或 `next_step`，一并更新。判断依据：来源中是否包含项目进展、状态变化、阶段完成、新阻塞等信号。":
                "项目对象只吸收已经完成或验证的事实，并更新 `summary` 或正文中的“已完成成果”；下一步、计划和待办保留在日程工具。",
            "若投影为目标对象新增了 `sources`/`decisions`/`constraints`/`outputs` 条目，同步追加到 frontmatter 对应列表。":
                "若投影为目标对象新增了 `sources`/`decisions`/`constraints`/`key_outputs` 条目，同步追加到 frontmatter 对应列表。",
        },
        "en": {
            "An ongoing page for a concrete initiative": "A completed-work dossier for a concrete initiative",
            "If the projection changes the target's `current_focus` or `next_step`, update those too. Look for signals like: project progress, status changes, milestone completions, new blockers.":
                "Project objects only absorb completed or verified facts into `summary` and completed-outcome sections; keep plans and next steps in scheduling tools.",
            "If the projection adds entries to the target's `sources`/`decisions`/`constraints`/`outputs`, append them to the corresponding frontmatter list.":
                "If the projection adds entries to the target's `sources`/`decisions`/`constraints`/`key_outputs`, append them to the corresponding frontmatter list.",
        },
    }
    for previous, replacement in replacements[lang].items():
        text = text.replace(previous, replacement)
    return text


def _build_root_readme(lang: str, with_examples: bool) -> str:
    if lang == "zh":
        if with_examples:
            return """# distill-vault 新手路径

这个 vault 已经包含一组可运行的示例对象，目标是让你先跑通第一轮索引、搜索和健康检查。

## First win
1. 先看当前对象状态：`distill status`
2. 再检查结构问题：`distill lint`
3. 构建图与派生产物：`distill run`
4. 验证可检索性：`distill search \"知识库\" --mode hybrid`

## 目录提示
- `知识/`：对象层
- `输出/`：交付物与派生产物
- `运维/`：索引、健康检查等运行痕迹
- `系统/规范/`：对象类型与投影规则

## 下一步
- 从 `知识/项目/`、`知识/概念/`、`知识/来源/` 里挑一个示例开始改成你的真实内容。
- 任何新对象都尽量补齐 `title`、`type`、`status`，并至少连一条 `[[wikilink]]`。
"""
        return """# distill-vault 新手路径

这个 vault 现在是一个干净骨架。最短 first win 是：先复制一个模板，写入第一条对象，再跑一次状态、lint 和主 pipeline。

## First win
1. 从模板开始，例如：`知识/概念/_模板.md`
2. 复制成你的第一条对象，并补齐 `title` / `type` / `status`
3. 给它至少加一条 `[[wikilink]]`
4. 运行：`distill status`
5. 运行：`distill lint`
6. 运行：`distill run`

## 推荐起点
- `知识/项目/_模板.md`
- `知识/概念/_模板.md`
- `知识/来源/_模板.md`

## 目录提示
- `知识/`：对象层
- `输出/`：交付物与派生产物
- `运维/`：索引、健康检查等运行痕迹
- `系统/规范/`：对象类型与投影规则
"""

    if with_examples:
        return """# distill-vault getting started

This vault already includes runnable example objects so you can reach a first win before adding your own notes.

## First win
1. Inspect the current object graph: `distill status`
2. Check structural health: `distill lint`
3. Build graph + derived artifacts: `distill run`
4. Verify search works end-to-end: `distill search \"knowledge\" --mode hybrid`

## Directory guide
- `knowledge/`: object layer
- `output/`: deliverables and derived artifacts
- `ops/`: index, health, and runtime artifacts
- `system/specs/`: object-type and projection rules

## Next
- Rewrite one example under `knowledge/projects/`, `knowledge/concepts/`, or `knowledge/sources/` with your own content.
- Keep `title`, `type`, and `status` frontmatter stable, and add at least one `[[wikilink]]`.
"""
    return """# distill-vault getting started

This vault is a clean skeleton. The shortest first win is: copy one template, create your first object, then run status, lint, and the main pipeline.

## First win
1. Start from a template such as `knowledge/concepts/_template.md`
2. Copy it into your first object and fill in `title` / `type` / `status`
3. Add at least one `[[wikilink]]`
4. Run: `distill status`
5. Run: `distill lint`
6. Run: `distill run`

## Recommended starting points
- `knowledge/projects/_template.md`
- `knowledge/concepts/_template.md`
- `knowledge/sources/_template.md`

## Directory guide
- `knowledge/`: object layer
- `output/`: deliverables and derived artifacts
- `ops/`: index, health, and runtime artifacts
- `system/specs/`: object-type and projection rules
"""


def _build_examples(lang: str) -> Iterable[tuple[str, str]]:
    today = date.today().isoformat()
    if lang == "zh":
        return [
            (
                "知识/项目/智能知识助手.md",
                f"""---
type: project
status: active
title: "智能知识助手"
tags: [AI, 知识库]
date: {today}
---

# 智能知识助手

> 一个面向团队内部的知识问答与沉淀项目，目标是把分散文档转成可检索、可追踪的对象网络。

## 目标
- 建立统一的知识目录与对象结构。
- 让成员可以通过自然语言检索历史决策与来源。
- 为后续自动化报告与健康检查打基础。

## 关键决策
- 采用 [[检索增强生成]] 作为问答主路径。
- 保持知识库为 [[Obsidian Vault]] 兼容结构。
- 将关键分析沉淀到 [[首轮知识库方案分析]]。

## 相关链接
- [[检索增强生成]]
- [[Obsidian Vault]]
- [[知识库采用 Markdown + Wikilink]]
- [[数据需保留在本地网络]]
- [[2026-05-01 团队知识库梳理会议]]
""",
            ),
            (
                "知识/概念/检索增强生成.md",
                f"""---
type: concept
status: active
title: "检索增强生成"
tags: [RAG, 检索]
date: {today}
---

# 检索增强生成

> 通过先检索相关资料，再将结果提供给生成模型回答问题的方法。

## 定义
检索增强生成（RAG）把外部知识与生成模型结合，降低纯参数记忆带来的幻觉风险。

## 边界
- 它不能替代高质量的原始 [[来源]]。
- 它依赖稳定的索引和对象链接结构。

## 相关链接
- [[智能知识助手]]
- [[2026-05-01 团队知识库梳理会议]]
- [[首轮知识库方案分析]]
""",
            ),
            (
                "知识/实体/Obsidian Vault.md",
                f"""---
type: entity
status: active
title: "Obsidian Vault"
tags: [工具, Markdown]
date: {today}
---

# Obsidian Vault

> 一种以本地文件夹和 Markdown 文件为核心的数据组织方式。

## 简介
项目选择使用 Obsidian 兼容目录结构，是因为它天然支持本地优先、可读文本和 `[[wikilink]]` 连接。

## 关键属性
- 文件格式简单，便于版本控制。
- 可以作为 [[智能知识助手]] 的长期知识载体。
- 有利于执行 [[知识库采用 Markdown + Wikilink]]。

## 相关链接
- [[智能知识助手]]
- [[知识库采用 Markdown + Wikilink]]
""",
            ),
            (
                "知识/来源/2026-05-01 团队知识库梳理会议.md",
                f"""---
type: source
status: active
title: "2026-05-01 团队知识库梳理会议"
tags: [会议, 来源]
date: {today}
---

# 2026-05-01 团队知识库梳理会议

> 团队首次统一讨论知识整理方式，明确了对象化沉淀和本地优先的方向。

## 摘要
会议讨论了当前知识分散、决策难追溯、输出复用率低的问题，并确定先建设一个轻量级对象知识库。

## 关键信息
- 首个试点项目为 [[智能知识助手]]。
- 核心技术路径参考 [[检索增强生成]]。
- 知识载体倾向于 [[Obsidian Vault]] 兼容结构。

## 相关链接
- [[知识库采用 Markdown + Wikilink]]
- [[数据需保留在本地网络]]
- [[首轮知识库方案分析]]
""",
            ),
            (
                "知识/决策/知识库采用 Markdown + Wikilink.md",
                f"""---
type: decision
status: active
title: "知识库采用 Markdown + Wikilink"
tags: [决策, 规范]
date: {today}
---

# 知识库采用 Markdown + Wikilink

> 为保证可迁移性、可读性与链接能力，知识库统一使用 Markdown 文件和 wikilink 语法。

## 背景
团队需要一个不依赖单一 SaaS 平台、且能被脚本和 AI 工具稳定处理的知识底座。

## 决策内容
- 所有核心对象以 Markdown 保存。
- 对象之间优先使用 `[[对象名]]` 建立关系。
- 目录结构遵循 Distill 的对象分类方式。

## 影响
该决策直接影响 [[智能知识助手]] 的目录设计，也决定了 [[Obsidian Vault]] 作为默认兼容形式。

## 相关链接
- [[Obsidian Vault]]
- [[数据需保留在本地网络]]
- [[2026-05-01 团队知识库梳理会议]]
""",
            ),
            (
                "知识/约束/数据需保留在本地网络.md",
                f"""---
type: constraint
status: active
title: "数据需保留在本地网络"
tags: [约束, 合规]
date: {today}
---

# 数据需保留在本地网络

> 涉及内部文档与运营数据的内容不能直接同步到不受控的外部平台。

## 约束描述
知识库必须支持本地存储、离线备份和可审计访问方式，避免核心数据外流。

## 影响范围
- 影响 [[智能知识助手]] 的部署方式。
- 限制第三方托管知识库产品的选择。
- 强化 [[知识库采用 Markdown + Wikilink]] 的必要性。

## 相关链接
- [[Obsidian Vault]]
- [[首轮知识库方案分析]]
""",
            ),
            (
                "知识/分析/首轮知识库方案分析.md",
                f"""---
type: analysis
status: active
title: "首轮知识库方案分析"
tags: [分析, 方案]
date: {today}
---

# 首轮知识库方案分析

> 对知识库对象结构、技术路径和约束条件进行的首轮综合分析。

## 问题
如何在低维护成本下，让团队知识既能被人阅读，也能被 AI 工具稳定处理？

## 分析过程
对比了纯文档库、数据库驱动方案以及本地 Markdown 方案，发现本地对象化目录最适合作为第一阶段落地路径。

## 结论
建议以 [[智能知识助手]] 为试点，采用 [[知识库采用 Markdown + Wikilink]]，并围绕 [[检索增强生成]] 逐步增强检索能力。

## 相关链接
- [[2026-05-01 团队知识库梳理会议]]
- [[数据需保留在本地网络]]
- [[Obsidian Vault]]
""",
            ),
        ]

    return [
        (
            "knowledge/projects/knowledge-assistant.md",
            f"""---
type: project
status: active
title: "Knowledge Assistant"
tags: [ai, knowledge-base]
date: {today}
---

# Knowledge Assistant

> An internal initiative to turn scattered notes and documents into a searchable network of structured knowledge objects.

## Goals
- Create a shared object model for team knowledge.
- Make past decisions and sources easier to find.
- Support future reporting and health automation.

## Key Decisions
- Use [[Retrieval-Augmented Generation]] as the main Q&A path.
- Keep the vault compatible with [[Obsidian Vault]].
- Capture early reasoning in [[Initial Knowledge Base Analysis]].

## Related Links
- [[Retrieval-Augmented Generation]]
- [[Obsidian Vault]]
- [[Use Markdown and Wikilinks for the Vault]]
- [[Data Must Stay on the Local Network]]
- [[2026-05-01 Knowledge Base Planning Meeting]]
""",
        ),
        (
            "knowledge/concepts/retrieval-augmented-generation.md",
            f"""---
type: concept
status: active
title: "Retrieval-Augmented Generation"
tags: [rag, retrieval]
date: {today}
---

# Retrieval-Augmented Generation

> A method that retrieves relevant material before asking a model to answer with grounded context.

## Definition
Retrieval-augmented generation (RAG) combines external knowledge retrieval with generation to reduce hallucinations and improve traceability.

## Boundaries
- It does not replace high-quality [[sources]].
- It depends on stable indexing and links between objects.

## Related Links
- [[Knowledge Assistant]]
- [[2026-05-01 Knowledge Base Planning Meeting]]
- [[Initial Knowledge Base Analysis]]
""",
        ),
        (
            "knowledge/entities/obsidian-vault.md",
            f"""---
type: entity
status: active
title: "Obsidian Vault"
tags: [tool, markdown]
date: {today}
---

# Obsidian Vault

> A local-folder and Markdown-based structure for managing connected notes.

## Overview
The project uses an Obsidian-compatible layout because it supports local-first storage, plain text, and durable `[[wikilink]]` relationships.

## Key Attributes
- Easy to version with git.
- Serves as the long-term storage layer for [[Knowledge Assistant]].
- Aligns with [[Use Markdown and Wikilinks for the Vault]].

## Related Links
- [[Knowledge Assistant]]
- [[Use Markdown and Wikilinks for the Vault]]
""",
        ),
        (
            "knowledge/sources/2026-05-01-knowledge-base-planning-meeting.md",
            f"""---
type: source
status: active
title: "2026-05-01 Knowledge Base Planning Meeting"
tags: [meeting, source]
date: {today}
---

# 2026-05-01 Knowledge Base Planning Meeting

> The team's first structured discussion about how to organize knowledge as durable objects in a local-first vault.

## Summary
The meeting focused on scattered documentation, poor traceability for decisions, and low reuse of previous outputs. The team agreed to start with a lightweight structured vault.

## Key Takeaways
- The first pilot project is [[Knowledge Assistant]].
- The retrieval approach should be informed by [[Retrieval-Augmented Generation]].
- The storage format should stay compatible with [[Obsidian Vault]].

## Related Links
- [[Use Markdown and Wikilinks for the Vault]]
- [[Data Must Stay on the Local Network]]
- [[Initial Knowledge Base Analysis]]
""",
        ),
        (
            "knowledge/decisions/use-markdown-and-wikilinks-for-the-vault.md",
            f"""---
type: decision
status: active
title: "Use Markdown and Wikilinks for the Vault"
tags: [decision, standard]
date: {today}
---

# Use Markdown and Wikilinks for the Vault

> To preserve portability, readability, and durable linking, the vault stores core objects as Markdown files connected by wikilinks.

## Context
The team needs a knowledge foundation that is not locked into a single SaaS tool and can be processed reliably by scripts and AI workflows.

## Decision
- Store core objects as Markdown files.
- Use `[[Object Name]]` as the preferred linking mechanism.
- Follow the Distill object directory structure.

## Impact
This decision shapes the folder design of [[Knowledge Assistant]] and makes [[Obsidian Vault]] the default compatibility target.

## Related Links
- [[Obsidian Vault]]
- [[Data Must Stay on the Local Network]]
- [[2026-05-01 Knowledge Base Planning Meeting]]
""",
        ),
        (
            "knowledge/constraints/data-must-stay-on-the-local-network.md",
            f"""---
type: constraint
status: active
title: "Data Must Stay on the Local Network"
tags: [constraint, compliance]
date: {today}
---

# Data Must Stay on the Local Network

> Internal documents and operational data cannot be synced directly into uncontrolled third-party platforms.

## Constraint
The vault must support local storage, offline backups, and auditable access patterns so sensitive material remains under team control.

## Scope
- Affects how [[Knowledge Assistant]] is deployed.
- Limits the use of fully hosted external knowledge platforms.
- Reinforces [[Use Markdown and Wikilinks for the Vault]].

## Related Links
- [[Obsidian Vault]]
- [[Initial Knowledge Base Analysis]]
""",
        ),
        (
            "knowledge/analysis/initial-knowledge-base-analysis.md",
            f"""---
type: analysis
status: active
title: "Initial Knowledge Base Analysis"
tags: [analysis, planning]
date: {today}
---

# Initial Knowledge Base Analysis

> A first-pass evaluation of object structure, technical direction, and constraints for the vault.

## Question
How can the team make knowledge easy for humans to read while also making it reliable for AI tooling to process?

## Reasoning
We compared plain document folders, database-first systems, and a local Markdown object model. The local structured vault offered the best first-step tradeoff.

## Conclusion
Start with [[Knowledge Assistant]], adopt [[Use Markdown and Wikilinks for the Vault]], and expand retrieval capabilities around [[Retrieval-Augmented Generation]].

## Related Links
- [[2026-05-01 Knowledge Base Planning Meeting]]
- [[Data Must Stay on the Local Network]]
- [[Obsidian Vault]]
""",
        ),
    ]
