# Build-vs-Buy: Knowledge Dossier Runtime v2

## Project dossier migration

Need: migrate task-oriented project metadata into completed-work knowledge dossiers.

Current project: the existing idempotent migration engine already preserves Markdown bodies, repairs frontmatter, validates JSON Schema, and writes through guarded atomic file replacement.

User references: the private acceptance vault is the validation surface; Obsidian Bases is the human browsing surface.

TK references: Tolaria confirms filesystem-first Markdown, Git audit, frontmatter conventions, and rebuildable views as the appropriate local-first kernel.

Official SDK / standard library: JSON Schema Draft 2020-12 and Obsidian Bases.

Mature OSS: existing `python-frontmatter`, PyYAML, `jsonschema`, Click, SQLite, and the official MCP SDK.

Decision: adapt the existing Distill migration, schema, CLI, MCP, and projection layers. Use Obsidian Bases directly for human views.

Reason: the change is domain semantics, not new storage, parsing, database, UI, or protocol infrastructure.

Risk: mechanical migration cannot reliably separate completed facts from mixed future-looking prose. The migration removes task fields deterministically; the private vault receives a semantic review pass afterward.

Verification: migration idempotency tests, schema validation, CLI/MCP contract tests, full Distill test suite, and the real private acceptance vault lint/run acceptance pass.
