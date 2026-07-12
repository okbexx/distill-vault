"""Action-oriented guidance for status, health, and lint surfaces."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


Step = dict[str, str]


def _step(title: str, why: str, do_next: str, verify_with: str) -> Step:
    return {
        "title": title,
        "why": why,
        "do_next": do_next,
        "verify_with": verify_with,
    }


def _has_runtime_checkpoint(vault_root: Any) -> bool:
    if not vault_root:
        return False
    return (Path(vault_root) / ".distill" / "checkpoint.json").exists()


def _has_distill_config(vault_root: Any) -> bool:
    if not vault_root:
        return False
    return (Path(vault_root) / "distill.yaml").exists()


def _has_distill_structure(vault_root: Any) -> bool:
    if not vault_root:
        return False
    root = Path(vault_root)
    return (root / "知识").exists() or (root / "knowledge").exists()


def render_next_steps_markdown(steps: list[Step], heading: str = "## Recommended Next Steps") -> str:
    if not steps:
        return ""
    lines = [heading]
    for idx, step in enumerate(steps[:3], start=1):
        lines.append(f"{idx}. **{step['title']}**")
        lines.append(f"   - Why: {step['why']}")
        lines.append(f"   - Do next: {step['do_next']}")
        lines.append(f"   - Verify with: `{step['verify_with']}`")
    return "\n".join(lines)


def guidance_from_index(index: Any) -> list[Step]:
    stats = getattr(index, "stats", {}) or {}
    steps: list[Step] = []

    vault_root = getattr(index, "root", None) or getattr(index, "vault", None)
    has_checkpoint_fn = getattr(index, "has_checkpoint", None)
    if callable(has_checkpoint_fn):
        has_checkpoint = bool(has_checkpoint_fn())
    else:
        has_checkpoint = _has_runtime_checkpoint(vault_root)
    has_distill_config = _has_distill_config(vault_root)
    has_distill_structure = _has_distill_structure(vault_root)
    total_objects = int(stats.get("total_objects", 0))

    broken_links = list(getattr(index, "broken_links", []) or [])
    true_orphans = list((getattr(index, "orphan_buckets", {}) or {}).get("true_orphan", []))

    if total_objects > 0 and not has_distill_config and not has_distill_structure:
        steps.append(
            _step(
                "Bootstrap distill.yaml for this existing Obsidian vault",
                "distill is currently scanning the markdown with inferred defaults, so scan roots, path semantics, and runtime artifact locations are still best-effort guesses.",
                "Write the starter config in place before committing to the first long-term runtime setup.",
                "distill init . --existing",
            )
        )

    if total_objects > 0 and not has_checkpoint:
        if broken_links or true_orphans:
            steps.append(
                _step(
                    "Preflight this existing vault before the first graph build",
                    "No pipeline checkpoint exists yet, so distill has not produced trustworthy graph, search, or report artifacts for the current files.",
                    "Use `distill lint` as the gate: clear blocking structural issues first, then run the pipeline once the vault is stable enough to trust.",
                    "distill lint",
                )
            )
        else:
            steps.append(
                _step(
                    "Complete the first distill run for this existing vault",
                    "No pipeline checkpoint exists yet, so graph, search, and report artifacts have not been built from the current files.",
                    "Run the full pipeline once to establish the first checkpoint and derived artifacts.",
                    "distill run",
                )
            )

    if broken_links:
        sample = broken_links[0]
        steps.append(
            _step(
                "Resolve broken links before trusting graph-derived output",
                f"{stats.get('broken_links', len(broken_links))} unresolved wikilink(s) will skew graph traversal and search relevance.",
                f"Fix or create the target `[[{sample['to']}]]` referenced from `{sample['from']}`.",
                "distill lint",
            )
        )

    if true_orphans:
        sample_path = true_orphans[0]
        sample_title = getattr(index, "_path_index", {}).get(sample_path, {}).get("title", Path(sample_path).stem)
        steps.append(
            _step(
                "Reconnect true orphans to the working graph",
                f"{len(true_orphans)} object(s) have no incoming or outgoing links, so they cannot participate in search or impact analysis.",
                f"Add at least one incoming or outgoing link for `{sample_path}` (start with `{sample_title}`).",
                "distill status",
            )
        )

    if steps:
        return steps[:3]

    if total_objects == 0:
        return [
            _step(
                "Seed the vault with its first typed object",
                "The vault is empty, so there is nothing yet for the runtime to index, link, or analyze.",
                "Add a note under `知识/概念/` or `知识/来源/` with `title`, `type`, and `status` frontmatter.",
                "distill status",
            )
        ]

    return [
        _step(
            "Refresh runtime artifacts while the vault is clean",
            "The scan is currently free of broken links and true orphans, so this is the right moment to refresh graph, exports, and checkpoint data.",
            "Run the main pipeline to rebuild graph and derived reports from this trusted state.",
            "distill run",
        )
    ]


def guidance_from_lint(issues: list[dict[str, Any]] | None, vault_root: Any = None) -> list[Step]:
    issues = issues or []
    has_checkpoint = _has_runtime_checkpoint(vault_root)
    has_distill_config = _has_distill_config(vault_root)
    has_distill_structure = _has_distill_structure(vault_root)

    if not issues:
        steps: list[Step] = []
        if not has_distill_config and not has_distill_structure:
            steps.append(
                _step(
                    "Bootstrap distill.yaml before locking in this runtime layout",
                    "Lint can run on inferred defaults, but an explicit config keeps scan roots and artifact locations stable across machines.",
                    "Write the starter config in place, then rerun lint once to confirm the inferred scan roots still look right.",
                    "distill init . --existing",
                )
            )
        if not has_checkpoint:
            steps.append(
                _step(
                    "Complete the first pipeline run for this existing vault",
                    "Lint is clean and no pipeline checkpoint exists yet, so distill can now build the first trustworthy graph and report artifacts.",
                    "Run the full pipeline once to create the initial checkpoint and derived outputs.",
                    "distill run",
                )
            )
            return steps[:3]
        steps.append(
            _step(
                "Refresh runtime artifacts from this clean lint baseline",
                "Lint found no structural issues, so graph and export regeneration should now be trustworthy.",
                "Run the full pipeline to refresh graph, reports, and checkpoint metadata.",
                "distill run",
            )
        )
        return steps[:3]

    steps: list[Step] = []
    by_rule = Counter(issue.get("rule", "unknown") for issue in issues)

    if not has_distill_config and not has_distill_structure:
        steps.append(
            _step(
                "Bootstrap distill.yaml before the first durable run",
                "The current lint view is based on inferred defaults, so persisting the scan roots now reduces surprise when the vault grows.",
                "Write the starter config in place, then keep working through the reported issues.",
                "distill init . --existing",
            )
        )

    if not has_checkpoint:
        steps.append(
            _step(
                "Finish structural preflight before the first pipeline run",
                "No pipeline checkpoint exists yet, so the first `distill run` should wait until blocking lint issues are under control.",
                "Resolve blocking lint errors and rerun lint until the vault is ready for its first graph build.",
                "distill lint",
            )
        )

    broken_issue = next((issue for issue in issues if issue.get("rule") == "broken-wikilink"), None)
    if broken_issue is not None:
        steps.append(
            _step(
                "Resolve broken wikilinks before anything else",
                f"{by_rule['broken-wikilink']} broken wikilink(s) block reliable graph traversal and downstream reports.",
                f"Fix or create the target `[[{broken_issue.get('link', 'unknown')}]]` referenced from `{broken_issue.get('file', 'unknown')}`.",
                "distill lint",
            )
        )

    metadata_issue_count = by_rule["incomplete-frontmatter"] + by_rule["unknown-type"]
    if metadata_issue_count:
        steps.append(
            _step(
                "Run the safe auto-fix pass for metadata issues",
                f"{metadata_issue_count} issue(s) are recoverable through automatic type/frontmatter normalization.",
                "Apply the built-in metadata fixer before doing manual cleanup.",
                "distill lint --fix",
            )
        )

    true_orphan_issues = [
        issue
        for issue in issues
        if issue.get("rule") == "orphan-object" and issue.get("orphan_bucket") == "true_orphan"
    ]
    if true_orphan_issues:
        sample = true_orphan_issues[0]
        steps.append(
            _step(
                "Attach true orphans to at least one related object",
                f"{len(true_orphan_issues)} object(s) are isolated from the graph and will stay invisible to impact analysis.",
                f"Add an incoming or outgoing wikilink for `{sample.get('file', 'unknown')}` from a related note.",
                "distill status",
            )
        )

    if steps:
        return steps[:3]

    return [
        _step(
            "Review the remaining informational issues, then refresh the runtime view",
            f"Lint found {len(issues)} non-blocking issue(s) that still deserve a human pass.",
            "Review the reported files and decide whether they should stay informational or be linked/normalized.",
            "distill run",
        )
    ]
