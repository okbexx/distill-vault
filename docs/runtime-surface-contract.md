# Runtime Surface Contract

`distill-vault` exposes a shared runtime contract for minimal knowledge-task operations through `distill.routing`.

This contract is consumed by both CLI and MCP surfaces so external agents do not have to reverse-engineer per-entrypoint payload differences.

## Three surfaces

### 1. Compact route
- CLI: `distill route`
- MCP: `projection_route`
- Purpose: minimal read/write boundary discovery
- Shape owner: `build_route_payload(plan)`
- Text renderer: `render_route_markdown(payload)`

Compact route stays intentionally low-noise. It returns the minimal route boundary plus `recommended_commit_*` guidance, but does **not** include `action` or `status`.

Stable compact-route fields:
- `intent`
- `operation`
- `confidence`
- `target_project`
- `read_paths`
- `write_paths`
- `optional_paths`
- `skip_steps`
- `recommended_commit_paths`
- `recommended_commit_message`
- `recommended_commit_command`
- `why`
- `warnings`

### 2. Full plan
- CLI: `distill plan`
- MCP: `projection_plan`
- Purpose: structured machine-facing action plan
- Shape owner: `build_plan_payload(...)`
- Text renderer: `render_plan_markdown(payload)`

Full plan extends the compact route with normalized planning semantics:
- deterministic completed-fact capture -> `action=knowledge_capture`, `status=planned`
- generic fallback / ambiguous target → `action=generic_update`, `status=needs_disambiguation`

Stable full-plan fields:
- `action`
- `status`
- `intent`
- `operation`
- `confidence`
- `target_project`
- `read_paths`
- `write_paths`
- `optional_paths`
- `skip_steps`
- `recommended_commit_paths`
- `recommended_commit_message`
- `recommended_commit_command`
- `why`
- `warnings`

### 3. Applied result
- CLI: `distill capture`
- CLI: `distill apply`
- MCP: `projection_apply`
- Purpose: execution result after the minimal write path runs
- Shape owner: `build_apply_payload(result)`
- Text renderer: `render_apply_markdown(payload, verb=...)`

Applied results currently use:
- `action=knowledge_capture`
- `status=applied`

Stable applied-result fields:
- `action`
- `status`
- `operation`
- `source_path`
- `project_path`
- `touched_paths`
- `recommended_commit_paths`
- `recommended_commit_message`
- `recommended_commit_command`

## Shared JSON contract rule

CLI and MCP must not hand-assemble near-duplicate route/plan/apply payloads.

Any new route/plan/apply field must be added centrally in `distill.routing` shared builders, then consumed unchanged by:
- CLI JSON surfaces
- MCP surfaces

That keeps runtime semantics from drifting across entrypoints.

## Shared markdown contract rule

CLI markdown/text surfaces must come from shared renderers in `distill.routing`, not per-command `click.echo(...)` formatting.

That keeps human-facing output aligned with the same contract used by machine-facing JSON surfaces.

## Integration guidance

Use:
- `route` / `projection_route` when you want the smallest possible boundary-discovery payload
- `plan` / `projection_plan` when you want the richer machine contract with normalized `action/status`
- `apply` / `projection_apply` when you want the execution result after the write path runs

## Compatibility rule for future work

When extending the runtime surface:
1. Keep `route` compact unless there is a strong reason not to.
2. Add richer machine-contract fields to `plan`, not `route`.
3. Keep apply/capture result payloads aligned with plan action naming.
4. If CLI and MCP start diverging, fix the shared builders/renderers first rather than patching callsites independently.
