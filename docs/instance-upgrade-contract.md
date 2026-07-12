# Instance Upgrade Contract

`distill-vault` exposes a second runtime-facing contract for aligning a vault instance with the engine currently installed.

This layer is intentionally separate from the task-routing contract in `distill.routing`.

## Surfaces

### 1. Engine capabilities
- CLI: `distill capabilities`
- MCP: `runtime_capabilities`
- Purpose: report what the current engine supports right now

Stable fields:
- `engine_version`
- `module_path`
- `executable_path`
- `python_path`
- `install_mode`
- `editable_source_path`
- `supported_commands`
- `supported_runtime_surfaces`
- `status_fields`
- `worker_pool_modes`

### 2. Instance doctor
- CLI: `distill doctor --instance-upgrade`
- MCP: `instance_doctor`
- Purpose: compare current engine surface with vault runtime adoption state

Stable fields:
- `engine_version`
- `runtime_stage`
- `has_checkpoint`
- `install_mode`
- `editable_source_path`
- `adoption_status`
- `capability_gaps`
- `recommended_actions`
- `warnings`
- `legacy_runtime_docs`

### 3. Instance upgrade plan
- CLI: `distill upgrade-plan`
- MCP: `instance_upgrade_plan`
- Purpose: return the minimal engine→instance adoption checklist

Stable fields:
- `action`
- `status`
- `target`
- `summary`
- `steps`
- `warnings`

## Contract rule

The engine→instance upgrade surfaces must be built from shared builders/renderers in `distill.capabilities` and `distill.instance_upgrade`, then reused unchanged by CLI and MCP entrypoints.

Do not hand-assemble near-duplicate payloads per command or per MCP tool.

## Compatibility guidance

Use:
- `capabilities` / `runtime_capabilities` when you need the engine truth
- `doctor --instance-upgrade` / `instance_doctor` when you need drift diagnosis
- `upgrade-plan` / `instance_upgrade_plan` when you need the smallest adoption checklist
