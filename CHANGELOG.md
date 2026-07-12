# Changelog

## 1.2.0 - 2026-07-11

- Added the idempotent v3 migration for human-facing Project Handbook and Knowledge Compounding pages.
- Added opt-in presentation-contract linting with exact H2 checks and Chinese/English templates.
- Added deterministic reverse adoption projection for reused projects, non-timeline outputs, and feedback candidates.
- Changed project fact capture to prefer the Handbook `Verified Facts` section while preserving v2 compatibility.
- Changed project fact capture to preserve the Handbook's durable `summary` instead of replacing it with a single event.
- Changed completed-fact capture to create schema-complete Source objects with deterministic IDs, provenance metadata, project backlinks, and stable trailing newlines.
- Fixed `distill commit` so nested lint/run checks reuse the active Distill interpreter instead of falling back to a system Python without the package.
- Changed MCP search to return 5 results by default and bounded `object_context` relations with totals and truncation signals.
- Updated generated Skill guidance so future project and stable-knowledge assets keep the same presentation contract.

## 1.1.0 - 2026-07-11

- Added the v2 project-dossier migration: `summary`, selected `key_outputs`, normalized wikilinks, and removal of task-oriented project fields.
- Changed route/plan/apply to capture completed facts and reject schedule language from project dossiers.
- Added schema-aware semantic promotion review/apply surfaces for CLI and MCP.
- Fixed `distill promote --auto` so unsafe candidates are never auto-applied.
- Added configurable export paths and instance doctor checks for engine version/source drift.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-07-10

### Added
- Immutable `VaultSnapshot` shared across pipeline phases.
- JSON Schema Draft 2020-12 validation with instance-scoped include globs.
- Explicit, idempotent `distill migrate --to 1 [--apply]` with deterministic IDs, lifecycle normalization, relation-list repair, preview, validation, path guards, and atomic writes.
- SQLite object/typed-edge projection with FTS5 search and persisted communities at `.distill/distill.db`.

### Changed
- Replaced the archived Kuzu dependency with Python stdlib SQLite and typed graph APIs.
- Replaced handwritten JSON-RPC/stdio handling with the official Python MCP SDK v1 on both server and verification client paths.
- Unified core vault writes on guarded atomic replacement.
- Deprecated arbitrary Cypher access; `cypher_query` now supports only a small read-only compatibility set.

### Fixed
- Plain operational labels in relation fields are no longer misclassified as broken object links.
- `lint --strict` treats warnings as failures while preserving informational system-doc findings as non-blocking.

## [0.2.1] — 2025-05-03

### Added
- **Platform-differentiated skill renderers (v6)** — One canonical spec now produces structurally different outputs for Hermes (YAML frontmatter), Codex (plain instruction markdown), and Claude (@-metadata comments).
- **Batch skill operations** — `install --to all` and `reconcile --to all` deploy to all three platforms in one command.
- **Skill reconcile state machine (v5)** — Deterministic repair path: `missing → install`, `drift → update`, `ok → noop`. Supports `--dry-run` and `--format json`.
- **Skill doctor (v4)** — Cross-platform health diagnosis in one command. Reports `ok` / `drift` / `missing` per target. CI-friendly exit codes.
- **Skill verify (v3)** — Check installed artifacts match canonical render. SHA-256 integrity verification.
- **Deterministic pipeline exports** — Removed timestamps and unstable ordering from checkpoint/export outputs. Consecutive `distill run` produces identical artifacts.

### Fixed
- **setup.py dev dependencies** — Added `pytest-xdist>=3.0` so `pip install -e ".[dev]"` includes everything CI needs.
- **Obsidian health check noise** — Pseudo-links (`GitHub:`, `站点:`), attachment targets, and compatibility-layer references no longer reported as broken links.
- **Orphan false positives** — Split into `true_orphan` and `system_doc` buckets; system/runtime docs treated as informational.
- **Frontmatter check scope** — Default enforcement limited to object-layer files; system/ops/output markdown no longer flagged.
- **ops_dir self-pollution** — Pipeline export outputs under `运维/` excluded from re-scanning, preventing orphan/stats inflation.

### Changed
- **Search naming** — "Semantic Hybrid Search" → "BM25 + TF-IDF Hybrid Search" to accurately reflect the implementation (no embedding/vector search).
- **README restructured** — Focused on core value proposition ("turn vault into queryable graph"), added Limitations & Non-goals, Roadmap, and clearer Quick Start paths.
- **Hooks documentation** — Added explicit risk labels, opt-in explanation, and emergency removal instructions.

## [0.2.0] — 2025-04-28

### Added
- **Skill install (v2)** — Write rendered skills to conventional platform directories (`~/.hermes/skills/`, `~/.codex/skills/`, `~/.claude/skills/`).
- **Canonical skill specs** — Vault-native skill authoring area with sample `vault-distill-ops` spec.
- **Git hooks** — `distill hook install/uninstall/status` for pre-commit, post-commit (incremental pipeline), post-merge.
- **One-command commit workflow** — `distill commit MSG [--push] [--no-lint]`.
- **Watch mode** — Filesystem watcher with debounced pipeline re-runs (requires `watchdog`).

### Changed
- Pipeline now uses Kahn's topological sort with cycle detection.
- Parallel file parsing via Worker Pool.

## [0.1.0] — 2025-04-15

### Added
- 6-phase pipeline: Scan → Parse → Graph → Analyze → Promote → Export.
- KuzuDB graph index with objects, wikilink edges, and frontmatter associations.
- BM25 keyword search, TF-IDF cosine search, RRF-fused hybrid search.
- Community detection (label-propagation) with modularity scoring.
- Impact analysis (BFS upstream/downstream risk propagation).
- Staleness detection via content-hash checkpoints.
- Graph-assisted rename with dry-run preview.
- MCP server with 16 tools (JSON-RPC 2.0 over stdio).
- Web UI with Sigma.js graph visualization.
- CLI with JSON output support.
- Lint & auto-fix for broken links, missing frontmatter, type inference.
- Promotion pipeline for Source → Concept/Decision/Output suggestions.
