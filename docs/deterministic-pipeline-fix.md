# Deterministic pipeline export fix

## Summary
Repeated `distill run` executions could mutate their own future inputs because exported markdown artifacts under the ops directory (`运维/`) were scanned back into the pipeline and index on subsequent runs. This caused:

- `scan.objects` count drift
- `graph` / `analyze` stats drift
- false orphan findings on generated health reports
- unstable `checkpoint.json`
- unstable exported `auto-index.json` / `health-report.md`

## Root cause
Two separate feedback loops existed:

1. `phase_scan()` in `distill/phases.py` scanned every markdown file under configured scan dirs, including generated ops markdown.
2. `VaultIndex.scan()` in `distill/index.py` also indexed ops markdown, so generated health reports could become first-class vault objects and then be flagged as orphans.

Additionally, export artifacts were nondeterministic because they embedded runtime-varying fields:

- `generated_at` timestamp in `auto-index.json`
- `Generated:` line in `health-report.md`
- `timestamp` in `.distill/checkpoint.json`
- unsorted dict/list serialization in exported JSON
- `export` phase stats persisted into checkpoint, even though export writes derived files

## Fix applied

### Input isolation
- Skip `ops_dir` markdown during pipeline scan in `distill/phases.py`
- Skip `ops_dir` markdown during `VaultIndex.scan()` in `distill/index.py`

### Deterministic export/checkpoint
- Remove timestamp fields from exported artifacts/checkpoint
- Normalize nested dict/list/tuple structures before writing JSON
- Write JSON with `sort_keys=True`
- Exclude `export` phase from persisted checkpoint phase stats

## Regression coverage
Added test:
- `tests/test_pipeline.py::TestPipeline::test_pipeline_repeated_runs_produce_stable_outputs`

It verifies:
- repeated `dag.run()` calls preserve the user-authored markdown set
- checkpoint/index/health outputs are byte-stable across repeated runs

## Validation
```bash
python -m pytest tests/test_pipeline.py -q -n 4
# 6 passed
```

## Follow-up
If future product intent is to optionally ingest ops docs as first-class knowledge objects, that should be an explicit configurable mode rather than default behavior for exported runtime artifacts.
