# v6: Platform-Differentiated Renderers + Batch Operations

## Problem

`render_skill()` produces nearly identical output for hermes/codex/claude.
The only difference is a prefix on the description field.  Real platform
conventions demand meaningfully different formats:

- **Hermes** reads YAML frontmatter + structured markdown sections.
- **Codex** reads instruction-style markdown without frontmatter.
- **Claude Code** reads concise instruction blocks with `@`-style metadata.

Additionally, `reconcile` and `install` only accept a single `--to` target,
while `export` and `verify` already support `--to all`.

## Changes

### 1. Platform renderers

| Target | Format |
|--------|--------|
| hermes | YAML frontmatter (name, description, version, author, license) + markdown sections with heading localization |
| codex | Plain markdown, instruction-first, no frontmatter. Each section prefixed with `##` but wrapped as agent instructions |
| claude | Concise instruction block with `@name` and `@description` metadata comments, followed by numbered rules |

`render_skill(spec, target)` dispatches to `_render_hermes()`, `_render_codex()`, `_render_claude()`.

### 2. `install --to all`

Add `"all"` to the `--to` choice for `skill install`.  Iterates all three
platforms and installs to each default directory.

### 3. `reconcile --to all`

Add `"all"` to the `--to` choice for `skill reconcile`.  Returns per-target
results in both text and JSON format.

## Test Plan

- Rendered output per platform is structurally different (hermes has frontmatter, codex doesn't, claude has @-comments)
- `install --to all` creates files in all three default dirs
- `reconcile --to all` returns combined results
- Existing tests continue to pass (backward compatibility for single-target ops)
