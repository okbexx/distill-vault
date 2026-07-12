# distill-vault

**Turn your Obsidian vault into a queryable knowledge graph.**

> Read vault files → build object graph → search, analyze, and let AI agents query it.

`distill-vault` is a CLI + library that reads an Obsidian-compatible vault, builds a
structured SQLite + FTS5 object/edge projection, and gives you search, health checks, impact analysis,
and a full MCP server so AI agents can treat your vault as a **runtime knowledge backend** —
not just a folder of markdown files.

**Recommended path:**

```
distill status                 → inspect current vault shape
distill lint                   → clear structural blockers first
distill migrate --to 1        → preview legacy metadata normalization
distill migrate --to 2        → preview project-dossier migration
distill migrate --to 3        → preview human-facing project and knowledge presentation migration
distill run                    → build the graph and checkpoint
distill search "query"         → search it
python -m distill.mcp_server   → expose to AI agents
```

Worker-pool execution on `distill run` is explicit and observable:

- `--worker-mode auto` → safety-first default; prefers `thread` when parallel workers are available
- `--worker-mode process` → tries process workers first, then falls back to `thread` if the pool fails to start or crashes
- `--worker-mode thread` / `serial` → force the execution strategy for debugging or deterministic runs
- `distill run --format json` exposes `worker_pool.requested_mode`, `last_mode`, `fallback_used`, `fallback_reason`, and per-phase scan/parse details
- markdown `distill run` prints a `[Worker Pool]` section with the same runtime truth

Runtime stages exposed by `status` / `health` JSON surfaces:

- `preflight` — no checkpoint yet; treat lint as the first gate before trusting graph-derived output
- `needs_attention` — checkpoint exists, but broken links or true orphans mean the runtime view needs repair
- `trusted_runtime` — checkpoint exists and the current scan is free of broken links and true orphans

Everything else (hooks, skill system, web UI, git integration) is for when you're ready to go deeper.

---

## Quick Start

### Start a new vault from scratch

```bash
git clone https://github.com/okbexx/distill-vault.git
cd distill-vault
pip install -e .

distill init my-vault --lang zh --examples
cd my-vault
cat README.md              # generated first-win checklist
distill status             # inspect example objects
distill lint               # structural sanity check
distill run                # build graph + derived artifacts
distill search "知识库" --mode hybrid
```

### Point at an existing Obsidian vault

```bash
# From the distill-vault repo root
pip install -e .

# Point at your Obsidian vault
cd ~/my-obsidian-vault
distill status --format json   # runtime_stage + vault_layout + next_steps
# optional but recommended for existing vaults without distill.yaml:
distill init . --existing      # persist inferred scan roots + runtime dirs
distill migrate --to 1         # preview IDs, lifecycle, and type normalization
distill migrate --to 1 --apply # validate and atomically apply the plan
distill migrate --to 2         # preview completed-work project dossiers
distill migrate --to 2 --apply # remove task fields and compact project outputs
distill migrate --to 3 --apply # add project handbooks and knowledge-compounding lifecycle pages
distill lint --format json     # issues + runtime surface + suggested next actions
distill run                    # build graph (first run)
distill health --format json   # confirm the runtime has reached a trusted state
distill search "知识管理" --mode hybrid
```

### Inspect engine → instance upgrade readiness

```bash
# What this distill engine supports right now
distill capabilities --format json

# Does this vault still run on legacy small-task guidance?
distill doctor --instance-upgrade --format json

# Minimal adoption checklist for this vault
distill upgrade-plan --format json
```

**For contributors:**

```bash
pip install -e ".[dev]"
scripts/run_tests.sh tests/ -q    # repo-local venv-aware pytest entrypoint
```

---

## What it does

**One-line summary:** Scan → Parse → Graph → Analyze → Export — a 6-phase pipeline that turns markdown files into a graph database you can search, analyze, and expose to AI agents.

| Layer | What | Why it matters | Status |
|-------|------|----------------|--------|
| **Pipeline** | 6-phase DAG with incremental checkpoints | Only re-indexes what changed; seconds even on large vaults | ✅ Stable |
| **Graph** | SQLite objects + typed edges + FTS5 | Disposable local projection with typed adjacency queries | ✅ Stable |
| **Search** | BM25 + TF-IDF cosine + RRF-fused hybrid | Three modes: keyword, similarity, or fused | ✅ Stable |
| **Analytics** | Community detection, impact analysis, staleness | Understand structure, not just content | ✅ Stable |
| **Lint & Health** | Structural checks, broken-link detection, orphan classification | Catch issues before they compound | ✅ Stable |
| **MCP Server** | 22 tools via the official Python MCP SDK | Codex / Claude / Cursor / Hermes can query your vault directly | ✅ Stable |
| **Skill System** | Canonical spec → 3 platform renderers (79 tests) | Write once, deploy to Hermes / Codex / Claude | ✅ Stable |
| **Web UI** | Sigma.js graph visualization + 8 API endpoints (46 tests) | Explore the graph in your browser | ✅ Stable |
| **Git Hooks** | Pre-commit lint, post-commit pipeline, post-merge refresh | Automate vault maintenance on every commit | ✅ Stable |
| **Watch Mode** | Filesystem watcher for live re-indexing | Hands-off pipeline on every file change | ⚠️ Experimental |

---

## Advanced Usage

```bash
# Incremental re-index (only changed files)
distill run --incremental

# Force a deterministic serial run
distill run --worker-mode serial

# Inspect worker-pool runtime truth in JSON
distill run --format json

# Web UI (✅ Stable — 46 tests + 8 API endpoints)
distill web --port 8420

# MCP server (for AI agent integration)
python -m distill.mcp_server --vault ~/my-vault

# Skill lifecycle (v6)
distill skill list
distill skill export my-skill --to hermes
distill skill install my-skill --to all
distill skill doctor
distill skill reconcile my-skill --to all
```

---

## Architecture

```
                    ┌──────────────────────────────────┐
                    │       CLI / Web / MCP / Skill     │
                    └────────────┬─────────────────────┘
                                 │
                    ┌────────────▼─────────────────────┐
                    │        Pipeline DAG Engine        │
                    │  (Kahn's Topo Sort + Incremental) │
                    └────────────┬─────────────────────┘
                                 │
          ┌──────────┬───────────┼───────────┬──────────┐
          │          │           │           │          │
     ┌────▼───┐ ┌───▼───┐ ┌────▼───┐ ┌────▼───┐ ┌───▼────┐
     │  Scan  │ │ Parse │ │ Graph  │ │Analyze │ │Export  │
     │+ Hash  │ │+ Pool │ │SQLite  │ │+Linter │ │+Report │
     └────────┘ └───────┘ └────┬───┘ └────────┘ └────────┘
                                │
                    ┌───────────▼───────────────────────┐
                    │    SQLite Object/Edge Projection   │
                    │  ┌────────┐    ┌────────────────┐  │
                    │  │ Object │◄──►│     Links      │  │
                    │  │ Nodes  │    │ (wikilink/fm)  │  │
                    │  └────────┘    └────────────────┘  │
                    └───────────┬───────────────────────┘
                                │
          ┌──────────┬──────────┼──────────┬──────────┬──────────┐
          │          │          │          │          │          │
     ┌────▼────┐ ┌──▼───┐ ┌───▼────┐ ┌───▼───┐ ┌───▼────┐ ┌───▼──────────┐
     │ Hybrid  │ │Comm- │ │Impact  │ │Rename │ │MCP     │ │Skill System  │
     │ Search  │ │unity │ │Analysis│ │Graph  │ │16 Tools│ │Spec→Render   │
     │BM25+TF  │ │Label │ │BFS     │ │Smart  │ │        │ │Hermes|Codex  │
     │         │ │      │ │        │ │       │ │        │ │Claude        │
     └─────────┘ └──────┘ └────────┘ └───────┘ └────────┘ └──────────────┘
```

---

## CLI Reference

### Core commands

| Command | Description |
|---|---|
| `distill status` | Vault overview & statistics |
| `distill migrate --to 1\|2\|3 [--apply]` | Preview / apply object-contract migrations; v2 creates completed-work dossiers, v3 adds human-facing project handbooks and knowledge-compounding pages |
| `distill run [--incremental] [--watch] [--workers N] [--worker-mode auto\|process\|thread\|serial]` | Build / refresh graph with observable worker-pool runtime |
| `distill search QUERY [--mode hybrid\|keyword\|semantic]` | Search vault objects |
| `distill lint [--fix]` | Check / auto-fix structural issues |
| `distill health` | Full health report |
| `distill promote [--dry-run]` | Discover promotion candidates; `--auto` applies only explicitly safe actions |
| `distill promote --source PATH --target PATH [--apply-proposal]` | Review or explicitly apply an agent-authored semantic proposal from stdin |
| `distill index [--watch]` | Build / rebuild index |

### Skill lifecycle ✅ Stable

| Command | Description |
|---|---|
| `distill skill list` | List canonical skill specs in vault |
| `distill skill export NAME --to TARGET` | Render to Hermes / Codex / Claude format |
| `distill skill install NAME --to TARGET` | Install rendered skill (`--to all` for batch) |
| `distill skill verify NAME --to TARGET` | Check installed artifact matches canonical |
| `distill skill doctor` | Cross-platform health diagnosis |
| `distill skill reconcile NAME --to TARGET` | Detect drift & repair (`--to all`, `--dry-run`) |

### Git integration ✅ Stable

> ⚠️ **Hooks modify your git workflow.** These are opt-in and can be removed with `distill hook uninstall`. Current behavior: pre-commit blocks only **staged error-level issues**; warnings are shown but do not block commit. post-commit runs incremental indexing in the background; post-merge runs a full refresh.

For small completed-fact captures, prefer the minimal runtime path instead of the full maintenance loop. Schedule language such as next steps, plans, and pending work is rejected from project dossiers:

```bash
distill route "记录激光雷达已完成 UAT 发布并通过验证" --format json
distill plan "记录激光雷达已完成 UAT 发布并通过验证" --format json
distill capture "记录激光雷达已完成 UAT 发布并通过验证"
distill commit "knowledge fact capture" --paths 知识/来源/2026-05-12-碎碎念.md --paths 知识/项目/激光雷达.md --skip-run
```

`distill route --format json` stays compact: it returns the minimal read/write surface plus `recommended_commit_*`, but does not add extra `action/status` wrapper fields. `distill plan --format json` is the fuller action-plan payload with `action`, `status`, `read_paths`, `write_paths`, `skip_steps`, and `recommended_commit_*`. The normalized `action/status` naming is used by `distill plan`, `distill capture`, `distill apply`, MCP `projection_plan`, and MCP `projection_apply`.

## Shared Runtime Surface Contract

The route / plan / apply surfaces are backed by a shared runtime contract in `distill.routing`.

- Shared JSON builders:
  - `build_route_payload(plan)`
  - `build_plan_payload(...)`
  - `build_apply_payload(result)`
- Shared markdown renderers:
  - `render_route_markdown(payload)`
  - `render_plan_markdown(payload)`
  - `render_apply_markdown(payload, verb=...)`

Contract layers:
- **route / projection_route** → compact boundary discovery, intentionally no `action` / `status`
- **plan / projection_plan** → full machine contract with normalized `action` / `status`
- **capture/apply / projection_apply** → execution result with normalized `action` / `status`

Any new route/plan/apply field should be added centrally through the shared builders in `distill.routing`, then consumed unchanged by CLI and MCP surfaces.

For the fuller integration-oriented contract, see `docs/runtime-surface-contract.md`.

MCP clients can use the same surfaces via `projection_route`, `projection_plan`, and `projection_apply`.

| Command | Description |
|---|---|
| `distill hook install` | Install git hooks (see warning above) |
| `distill hook uninstall` | Remove all distill-managed hooks |
| `distill hook status` | Show hook installation status |
| `distill commit MSG [--push] [--no-lint]` | Lint → add → commit → pipeline → push |

All commands support `--format json` for machine-readable output.

`distill run` runtime surfaces now expose the worker-pool execution contract too:

- markdown output adds a `[Worker Pool]` block after the phase report
- JSON output adds a `worker_pool` object with `requested_mode`, `last_mode`, `fallback_used`, `fallback_reason`, and per-phase `scan` / `parse` mode snapshots
- MCP `pipeline_run` and `pipeline_status` return the same `worker_pool` object

JSON status-style surfaces now share the same runtime contract:

- `distill status --format json`
- `distill health --format json`
- `distill lint --format json`
- MCP `vault_status`
- MCP `lint_check` / `lint_fix`

Shared fields include:

- `runtime_stage`
- `has_checkpoint`
- `scan_roots`
- `vault_layout`
- `next_steps`

For MCP `vault_status`, the nested `health.level` now tracks *broken links + true orphans* rather than all orphan-like files, so system/runtime/skill docs can remain informational without making a clean runtime look degraded. The nested payload also exposes `reason` (`clean_runtime`, `minor_runtime_issues`, `blocking_runtime_issues`) plus `signals` for `broken_links`, `orphan_objects`, `true_orphans`, and `system_docs`.

### Skill system details

#### v6: Platform-differentiated renderers

Each target platform receives a structurally different rendered output from one canonical spec:

| Target | Format |
|---|---|
| **hermes** | YAML frontmatter (`name`, `description`, `version`) + localized markdown sections |
| **codex** | Plain instruction markdown with `<!-- Codex skill: name -->` comment |
| **claude** | `<!-- @name -->` / `<!-- @description -->` metadata comments + concise numbered rules |

Batch operations:
- `distill skill install NAME --to all` — install to all three platform dirs
- `distill skill reconcile NAME --to all` — batch reconcile (supports `--dry-run`, `--format json`)

#### v5: Reconcile state machine

`reconcile` models three explicit artifact states:
- `missing` → install
- `drift` → update
- `ok` → noop

`--dry-run` reports what would change without writing files. JSON mode distinguishes `after` (actual write) from `desired_after` (dry-run plan).

#### v4: Doctor

```bash
distill skill doctor my-skill              # human-readable
distill skill doctor my-skill --format json  # CI-friendly
```

Reports each target as `ok`, `drift`, or `missing`. Exits non-zero when any target has issues.

#### v3: Verify

```bash
distill skill verify my-skill --to hermes
distill skill verify my-skill --to all --format json
```

Checks for missing files and content drift. Returns SHA-256 digests for integrity verification.

### Lint semantics

- `system_doc` orphans are treated as **informational**, not actionable warnings.
- Frontmatter completeness is enforced for object-layer paths (e.g. `知识/概念/*`) by default, not for system/ops/output markdown.
- Stricter enforcement via `lint.frontmatter_required_globs` in `distill.yaml`:

```yaml
lint:
  frontmatter_required_globs:
    - "知识/**/*.md"
    - "系统/规范/*.md"
```

---

## MCP Tools (24)

| Tool | Description |
|---|---|
| `vault_status` | Vault overview & graph stats |
| `vault_staleness` | Check if index is stale |
| `search` | Hybrid search (BM25 + TF-IDF + RRF fusion), defaulting to 5 results for agent context efficiency |
| `cypher_query` | Deprecated limited read-only compatibility queries |
| `object_context` | Object metadata plus bounded in/out refs, relation totals, and truncation signals |
| `list_objects` | List/filter vault objects |
| `impact_upstream` | What depends on this object? |
| `impact_downstream` | What does this object depend on? |
| `detect_changes` | Analyze uncommitted changes |
| `community_detect` | Run community detection |
| `community_info` | Get community details |
| `rename` | Graph-assisted smart rename |
| `lint_check` | Check for issues |
| `lint_fix` | Auto-fix issues |
| `pipeline_run` | Trigger main pipeline execution with MCP-friendly results |
| `pipeline_status` | Get main-pipeline checkpoint + staleness summary |

---

## Obsidian-Aware Health Semantics

- **Broken-link de-noising** — Ignores pseudo-links (`GitHub:`, `站点:`, `报告:`, etc.)
- **Attachment-aware linting** — `.html`, images, docs, media treated as normal attachments, not missing objects
- **Compatibility-link tolerance** — `兼容层/...` references excluded from broken-object checks
- **Orphan buckets** — Splits into `true_orphan` and `system_doc`
- **Scoped frontmatter checks** — Defaults to object-layer files only

---

## Tested & Proven

- **Python 3.10+** (CI: 3.10 / 3.11 / 3.12)
- **SQLite 3 + FTS5** through Python's standard library
- **Official Python MCP SDK v1** for protocol lifecycle and stdio transport
- **Real private acceptance vault benchmark:**

| Operation | Time |
|-----------|------|
| Full pipeline (6 phases) | **0.70s** |
| Hybrid search | **0.66s** |
| Health check | **0.39s** |

- **full test suite passing locally** — covers hooks, commit, config, init, pipeline, skill v1–v6, platform renderers
- **repo-local test entrypoint** — `scripts/run_tests.sh ...` activates the project venv when present, then runs `python3 -m pytest`
- **CI** — GitHub Actions on every push/PR, 3 Python versions

---

## Limitations & Non-goals

### Current limitations

- **No vector/embedding search.** The "semantic" mode uses TF-IDF cosine similarity, not embedding-based vector search. This works well for structured knowledge bases but may miss nuanced semantic matches that dense embeddings catch.
- **Single-vault only.** One `distill run` operates on one vault directory. Multi-vault federation is not supported.
- **SQLite is a rebuildable local projection, not the source of truth.** Markdown and Git remain authoritative; `.distill/distill.db` can always be deleted and rebuilt.
- **Vault size sweet spot: ~1,000–5,000 markdown files.** Tested at 234 objects with good performance. Very large vaults (10k+ files) will work but haven't been benchmarked for latency.
- **Obsidian-specific.** Wikilink parsing and frontmatter conventions follow Obsidian's format. Other markdown-based systems (Foam, Logseq) may work partially but aren't explicitly supported.
- **Watch mode is experimental.** `distill run --watch` uses filesystem watching (requires `watchdog`) but hasn't been stress-tested under heavy concurrent edits.
- **Web UI is minimal.** Sigma.js visualization for exploring the graph. Not a full vault management interface.

### Non-goals (what this project intentionally does NOT do)

- **Not a note-taking app.** distill-vault reads and analyzes; it doesn't replace Obsidian or your editor.
- **Not a general-purpose graph database.** Distill exposes typed knowledge operations instead of arbitrary SQL or a graph query language.
- **Not a replacement for Obsidian plugins.** It complements Obsidian by adding graph analytics and AI agent integration that runs outside the editor.
- **No built-in LLM/AI.** The MCP server exposes tools for AI agents to call, but distill-vault itself doesn't call any LLM.
- **No real-time sync.** Changes are picked up on the next `distill run` or via watch mode, not via live filesystem events pushed to the graph.

---

## Roadmap

### Near-term
- **Embedding-based vector search** — Add optional dense retrieval alongside BM25/TF-IDF for true semantic search
- **Benchmark suite** — Performance numbers at 1k / 5k / 10k files
- **CI hardening** — Coverage reporting, lint gate, multi-OS matrix

### Medium-term
- **Multi-vault federation** — Query across multiple vaults from a single graph
- **Plugin API** — Custom phases, linters, and renderers as pluggable extensions
- **Web UI v2** — Search, health dashboard, and community explorer in the browser

### Long-term
- **Collaborative vaults** — Merge graphs from multiple contributors
- **CI/CD integration examples** — Pre-built GitHub Actions for vault health checks

---

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history.

---

## License

MIT
