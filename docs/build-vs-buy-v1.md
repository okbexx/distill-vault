# Build-vs-Buy: Distill Runtime v1

## MCP

Need: stable stdio protocol, lifecycle, tools, resources, schemas, and clients.

Current project: handwritten JSON-RPC and stdio framing.

References: official Model Context Protocol Python SDK; TK CodeGraph and
loop-engineering reports.

Decision: **reuse** `mcp>=1.12.4,<2`.

Reason: protocol negotiation and transport are infrastructure. Distill owns
tool semantics only. The v1 range avoids adopting the v2 beta API during this
migration.

Verification: official client session initializes the real server, lists
tools, and calls `vault_status`.

## Object validation

Need: machine-readable object contracts with per-type required fields.

Current project: Python dictionaries and Markdown prose drift independently.

Decision: **reuse** JSON Schema Draft 2020-12 with `jsonschema>=4.23,<5`.

Reason: standard validators, reusable schemas, and precise diagnostics avoid a
custom validation language.

Verification: fixture objects and the real private acceptance vault validate through
the same linter path.

## Local graph and search projection

Need: durable object/edge projection, backlinks, traversal, and local search.

Current project: mandatory Kuzu database with full rebuilds. The upstream Kuzu
repository is archived.

References: Python stdlib SQLite 3 with FTS5; TK CodeGraph report demonstrates
the objects/edges/FTS pattern for a local agent-facing graph.

Decision: **adapt** SQLite + FTS5 using the standard `sqlite3` module.

Reason: Distill's graph is small and local. Typed adjacency queries and
recursive traversal do not require a dedicated graph server or a Cypher
runtime.

Verification: graph parity tests, FTS search tests, repeated-build byte/content
stability, and 500/5k/10k object benchmarks.

## Markdown/frontmatter

Need: preserve human-readable Obsidian-compatible documents.

Current project: `python-frontmatter` + PyYAML and a narrow wikilink extractor.

Decision: **adapt** the existing parser for v1 and centralize it behind
`VaultSnapshot`.

Reason: replacing the Markdown parser and the runtime architecture together
would obscure migration failures. AST-level Markdown parsing remains a
separate evidence-driven follow-up.

Verification: code-fence, alias, path-link, duplicate-title, and malformed
frontmatter fixtures.

## CLI and Git

Need: stable human and automation entrypoints.

Decision: **reuse** Click and the Git CLI. Split commands by adapter module only
when it reduces the current `cli.py` ownership concentration.

Reason: both are mature and already integrated. Replacing them adds no user
capability.
