# Distill Runtime Architecture v1

## Product boundary

Distill is the deterministic runtime for a local-first Markdown knowledge
vault. The vault remains the source of truth; every database, checkpoint, and
search index under `.distill/` is a rebuildable projection.

The runtime is split into four layers:

1. **Vault contract**: Markdown/frontmatter objects, instance configuration,
   JSON Schema, lifecycle, and relation policy.
2. **Core services**: one immutable `VaultSnapshot`, validation, indexing,
   search, health, projection planning, and guarded writes.
3. **Projection storage**: SQLite tables for objects and edges plus FTS5 for
   local search. The database is disposable and versioned.
4. **Adapters**: Click CLI, official Python MCP SDK, optional Git integration,
   and the experimental Web UI.

## Invariants

- Markdown and Git are authoritative; SQLite is never an independent source.
- A vault scan parses each Markdown file at most once per operation.
- Object identity comes from `id`; path is the fallback identity during legacy
  migration. Duplicate titles never resolve silently.
- Instance policy belongs in the vault, not in the generic engine.
- Every write has a plan or explicit target, stays inside the vault root,
  validates against the instance schema, and is applied atomically.
- CLI and MCP call the same core services and return the same structured
  payloads.
- Derived runtime artifacts do not feed back into future scans.

## User path

The normal path is:

1. `distill status` or MCP `vault_status` checks the current runtime.
2. `distill search` / MCP `search` finds relevant objects with provenance.
3. `distill plan` / MCP `projection_plan` previews a knowledge write.
4. `distill apply` / MCP `projection_apply` applies an explicit low-risk plan.
5. `distill lint` verifies schema, links, and object health.

Migration is explicit:

```bash
distill migrate --to 1
distill migrate --to 1 --apply
distill run
distill lint --strict
```

## Compatibility

- Existing `distill.yaml` files remain valid.
- Vaults without a schema continue in legacy mode and receive a doctor action.
- The Kuzu graph is replaced by `.distill/distill.db`. It is rebuildable, so no
  user-authored data migration is required.
- The old public Cypher tool is deprecated because an archived database engine
  must not remain part of the stable contract. Typed graph tools remain.
