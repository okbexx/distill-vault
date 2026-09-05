"""Pipeline phases for distill-vault.

6-Phase Pipeline:
1. scan      - Detect file system changes
2. parse     - Parse frontmatter and content
3. graph     - Build/update the SQLite object/edge projection
4. analyze   - Broken links, orphans, type consistency
5. promote   - Suggest promotions (source -> concept/decision/output)
6. export    - Generate index, health report, promotion queue
"""

import json
import hashlib
from pathlib import Path
from collections import defaultdict

import frontmatter

from .atomic_io import atomic_write_text
from .config import get_ops_dir, get_scan_dirs, load_config
from .graph_index import GraphIndex
from .health import HealthChecker
from .index import VaultIndex
from .lint import VaultLinter
from .pipeline import PipelineDAG
from .promote import PromotionPipeline
from .snapshot import VaultSnapshot
from .vault_semantics import (
    FRONTMATTER_EDGE_TYPES,
    build_lookup_indexes,
    extract_frontmatter_links,
    extract_wikilinks,
    listify,
    source_attachment_owners,
    resolve_link_target,
)
from .worker_pool import WorkerPool


def _stable_value(value):
    if isinstance(value, dict):
        return {k: _stable_value(value[k]) for k in sorted(value)}
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, list):
        normalized = [_stable_value(item) for item in value]
        try:
            return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        except TypeError:
            return normalized
    return value


def build_pipeline(vault_root: Path, worker_pool: WorkerPool | None = None, config=None) -> PipelineDAG:
    config = config or load_config(vault_root)
    dag = PipelineDAG(vault_root, worker_pool=worker_pool, config=config)

    def _record_worker_pool_phase(ctx, phase_name: str):
        pool = getattr(ctx, "worker_pool", None)
        if not pool:
            return
        phase_map = ctx.metadata.setdefault("worker_pool_phases", {})
        phase_map[phase_name] = {
            "requested_mode": pool.mode,
            "last_mode": pool.last_mode,
            "fallback_used": bool(pool.fallback_used),
            "fallback_reason": pool.fallback_reason,
        }
        history = ctx.metadata.setdefault("worker_pool_fallback_history", [])
        reason = pool.fallback_reason
        if reason and not any(item.get("phase") == phase_name and item.get("fallback_reason") == reason for item in history):
            history.append({"phase": phase_name, "fallback_reason": reason})
    
    # Phase 1: scan
    @dag.register("scan")
    def phase_scan(ctx):
        vault = ctx.vault
        ops_dir = get_ops_dir(ctx.config, vault)
        all_files = []
        seen = set()
        for d in get_scan_dirs(ctx.config, vault):
            for path in d.rglob("*.md"):
                resolved = path.resolve()
                if (resolved in seen or not resolved.is_relative_to(vault.resolve())
                        or resolved != path.absolute()
                        or ops_dir.resolve() in resolved.parents):
                    continue
                seen.add(resolved)
                all_files.append(path)
        
        ctx.set("all_files", all_files)
        ctx.set("file_count", len(all_files))
        
        # Compute content hash for incremental
        if ctx.worker_pool:
            hashes = ctx.worker_pool.hash_files(all_files, vault)
            if ctx.worker_pool.failures:
                ctx.set("hash_failures", list(ctx.worker_pool.failures))
        else:
            hashes = {}
            for f in all_files:
                try:
                    hashes[str(f.relative_to(vault))] = hashlib.md5(
                        f.read_bytes()
                    ).hexdigest()
                except Exception:
                    pass
        ctx.set("file_hashes", hashes)
        _record_worker_pool_phase(ctx, "scan")
        
        dag.phases["scan"].objects_processed = len(all_files)
    
    # Phase 2: parse
    @dag.register("parse", deps=["scan"])
    def phase_parse(ctx):
        files = ctx.get("all_files", [])
        # Original Markdown must never enter the frontmatter worker parser.
        attachment_owners = source_attachment_owners(
            ctx.vault, (str(path.relative_to(ctx.vault)) for path in files))
        files = [path for path in files if str(path.relative_to(ctx.vault)) not in attachment_owners]
        wikilinks = defaultdict(list)
        
        if ctx.worker_pool:
            objects = ctx.worker_pool.parse_files(files, ctx.vault)
            if ctx.worker_pool.failures:
                ctx.set("parse_failures", list(ctx.worker_pool.failures))
            for obj in objects:
                for link in obj.get("wikilinks", []):
                    wikilinks[obj["path"]].append(link)
        else:
            objects = []
            for path in files:
                try:
                    post = frontmatter.load(str(path))
                    rel = str(path.relative_to(ctx.vault))
                    obj = {
                        "path": rel,
                        "title": post.get("title", path.stem),
                        "type": post.get("type", "unknown"),
                        "status": post.get("status", "unknown"),
                        "frontmatter": dict(post.metadata),
                        "content": post.content,
                    }
                    objects.append(obj)
                    
                    # Extract wikilinks from content
                    links = extract_wikilinks(post.content)
                    links.extend(extract_frontmatter_links(dict(post.metadata), include_plain_strings=True))

                    for link in links:
                        wikilinks[rel].append(link)
                    
                except Exception:
                    continue
        
        objects.extend({"path": path} for path in attachment_owners
                       if path in {str(p.relative_to(ctx.vault)) for p in ctx.get("all_files", [])})
        snapshot = VaultSnapshot.from_objects(ctx.vault, objects, config=ctx.config)
        objects = [obj.as_dict(include_content=True) for obj in snapshot.objects]
        wikilinks = {obj.path: list(obj.links) for obj in snapshot.objects}
        ctx.set("objects", objects)
        ctx.set("wikilinks", wikilinks)
        ctx.set("object_count", len(objects))
        ctx.set("snapshot", snapshot)
        _record_worker_pool_phase(ctx, "parse")
        dag.phases["parse"].objects_processed = len(objects)
    
    # Phase 3: graph
    @dag.register("graph", deps=["parse"])
    def phase_graph(ctx):
        gi = GraphIndex(ctx.vault)
        graph_stats = gi.build(ctx.get("snapshot"))
        ctx.set("graph_index", gi)
        ctx.set("graph_stats", graph_stats)
        dag.phases["graph"].objects_processed = graph_stats["nodes"]
    
    # Phase 4: analyze
    @dag.register("analyze", deps=["graph"])
    def phase_analyze(ctx):
        gi = ctx.get("graph_index")
        
        # Orphans: align with VaultIndex semantics (no incoming and no outgoing resolved links)
        # Exported 运维 artifacts are derived outputs and should not feed back into health calculations.
        indexed = VaultIndex(ctx.vault, config=ctx.config, snapshot=ctx.get("snapshot"))
        indexed.scan()
        orphans = [(path, indexed._path_index[path].get("title", Path(path).stem)) for path in indexed.orphans]
        orphan_buckets = {
            bucket: [
                (path, indexed._path_index[path].get("title", Path(path).stem))
                for path in paths
            ]
            for bucket, paths in indexed.orphan_buckets.items()
        }

        # Broken links: not in graph (we need to compare wikilinks vs resolved)
        # For now, use VaultLinter as fallback for detailed analysis
        linter = VaultLinter(ctx.vault, config=ctx.config, snapshot=ctx.get("snapshot"))
        linter.scan()
        issues = linter.lint()
        
        # Type distribution
        type_dist = gi.type_distribution()
        
        ctx.set("orphans", orphans)
        ctx.set("orphan_buckets", orphan_buckets)
        ctx.set("issues", issues)
        ctx.set("type_distribution", type_dist)
        ctx.set("issue_count", len(issues))
        dag.phases["analyze"].objects_processed = len(orphans) + len(issues)
    
    # Phase 5: promote
    @dag.register("promote", deps=["analyze"])
    def phase_promote(ctx):
        pipe = PromotionPipeline(ctx.vault, config=ctx.config, snapshot=ctx.get("snapshot"))
        pipe.scan()
        actions = pipe.plan()
        
        ctx.set("promotion_actions", actions)
        ctx.set("promotion_count", len(actions))
        dag.phases["promote"].objects_processed = len(actions)
    
    # Phase 6: export
    @dag.register("export", deps=["promote"])
    def phase_export(ctx):
        vault = ctx.vault
        ops_dir = get_ops_dir(ctx.config, vault)

        checker = HealthChecker(vault, config=ctx.config, snapshot=ctx.get("snapshot"))
        checker.scan()
        checker.index._has_checkpoint_override = True

        # Save JSON index using the shared runtime/index contract.
        export_config = ctx.config.get("exports", {})
        idx_path = _configured_export_path(
            vault,
            export_config.get("index_path"),
            ops_dir / "索引" / "auto-index.json",
        )
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            idx_path,
            json.dumps(checker.index.auto_index_payload(), indent=2, ensure_ascii=False, sort_keys=True),
            root=vault,
        )

        # Save health report using the shared health surface contract.
        health_path = _configured_export_path(
            vault,
            export_config.get("health_path"),
            ops_dir / "健康检查" / "health-report.md",
        )
        atomic_write_text(health_path, checker.report(), root=vault)

        ctx.set("export_paths", {
            "index": str(idx_path),
            "health": str(health_path),
        })
        dag.phases["export"].objects_processed = 2
    
    return dag


def _configured_export_path(vault: Path, configured: str | None, default: Path) -> Path:
    """Resolve an instance-owned export path; atomic writes enforce the vault boundary."""
    if not configured:
        return default
    return vault / configured
