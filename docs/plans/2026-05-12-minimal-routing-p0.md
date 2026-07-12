# distill-vault Minimal Routing P0 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a first-class minimal routing surface so distill-vault can tell an agent the smallest read/write set for a short knowledge operation, and support path-scoped commit flow for those small tasks.

**Architecture:** Introduce a lightweight routing module that classifies a user intent into a task kind and returns a deterministic plan: files to read, files to write, optional files, and heavy steps to skip. Surface that plan in both CLI (`distill route`) and MCP (`projection_route`). Then extend the commit wrapper so the route plan can be executed safely with path-scoped staging instead of `git add -A`.

**Tech Stack:** Python 3, Click CLI, existing distill index/config helpers, MCP tool registry, pytest, click.testing.CliRunner.

---

## Problem Statement

Today distill-vault has strong vault inspection and pipeline primitives (`status`, `lint`, `run`, `health`, MCP status/search/impact), but it does not expose a task-routing/runtime surface that answers: for this specific request, what is the minimal file set to read, what is the minimal file set to write, and which heavy maintenance steps can be skipped.

That gap makes tiny capture tasks expensive. Agents have to re-read broad docs or inspect unrelated files just to record one project update. The repo also lacks a safe scoped-commit path: `distill commit` always stages `git add -A` and runs the heavy post-commit pipeline path, which is overkill for short note captures and dangerous when the working tree already contains unrelated edits.

## Solution

Ship a P0 routing/runtime slice with two concrete capabilities:

1. `distill route <intent>` / MCP `projection_route` — deterministic route planning for small operations, especially project progress capture.
2. `distill commit --paths ... [--skip-run]` — path-scoped commit execution so the route plan can be applied without widening staging or forcing a full maintenance path.

The first release intentionally stays narrow: optimize the most painful small task, "record this project progress update", rather than trying to auto-edit files or solve every ingest category at once.

## User Stories

1. As an agent, I want to pass a short intent like “记录一下激光雷达今天进展” and immediately receive a minimal read/write plan, so that I do not need to inspect unrelated files.
2. As an operator, I want the route plan to tell me which maintenance steps can be skipped, so that tiny writes finish in minutes rather than invoking a full vault maintenance loop.
3. As an agent, I want the route output in CLI JSON, so that I can consume it programmatically.
4. As an MCP client, I want a `projection_route` tool, so that routing is part of the runtime rather than hidden in docs.
5. As a user with a dirty working tree, I want `distill commit` to stage only specified paths, so that unrelated modifications are not accidentally committed.
6. As a user doing a tiny capture, I want to skip the heavy `distill run` step when appropriate, so that small commits stay fast.
7. As a reviewer, I want route output to explain why those files were chosen, so that the plan is auditable and trustworthy.
8. As a maintainer, I want the first route heuristic to be explicit and deterministic, so that tests can lock it down and future expansion is safe.
9. As a maintainer, I want the route module to reuse config/path semantics already known by the vault, so that Chinese and English vault layouts both work.
10. As a maintainer, I want CLI and MCP to use the same routing implementation, so that product behavior does not drift between surfaces.

## Implementation Decisions

### 1. New routing module
Create a small module, likely `distill/routing.py`, with a single public planner object/function that returns a structured plan dict.

Initial schema:
- `intent`: original user text
- `task_kind`: string enum, start with `progress_capture` and `generic_update`
- `confidence`: `high|medium|low`
- `target_project`: optional project title/path hint
- `read_paths`: ordered list of relative paths
- `write_paths`: ordered list of relative paths
- `optional_paths`: ordered list of relative paths
- `skip_steps`: ordered list of strings like `distill run`, `repo-wide lint`, `index rebuild`
- `why`: concise explanation list
- `warnings`: list for ambiguity or missing targets

### 2. Routing heuristics (P0 only)
Implement only the narrowest high-value heuristic set:

#### `progress_capture`
Trigger when the intent strongly suggests a short progress/update record, e.g. contains words like:
- Chinese: `记录`, `进展`, `今天`, `上线`, `发布`, `UAT`, `修复`, `调整`
- English: `record`, `progress`, `update`, `uat`, `release`, `launch`

If the vault contains a project object whose `title` matches a token/entity in the intent, plan:
- read: current project file + today’s source file if it already exists
- write: today’s source file + project file
- optional: ops log/index only as optional, never required
- skip: `distill run`, `distill lint`, `repo-wide index maintenance`

If no matching project is found, downgrade confidence and return a `generic_update` route with warnings instead of guessing.

### 3. Path discovery rules
Use config-driven canonical directories:
- source dir from configured knowledge roots + source path prefix (`知识/来源` or `knowledge/source`)
- project dir from configured knowledge roots + project path prefix (`知识/项目` or `knowledge/project`)

Do not hardcode Chinese-only paths in planner logic; derive from `config.objects.path_type_map` or a small helper layer.

For today’s source filename in P0, use a conservative placeholder naming rule:
- Chinese vault: `YYYY-MM-DD-碎碎念.md`
- English vault: `YYYY-MM-DD-notes.md`

P0 only needs to identify the path; it does not need to create or edit the file yet.

### 4. CLI surface
Add `distill route` command with:
- required argument: `intent`
- optional `--project` hint to override/assist matching
- optional `--format markdown|json`

Markdown output should be human-scannable:
- task kind
- confidence
- target project
- read paths
- write paths
- optional paths
- skip steps
- warnings

JSON output should be machine-readable and contain the raw plan dict.

### 5. MCP surface
Add MCP tool:
- name: `projection_route`
- args:
  - `intent` required
  - `project_hint` optional

Handler must call the exact same planner used by CLI.

### 6. Commit scoping
Extend `DistillCommit.commit()` and CLI `distill commit`:
- new parameter/flag: `paths: list[str] | None`
- new flag: `--skip-run`

Behavior:
- if `paths` omitted: preserve current default (`git add -A`)
- if `paths` provided: stage only those paths via `git add -- <paths...>`
- if `skip_run=True`: skip `distill run` after commit
- default remains backward-compatible for existing callers

The scoped flow is explicitly for small tasks; route output will recommend it.

### 7. Testing strategy
Because the repo does not currently include the wrapper `scripts/run_tests.sh`, verify that fact explicitly and use narrow direct pytest commands for RED/GREEN.

Add tests first in vertical slices:

#### Slice A: route planner + CLI + MCP
- planner identifies `progress_capture`
- planner resolves project/source paths in a zh vault
- `distill route --format json` is machine-readable
- MCP `projection_route` returns the same structure
- ambiguous/no-project path returns warning instead of blind guess

#### Slice B: scoped commit
- `DistillCommit.commit(paths=[...])` uses `git add -- <paths...>` instead of `git add -A`
- `skip_run=True` suppresses the `distill run` call
- CLI `distill commit ... --paths a --paths b --skip-run` threads values correctly

### 8. Documentation
For this P0 implementation, update README only if the code lands cleanly. Keep docs small:
- mention `distill route` as the daily-operation entrypoint
- mention `distill commit --paths ... --skip-run` for small capture tasks

## Testing Decisions

- Use `click.testing.CliRunner` for CLI tests, matching existing repo style.
- Reuse small synthetic vault fixtures created inside tests.
- Keep route heuristics deterministic and assert exact path lists.
- For commit tests, patch `subprocess.run` as existing `tests/test_hooks_and_commit.py` already does.
- Focus on external behavior, not internal helper layout.

## Out of Scope

- Automatic patch/write application (`distill capture`) in this first pass
- Natural-language extraction of project names via LLMs or fuzzy semantic search
- Rich multi-object routing for articles, decisions, concepts, promotion queue, etc.
- Scoped linting beyond existing staged-lint support
- Reworking the entire commit default path

## Further Notes

- Repo state is already dirty in multiple files before this task. Do not overwrite unrelated in-flight work.
- Commit boundary discipline matters here: keep changes limited to routing, commit surface, tests, and minimal docs.
- The product win for this pass is not “full auto-ingest”; it is “minimal file-surface clarity becomes an explicit runtime capability.”
