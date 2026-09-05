#!/usr/bin/env python3
"""distill-vault CLI: Knowledge base runtime."""

import os
import sys
import json
from pathlib import Path

import click

from .config import load_config, get_scan_dirs, get_ops_dir, looks_like_obsidian_vault
from .capabilities import CapabilityPayload, collect_capabilities, render_capabilities_markdown
from .instance_upgrade import (
    DoctorPayload,
    UpgradePlanPayload,
    build_upgrade_plan,
    doctor_instance,
    render_doctor_markdown,
    render_upgrade_plan_markdown,
)
from .index import VaultIndex
from .lint import VaultLinter
from .health import HealthChecker
from .next_steps import render_next_steps_markdown
from .search_hybrid import VaultSearch
from .promote import PromotionPipeline, apply_promotion, review_promotion
from .utils import find_vault_root
from .routing import (
    ApplyPayload,
    PlanPayload,
    RoutePayload,
    build_apply_payload,
    capture_progress_update,
    render_apply_markdown,
    render_plan_markdown,
    render_route_markdown,
    route_intent,
    route_plan,
)
from .write_object import write_object
from .web_server import DistillWebServer
from .worker_pool import WorkerPool
from .mcp_config import (
    DEFAULT_CODEX_MCP_NAME,
    MCPConfigError,
    get_codex_mcp_status,
    install_codex_mcp_server,
    render_status,
    resolve_codex_config_path,
    resolve_install_vault,
)
from .migrate import migrate_vault
from .skill_specs import discover_skill_specs, get_skill_spec, export_skill, export_targets, render_skill, install_skill, verify_installed_skill, reconcile_installed_skill, verification_result_payload, doctor_payload, verify_many_payload, reconcile_result_payload, SUPPORTED_SKILL_TARGETS

PASS_CONTEXT = click.make_pass_decorator(dict, ensure=True)


def _require_vault(ctx):
    """Ensure we're inside a distill vault or an existing Obsidian vault that can be inferred."""
    vault = ctx.obj.get("vault")
    if vault is None:
        click.echo("Error: Not inside a distill-vault. Run 'distill init' to create one.", err=True)
        sys.exit(1)
    cfg_file = vault / "distill.yaml"
    has_dirs = (vault / "知识").exists() or (vault / "knowledge").exists()
    inferred_existing_vault = looks_like_obsidian_vault(
        vault,
        allow_markdown_fallback=ctx.obj.get("vault_explicit", False),
    )
    if not has_dirs and not cfg_file.exists() and not inferred_existing_vault:
        click.echo(
            f"Error: {vault} is not a valid vault. Run 'distill init' first, or use 'distill init . --existing' inside an existing Obsidian vault.",
            err=True,
        )
        sys.exit(1)


@click.group()
@click.option("--vault", "-v", type=click.Path(), help="Path to vault root (default: current dir)")
@click.option("--verbose", "-V", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx, vault, verbose):
    """distill-vault: Runtime for your knowledge base."""
    vault_path = Path(vault) if vault else find_vault_root(Path.cwd())
    # Allow None for init command — it doesn't need an existing vault
    ctx.ensure_object(dict)
    ctx.obj["vault"] = vault_path or Path.cwd()
    ctx.obj["vault_explicit"] = bool(vault)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def status(ctx, fmt):
    """Show vault overview and statistics."""
    _require_vault(ctx)
    idx = VaultIndex(ctx.obj["vault"])
    idx.scan()
    if fmt == "json":
        click.echo(json.dumps(idx.status_payload(), ensure_ascii=False, indent=2))
    else:
        click.echo(idx.report())


@cli.command(name="migrate")
@click.option("--to", "target_version", type=click.IntRange(min=1), required=True, help="Target vault contract version")
@click.option("--apply", is_flag=True, help="Apply the validated migration plan atomically")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def migrate_command(ctx, target_version: int, apply: bool, fmt: str) -> None:
    """Preview or apply an idempotent vault contract migration."""
    _require_vault(ctx)
    try:
        payload = migrate_vault(ctx.obj["vault"], target_version=target_version, apply=apply)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    mode = "applied" if apply else "preview"
    click.echo(f"Migration v{target_version} ({mode})")
    click.echo(f"  scanned: {payload['files_scanned']}")
    click.echo(f"  changed: {payload['files_changed']}")
    click.echo(f"  validation_errors: {len(payload['validation_errors'])}")
    for change in payload["changes"]:
        click.echo(f"  - {change['path']}: {', '.join(change['operations'])}")


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def capabilities(ctx, fmt: str) -> None:
    """Show the engine capability surface exposed by this distill runtime."""
    _require_vault(ctx)
    payload: CapabilityPayload = collect_capabilities()
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(render_capabilities_markdown(payload))


@cli.command()
@click.option("--instance-upgrade", is_flag=True, help="Audit engine→instance runtime adoption instead of skill lifecycle health")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def doctor(ctx, instance_upgrade: bool, fmt: str) -> None:
    """Run doctor surfaces for the current vault runtime."""
    _require_vault(ctx)
    if not instance_upgrade:
        click.echo("Error: Only --instance-upgrade is supported for this doctor surface.", err=True)
        sys.exit(1)
    payload: DoctorPayload = doctor_instance(ctx.obj["vault"])
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(render_doctor_markdown(payload))


@cli.command(name="upgrade-plan")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def upgrade_plan_command(ctx, fmt: str) -> None:
    """Show the engine→instance upgrade plan for the current vault."""
    _require_vault(ctx)
    payload: UpgradePlanPayload = build_upgrade_plan(ctx.obj["vault"])
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(render_upgrade_plan_markdown(payload))


@cli.group()
def mcp():
    """Install and inspect MCP client integrations."""
    pass


@mcp.command("install")
@click.option("--to", "target", type=click.Choice(["codex"]), required=True, help="MCP client target")
@click.option("--vault", "vault_arg", type=click.Path(path_type=Path), help="Vault root to expose through MCP")
@click.option("--name", default=DEFAULT_CODEX_MCP_NAME, show_default=True, help="MCP server name")
@click.option("--force", is_flag=True, help="Replace an existing MCP server with the same name")
@click.option("--dry-run", is_flag=True, help="Print the resulting config without writing it")
@click.option("--no-verify", is_flag=True, help="Skip MCP initialize verification after writing")
@click.option("--use-env", is_flag=True, help="Store the vault path in DISTILL_VAULT instead of args")
@click.option("--config", "config_arg", type=click.Path(path_type=Path), help="Override Codex config path")
@click.pass_context
def mcp_install(ctx, target: str, vault_arg: Path | None, name: str, force: bool, dry_run: bool, no_verify: bool, use_env: bool, config_arg: Path | None) -> None:
    """Install a distill MCP server into a client config."""
    if target != "codex":
        raise click.ClickException(f"Unsupported MCP target: {target}")
    try:
        vault_path = resolve_install_vault(vault_arg, context_vault=ctx.obj.get("vault"))
        config_path = resolve_codex_config_path(config_arg)
        result = install_codex_mcp_server(
            vault_path=vault_path,
            config_path=config_path,
            name=name,
            force=force,
            dry_run=dry_run,
            verify=not no_verify,
            use_env=use_env,
        )
    except MCPConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    if result.dry_run:
        click.echo(f"Dry run: would install Codex MCP server '{result.server_name}' at {result.config_path}")
        click.echo(result.rendered_config, nl=False)
        return

    click.echo(f"Installed Codex MCP server '{result.server_name}' at {result.config_path}")
    click.echo(f"Vault: {result.vault_path}")
    if result.backup_path is not None:
        click.echo(f"Backup: {result.backup_path}")
    click.echo(f"Verified: {'yes' if result.verified else 'skipped'}")
    click.echo("Next:")
    click.echo("  Start a new Codex session, then run:")
    click.echo(f"  distill mcp status --to codex --name {result.server_name} --verify")


@mcp.command("status")
@click.option("--to", "target", type=click.Choice(["codex"]), required=True, help="MCP client target")
@click.option("--name", default=DEFAULT_CODEX_MCP_NAME, show_default=True, help="MCP server name")
@click.option("--verify", is_flag=True, help="Start the MCP server and verify initialize")
@click.option("--config", "config_arg", type=click.Path(path_type=Path), help="Override Codex config path")
@click.pass_context
def mcp_status(ctx, target: str, name: str, verify: bool, config_arg: Path | None) -> None:
    """Show MCP client integration status."""
    if target != "codex":
        raise click.ClickException(f"Unsupported MCP target: {target}")
    try:
        config_path = resolve_codex_config_path(config_arg)
        result = get_codex_mcp_status(config_path=config_path, name=name, verify=verify)
    except MCPConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(render_status(result))


@cli.command()
@click.option("--watch", is_flag=True, help="Watch for file changes and auto-reindex")
@click.pass_context
def index(ctx, watch):
    """Build or rebuild the vault index."""
    _require_vault(ctx)
    config = load_config(ctx.obj["vault"])
    idx = VaultIndex(ctx.obj["vault"], config=config)
    idx.scan()
    idx.save()
    click.echo(idx.report())
    ops_dir = get_ops_dir(config, ctx.obj["vault"]) / "索引" if (get_ops_dir(config, ctx.obj["vault"]) / "索引").exists() else get_ops_dir(config, ctx.obj["vault"]) / "index"
    click.echo(f"\nIndex saved to: {ops_dir / 'auto-index.json'}")
    if watch:
        click.echo("\nWatching for changes... (Ctrl+C to stop)")
        _watch_index(ctx.obj["vault"])

def _watch_index(vault_path: Path):
    """Watch vault directories and auto-reindex on changes."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        click.echo("Error: watchdog not installed. Run: pip install watchdog", err=True)
        sys.exit(1)

    class ReindexHandler(FileSystemEventHandler):
        def __init__(self, vault_path):
            self.vault_path = vault_path
            self._debounce = False

        def on_any_event(self, event):
            if event.is_directory:
                return
            if not event.src_path.endswith(".md"):
                return
            if self._debounce:
                return
            self._debounce = True
            import threading
            def do_reindex():
                try:
                    idx = VaultIndex(self.vault_path)
                    idx.scan()
                    idx.save()
                    click.echo(f"[reindex] {event.src_path}")
                finally:
                    self._debounce = False
            threading.Timer(1.0, do_reindex).start()

    handler = ReindexHandler(vault_path)
    observer = Observer()
    config = load_config(vault_path)
    for d in get_scan_dirs(config, vault_path):
        if d.exists():
            observer.schedule(handler, str(d), recursive=True)
    observer.start()
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    click.echo("\nStopped watching.")


@cli.command()
@click.argument("text")
@click.option("--attachment", multiple=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def record(ctx, text, attachment, fmt):
    """Save arbitrary TEXT as a raw source without classifying or promoting it."""
    from .source_record import record_source
    _require_vault(ctx)
    try:
        payload = record_source(ctx.obj["vault"], text, attachments=list(attachment))
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Saved: {payload['source_path']}\nOriginal: {payload['raw_path']}\n{payload['recommended_commit_command']}")


@cli.command()
@click.option("--fix", is_flag=True, help="Auto-fix fixable issues")
@click.option("--staged", is_flag=True, help="Only check git staged files")
@click.option("--paths", multiple=True, help="Validate only these vault-relative files or directories")
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def lint(ctx, fix, staged, strict, fmt, paths):
    """Lint vault objects for structural issues."""
    _require_vault(ctx)
    linter = VaultLinter(ctx.obj["vault"])
    linter.scan()
    try:
        issues = linter.lint(fix=fix, staged=staged, paths=list(paths) or None)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    blocking_severities = {"error", "warning"} if strict else {"error"}
    failed = any(issue.get("severity") in blocking_severities for issue in issues)
    if fix and linter._fixes_applied:
        click.echo(click.style("\n[Auto-Fix Report]", fg="blue", bold=True))
        click.echo(linter.get_fix_report())
        click.echo()
    if fmt == "json":
        output = linter.index.status_payload()
        output.update({
            "issues": issues,
            "issue_count": len(issues),
            "fixes_applied": linter._fixes_applied if fix else [],
            "next_steps": linter.recommended_next_steps(issues),
        })
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
        if strict and failed:
            ctx.exit(1)
        return
    if not issues:
        click.echo(click.style("\u2713 No issues found", fg="green"))
        guidance = render_next_steps_markdown(linter.recommended_next_steps(issues))
        if guidance:
            click.echo()
            click.echo(guidance)
        return
    for issue in issues:
        severity = issue.get("severity", "warning")
        color = {"error": "red", "warning": "yellow", "info": "blue"}.get(severity, "white")
        click.echo(click.style(f"[{severity.upper()}] {issue['message']}", fg=color))
        if ctx.obj["verbose"]:
            click.echo(f"  File: {issue.get('file', 'N/A')}")
            click.echo(f"  Rule: {issue.get('rule', 'N/A')}")
    guidance = render_next_steps_markdown(linter.recommended_next_steps(issues))
    if guidance:
        click.echo()
        click.echo(guidance)
    if failed:
        sys.exit(1)


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.pass_context
def health(ctx, fmt, output):
    """Run health check on the vault."""
    _require_vault(ctx)
    checker = HealthChecker(ctx.obj["vault"])
    checker.scan()
    report = checker.report(fmt=fmt)
    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Health report saved to: {output}")
    else:
        click.echo(report)


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--type", "obj_type", help="Filter by object type")
@click.option("--mode", type=click.Choice(["keyword", "semantic", "hybrid"]), default="hybrid", show_default=True, help="Search mode")
@click.pass_context
def search(ctx, query, limit, obj_type, mode):
    """Search vault objects."""
    _require_vault(ctx)
    searcher = VaultSearch(ctx.obj["vault"])
    results = searcher.search(query, limit=limit, obj_type=obj_type, mode=mode)
    if not results:
        click.echo("No results found.")
        return
    click.echo(f"Found {len(results)} result(s) [{mode}]:\n")
    for r in results:
        click.echo(click.style(r["title"], fg="cyan", bold=True))
        click.echo(f"  Path: {r['path']}")
        if r.get("type"):
            click.echo(f"  Type: {r['type']}")
        if r.get("source"):
            click.echo(f"  Source: {r['source']}")
        if r.get("excerpt"):
            click.echo(f"  {r['excerpt'][:200]}...")
        click.echo()


@cli.command()
@click.argument("intent")
@click.option("--project", "project_hint", help="Optional project hint to narrow the route")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def route(ctx, intent: str, project_hint: str | None, fmt: str) -> None:
    """Plan the minimal read/write surface for a knowledge task."""
    _require_vault(ctx)
    plan: RoutePayload = route_intent(ctx.obj["vault"], intent, project_hint=project_hint)
    if fmt == "json":
        click.echo(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    click.echo(render_route_markdown(plan))


@cli.command(name="plan")
@click.argument("intent")
@click.option("--project", "project_hint", help="Optional project hint to narrow the plan")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def plan_command(ctx, intent: str, project_hint: str | None, fmt: str) -> None:
    """Return the full action plan for a knowledge task."""
    _require_vault(ctx)
    plan: PlanPayload = route_plan(ctx.obj["vault"], intent, project_hint=project_hint)
    if fmt == "json":
        click.echo(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    click.echo(render_plan_markdown(plan))


@cli.command()
@click.argument("intent")
@click.option("--project", "project_hint", help="Optional project hint to narrow the capture target")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def capture(ctx, intent: str, project_hint: str | None, fmt: str) -> None:
    """Capture a short completed fact in its source and project dossier."""
    _require_vault(ctx)
    try:
        result = capture_progress_update(ctx.obj["vault"], intent, project_hint=project_hint)
    except ValueError as exc:
        click.echo(click.style(f"Capture failed: {exc}", fg="red"), err=True)
        sys.exit(1)
    payload: ApplyPayload = build_apply_payload(result)
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(render_apply_markdown(payload, verb="Captured"))


@cli.command()
@click.argument("intent")
@click.option("--project", "project_hint", help="Optional project hint to narrow the apply target")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def apply(ctx, intent: str, project_hint: str | None, fmt: str) -> None:
    """Alias for the completed-fact capture path."""
    _require_vault(ctx)
    try:
        result = capture_progress_update(ctx.obj["vault"], intent, project_hint=project_hint)
    except ValueError as exc:
        click.echo(click.style(f"Apply failed: {exc}", fg="red"), err=True)
        sys.exit(1)
    payload: ApplyPayload = build_apply_payload(result)
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(render_apply_markdown(payload, verb="Applied"))


@cli.command(name="write-object")
@click.option("--target", required=True, help="Vault-relative markdown path to write")
@click.option("--overwrite", is_flag=True, help="Allow replacing an existing markdown file")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def write_object_command(ctx, target: str, overwrite: bool, fmt: str) -> None:
    """Write a single markdown object from stdin with vault path guards."""
    _require_vault(ctx)
    content = sys.stdin.read()
    try:
        result = write_object(ctx.obj["vault"], target, content, overwrite=overwrite)
    except (FileExistsError, OSError, ValueError) as exc:
        click.echo(click.style(f"Write failed: {exc}", fg="red"), err=True)
        sys.exit(1)

    payload = {
        "status": result.status,
        "path": result.path,
        "bytes_written": result.bytes_written,
        "sha256": result.sha256,
        "overwritten": result.overwritten,
    }
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(f"Written {result.path} ({result.bytes_written} bytes, sha256={result.sha256})")


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be promoted without doing it")
@click.option("--auto", is_flag=True, help="Auto-promote low-risk items")
@click.option("--source", help="Source or output object for an explicit semantic proposal")
@click.option("--target", help="Target concept, decision, or constraint Markdown path")
@click.option("--apply-proposal", is_flag=True, help="Apply a schema-valid explicit proposal read from stdin")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def promote(ctx, dry_run, auto, source, target, apply_proposal, fmt):
    """Review/apply one semantic proposal, or inspect discovered candidates."""
    _require_vault(ctx)
    if source or target or apply_proposal:
        if not source or not target:
            raise click.ClickException("--source and --target are required for an explicit proposal")
        content = click.get_text_stream("stdin").read()
        try:
            payload = (
                apply_promotion(ctx.obj["vault"], source=source, target=target, content=content)
                if apply_proposal
                else review_promotion(ctx.obj["vault"], source=source, target=target, content=content)
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        if fmt == "json":
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            click.echo(f"Promotion proposal: {payload['status']}")
            click.echo(f"  source: {payload['source']}")
            click.echo(f"  target: {payload['target']}")
            if payload.get("validation_errors"):
                click.echo("  blockers:")
                for item in payload["validation_errors"]:
                    click.echo(f"    - {item}")
            elif not apply_proposal:
                click.echo("  review passed; rerun with --apply-proposal to write the object and source backlink")
        return

    pipe = PromotionPipeline(ctx.obj["vault"])
    pipe.scan()
    actions = pipe.plan(auto=auto)
    if not actions:
        click.echo("Promotion queue is empty.")
        return
    if fmt == "json":
        click.echo(json.dumps(actions, ensure_ascii=False, indent=2))
        return
    for action in actions:
        click.echo(f"[{action['type']}] {action['source']} -> {action['target']}")
        if ctx.obj["verbose"]:
            click.echo(f"  Reason: {action['reason']}")
    if dry_run:
        click.echo("\n(Dry run - no changes made)")
        return
    if not auto:
        if not click.confirm("\nApply these promotions?"):
            click.echo("Cancelled.")
            return
    pipe.apply(actions)
    click.echo("Promotions applied.")


@cli.command()
@click.option("--watch", is_flag=True, help="Watch for file changes and re-run pipeline")
@click.option("--incremental", is_flag=True, help="Only run phases affected by changes")
@click.option("--workers", type=int, default=None, help="Worker process count for parallel scan/parse")
@click.option("--worker-mode", type=click.Choice(["auto", "process", "thread", "serial"]), default="auto", show_default=True, help="Execution mode for scan/parse workers (auto prefers thread; process falls back to thread on pool failure)")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def run(ctx, watch, incremental, workers, worker_mode, fmt):
    """Run the full 6-phase pipeline on the vault."""
    _require_vault(ctx)
    from .phases import build_pipeline
    
    vault = ctx.obj["vault"]
    worker_pool = WorkerPool(workers=workers, mode=worker_mode) if workers is not None else WorkerPool(mode=worker_mode)
    dag = build_pipeline(vault, worker_pool=worker_pool)
    
    if watch:
        click.echo("Starting pipeline in watch mode... (Ctrl+C to stop)")
        _watch_pipeline(vault, dag, incremental, fmt)
        return
    
    if fmt != "json":
        click.echo("Running pipeline...")
    try:
        results = dag.run(incremental=incremental)
    except Exception as e:
        click.echo(click.style(f"Pipeline failed: {e}", fg="red"), err=True)
        sys.exit(1)
    
    if fmt == "json":
        payload = dict(results)
        worker_summary = dag.worker_pool_summary()
        if worker_summary:
            payload["worker_pool"] = worker_summary
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(dag.report())
        worker_report = dag.worker_pool_report()
        if worker_report:
            click.echo()
            click.echo(worker_report)
        click.echo()
        export_paths = dag.ctx.get("export_paths", {})
        for key, path in export_paths.items():
            click.echo(f"  {key}: {path}")


def _watch_pipeline(vault, dag, incremental, fmt):
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        click.echo("Error: watchdog not installed. Run: pip install watchdog", err=True)
        sys.exit(1)
    
    class PipelineHandler(FileSystemEventHandler):
        def __init__(self):
            self._debounce = False
        
        def on_any_event(self, event):
            if event.is_directory:
                return
            if not event.src_path.endswith(".md"):
                return
            if self._debounce:
                return
            self._debounce = True
            import threading
            def do_run():
                try:
                    click.echo(f"[pipeline] Change detected: {event.src_path}")
                    dag.ctx.changed_files.append(event.src_path)
                    results = dag.run(incremental=incremental)
                    if fmt == "json":
                        payload = dict(results)
                        worker_summary = dag.worker_pool_summary()
                        if worker_summary:
                            payload["worker_pool"] = worker_summary
                        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
                    else:
                        click.echo(dag.report())
                        worker_report = dag.worker_pool_report()
                        if worker_report:
                            click.echo(worker_report)
                except Exception as e:
                    click.echo(click.style(f"[pipeline] Error: {e}", fg="red"))
                finally:
                    self._debounce = False
            threading.Timer(2.0, do_run).start()
    
    handler = PipelineHandler()
    observer = Observer()
    config = load_config(vault)
    for d in get_scan_dirs(config, vault):
        if d.exists():
            observer.schedule(handler, str(d), recursive=True)
    observer.start()
    
    # Run once immediately
    try:
        dag.run(incremental=False)
        click.echo(dag.report())
    except Exception as e:
        click.echo(click.style(f"Initial pipeline failed: {e}", fg="red"))
    
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    click.echo("\nStopped watching.")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host")
@click.option("--port", default=8420, type=int, show_default=True, help="Bind port")
@click.pass_context
def web(ctx, host, port):
    """Start the lightweight Web UI server."""
    _require_vault(ctx)
    server = DistillWebServer(ctx.obj["vault"], host=host, port=port)
    click.echo(f"Starting Web UI at http://{host}:{port}")
    server.serve_forever()


@cli.command()
@click.argument("name")
@click.option("--lang", type=click.Choice(["zh", "en"]), default="zh", show_default=True, help="Vault language")
@click.option("--examples", is_flag=True, help="Include example objects")
@click.option("--existing", is_flag=True, help="Bootstrap distill.yaml inside an existing Obsidian vault without overwriting notes")
@click.pass_context
def init(ctx, name, lang, examples, existing):
    """Initialize a new distill-vault with full skeleton."""
    from .init_cmd import init_existing_vault, init_vault
    target = Path(name)
    if existing:
        try:
            result = init_existing_vault(str(target), lang=lang)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        click.echo(f"Bootstrapped existing vault: {target}")
        click.echo(f"  Files: {result['files_created']}")
        click.echo("  Existing notes preserved")
        click.echo("\nNext steps:")
        click.echo(f"  cd {name}")
        if lang == "zh":
            click.echo("  # 先看推断出的对象层 / 输出层 / 运维层 / 系统层")
            click.echo("  distill status")
            click.echo("  # 把 lint 当成首轮图构建前的 preflight")
            click.echo("  distill lint")
            click.echo("  distill run")
            click.echo("  distill health")
        else:
            click.echo("  # Inspect the inferred object / output / ops / system roots")
            click.echo("  distill status")
            click.echo("  # Treat lint as the preflight gate before the first graph build")
            click.echo("  distill lint")
            click.echo("  distill run")
            click.echo("  distill health")
            click.echo("  # Optional: refine distill.yaml scan roots and path mappings once the first run looks right")
        return
    if target.exists() and any(target.iterdir()):
        click.echo(f"Error: {target} already exists and is not empty.", err=True)
        sys.exit(1)
    result = init_vault(str(target), lang=lang, with_examples=examples)
    click.echo(f"Initialized new vault: {target}")
    click.echo(f"  Directories: {result['dirs_created']}")
    click.echo(f"  Files: {result['files_created']}")
    click.echo("\nNext steps:")
    click.echo(f"  cd {name}")
    if lang == "zh":
        click.echo("  # 打开 README.md，先按里面的 first-win 路径跑通一轮")
        click.echo("  cat README.md")
        click.echo("  distill status")
        click.echo("  distill lint")
        click.echo("  distill run")
        if examples:
            click.echo('  distill search "知识库" --mode hybrid')
    else:
        click.echo("  # Open README.md and follow the first-win checklist")
        click.echo("  cat README.md")
        click.echo("  distill status")
        click.echo("  distill lint")
        click.echo("  distill run")
        if examples:
            click.echo('  distill search "knowledge" --mode hybrid')


@cli.group()
def skill():
    """Discover, export, and install canonical skill specs."""
    pass


@skill.command("list")
@click.pass_context
def skill_list(ctx):
    """List canonical skill specs in the vault."""
    _require_vault(ctx)
    specs = discover_skill_specs(ctx.obj["vault"])
    if not specs:
        click.echo("No skill specs found.")
        return
    for spec in specs:
        click.echo(f"{spec.name}\t{spec.path.relative_to(ctx.obj['vault'])}")


@skill.command("export")
@click.argument("name")
@click.option("--to", "target", type=click.Choice(["hermes", "codex", "claude", "all"]), required=True, help="Target skill platform")
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path("distill-skill-exports"), show_default=True, help="Directory for rendered skill artifacts")
@click.option("--stdout", "to_stdout", is_flag=True, help="Print rendered skill content instead of writing files")
@click.pass_context
def skill_export(ctx, name, target, output_dir, to_stdout):
    """Export one canonical skill spec to platform artifacts."""
    _require_vault(ctx)
    try:
        spec = get_skill_spec(ctx.obj["vault"], name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    targets = list(export_targets(target))
    if to_stdout:
        if len(targets) != 1:
            click.echo("Error: --stdout only supports a single target.", err=True)
            sys.exit(1)
        click.echo(render_skill(spec, targets[0]))
        return

    written = []
    for item in targets:
        written.append(export_skill(spec, item, output_dir))
    for path in written:
        click.echo(f"exported: {path}")


@skill.command("install")
@click.argument("name")
@click.option("--to", "target", type=click.Choice(["hermes", "codex", "claude", "all"]), required=True, help="Install target platform")
@click.option("--target-dir", type=click.Path(path_type=Path), help="Override the default install root for the chosen target")
@click.pass_context
def skill_install(ctx, name, target, target_dir):
    """Install one canonical skill spec into a platform skill directory."""
    _require_vault(ctx)
    try:
        spec = get_skill_spec(ctx.obj["vault"], name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if target == "all":
        if target_dir is not None:
            raise click.ClickException("--target-dir is not supported with --to all")
        for platform in SUPPORTED_SKILL_TARGETS:
            try:
                installed = install_skill(spec, platform)
                click.echo(f"installed: {installed}")
            except OSError as exc:
                raise click.ClickException(f"Failed to install skill '{name}' for {platform}: {exc}") from exc
        return

    try:
        installed = install_skill(spec, target, target_dir=target_dir)
    except OSError as exc:
        raise click.ClickException(f"Failed to install skill '{name}' for {target}: {exc}") from exc
    click.echo(f"installed: {installed}")


@skill.command("verify")
@click.argument("name")
@click.option("--to", "target", type=click.Choice(["hermes", "codex", "claude", "all"]), required=True, help="Verify target platform skill artifact")
@click.option("--target-dir", type=click.Path(path_type=Path), help="Override the default install/export root for the chosen target; only valid for single-target verify")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", show_default=True, help="Output format")
@click.pass_context
def skill_verify(ctx, name, target, target_dir, fmt):
    """Verify an installed/exported skill matches the rendered canonical output."""
    _require_vault(ctx)
    try:
        spec = get_skill_spec(ctx.obj["vault"], name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if target == "all":
        if target_dir is not None:
            raise click.ClickException("--target-dir is not supported with --to all")
        results = [verify_installed_skill(spec, platform) for platform in SUPPORTED_SKILL_TARGETS]
        any_failed = any(item.status != "ok" for item in results)
        if fmt == "json":
            click.echo(json.dumps(verify_many_payload(spec.name, results), ensure_ascii=False, indent=2))
            if any_failed:
                sys.exit(1)
            return
        for result in results:
            if result.status == "missing":
                click.echo(f"{result.target}: artifact missing at {result.path}")
            elif result.status == "drift":
                click.echo(
                    f"{result.target}: drift detected at {result.path} "
                    f"(expected_sha256={result.expected_sha256}, actual_sha256={result.actual_sha256})"
                )
            else:
                click.echo(f"{result.target}: verified {result.path} (sha256={result.expected_sha256})")
        if any_failed:
            sys.exit(1)
        return

    result = verify_installed_skill(spec, target, target_dir=target_dir)
    if fmt == "json":
        click.echo(json.dumps(verification_result_payload(spec.name, result), ensure_ascii=False, indent=2))
        if result.status != "ok":
            sys.exit(1)
        return
    if not result.exists:
        raise click.ClickException(
            f"Skill '{name}' artifact missing for {target} at {result.path}"
        )
    if not result.matches:
        raise click.ClickException(
            f"Skill '{name}' drift detected for {target}: {result.path} does not match rendered output "
            f"(expected_sha256={result.expected_sha256}, actual_sha256={result.actual_sha256})"
        )
    click.echo(
        f"verified: {result.path} matches rendered output "
        f"(sha256={result.expected_sha256})"
    )


@skill.command("doctor")
@click.argument("name")
@click.option("--hermes-dir", type=click.Path(path_type=Path), help="Override Hermes skill root for diagnosis")
@click.option("--codex-dir", type=click.Path(path_type=Path), help="Override Codex skill root for diagnosis")
@click.option("--claude-dir", type=click.Path(path_type=Path), help="Override Claude skill root for diagnosis")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", show_default=True, help="Output format")
@click.pass_context
def skill_doctor(ctx, name, hermes_dir, codex_dir, claude_dir, fmt):
    """Diagnose cross-platform skill artifact health."""
    _require_vault(ctx)
    try:
        spec = get_skill_spec(ctx.obj["vault"], name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    overrides = {
        "hermes": hermes_dir,
        "codex": codex_dir,
        "claude": claude_dir,
    }
    results = [
        verify_installed_skill(spec, platform, target_dir=overrides[platform])
        for platform in SUPPORTED_SKILL_TARGETS
    ]
    any_failed = any(item.status != "ok" for item in results)
    if fmt == "json":
        click.echo(json.dumps(doctor_payload(spec.name, results), ensure_ascii=False, indent=2))
        if any_failed:
            sys.exit(1)
        return
    for result in results:
        if result.status == "missing":
            click.echo(f"{result.target}: missing ({result.path})")
        elif result.status == "drift":
            click.echo(
                f"{result.target}: drift ({result.path}) "
                f"expected_sha256={result.expected_sha256} actual_sha256={result.actual_sha256}"
            )
        else:
            click.echo(f"{result.target}: ok ({result.path}) sha256={result.expected_sha256}")
    if any_failed:
        sys.exit(1)


@skill.command("reconcile")
@click.argument("name")
@click.option("--to", "target", type=click.Choice(["hermes", "codex", "claude", "all"]), required=True, help="Reconcile target platform skill artifact")
@click.option("--target-dir", type=click.Path(path_type=Path), help="Override the default install/export root for the chosen target")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing files")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", show_default=True, help="Output format")
@click.pass_context
def skill_reconcile(ctx, name, target, target_dir, dry_run, fmt):
    """Reconcile a platform skill artifact back to the canonical rendered output."""
    _require_vault(ctx)
    try:
        spec = get_skill_spec(ctx.obj["vault"], name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if target == "all":
        if target_dir is not None:
            raise click.ClickException("--target-dir is not supported with --to all")
        results = [
            reconcile_installed_skill(spec, platform, dry_run=dry_run)
            for platform in SUPPORTED_SKILL_TARGETS
        ]
        if fmt == "json":
            payload = {
                "skill": spec.name,
                "mode": "reconcile-all",
                "results": [reconcile_result_payload(r) for r in results],
            }
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for r in results:
            if r.action == "noop":
                click.echo(f"{r.target}: already aligned: {r.path}")
            elif r.action in ("install", "update"):
                click.echo(f"{r.target}: would {r.action}: {r.path}")
            else:
                click.echo(f"{r.target}: {r.action}: {r.path}")
        return

    result = reconcile_installed_skill(spec, target, target_dir=target_dir, dry_run=dry_run)
    if fmt == "json":
        click.echo(json.dumps(reconcile_result_payload(result), ensure_ascii=False, indent=2))
        return

    if result.action == "noop":
        click.echo(f"already aligned: {result.path}")
        return
    if result.action == "install":
        click.echo(f"would install: {result.path}")
        return
    if result.action == "update":
        click.echo(f"would update: {result.path}")
        return
    if result.action == "installed":
        click.echo(f"installed: {result.path}")
        return
    if result.action == "updated":
        click.echo(f"updated: {result.path}")
        return


# ── Hooks management ──────────────────────────────────────────────

@cli.group()
def hook():
    """Manage git hooks for automatic vault maintenance."""
    pass


@hook.command("install")
@click.pass_context
def hook_install(ctx):
    """Install distill-managed git hooks (pre-commit, post-commit, post-merge)."""
    _require_vault(ctx)
    from .hooks import VaultHooks
    hooks = VaultHooks(ctx.obj["vault"])
    result = hooks.install()
    if result["installed"]:
        for name in result["installed"]:
            click.echo(click.style(f"  ✓ {name} installed", fg="green"))
    if result["skipped"]:
        for name in result["skipped"]:
            click.echo(click.style(f"  ⚠ {name} skipped (existing non-distill hook)", fg="yellow"))
    if not result["installed"] and not result["skipped"]:
        click.echo("No hooks to install.")


@hook.command("uninstall")
@click.pass_context
def hook_uninstall(ctx):
    """Remove distill-managed git hooks."""
    _require_vault(ctx)
    from .hooks import VaultHooks
    hooks = VaultHooks(ctx.obj["vault"])
    result = hooks.uninstall()
    if result["removed"]:
        for name in result["removed"]:
            click.echo(click.style(f"  ✓ {name} removed", fg="green"))
    if result["not_found"]:
        for name in result["not_found"]:
            click.echo(f"  - {name} not found")


@hook.command("status")
@click.pass_context
def hook_status(ctx):
    """Show which distill git hooks are installed."""
    _require_vault(ctx)
    from .hooks import VaultHooks
    hooks = VaultHooks(ctx.obj["vault"])
    result = hooks.status()
    for name, active in result.items():
        icon = click.style("✓", fg="green") if active else click.style("✗", fg="red")
        click.echo(f"  {icon} {name}")


# ── Commit wrapper ────────────────────────────────────────────────

@cli.command("commit")
@click.argument("message")
@click.option("--push", is_flag=True, help="Push after committing")
@click.option("--no-lint", "skip_lint", is_flag=True, help="Skip lint check")
@click.option("--paths", multiple=True, help="Stage only the specified path(s); can be repeated")
@click.option("--skip-run", is_flag=True, help="Skip post-commit distill run for small scoped updates")
@click.pass_context
def distill_commit(ctx, message, push, skip_lint, paths, skip_run):
    """Lint → add → commit → optional run pipeline → optional push."""
    _require_vault(ctx)
    from .commit import DistillCommit
    dc = DistillCommit(ctx.obj["vault"])
    result = dc.commit(
        message,
        push=push,
        skip_lint=skip_lint,
        paths=list(paths) or None,
        skip_run=skip_run,
    )
    if result["success"]:
        click.echo(click.style("✓ Committed", fg="green", bold=True) + f"  {result.get('commit_hash', '')[:8]}")
        if result.get("push_success"):
            click.echo(click.style("✓ Pushed", fg="green"))
    else:
        click.echo(click.style("✗ Commit failed", fg="red", bold=True))
        if result.get("lint_issues"):
            for issue in result["lint_issues"]:
                click.echo(click.style(f"  [{issue.get('severity','error').upper()}] {issue.get('message','')}", fg="red"))
        if result.get("error"):
            click.echo(f"  {result['error']}")
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
