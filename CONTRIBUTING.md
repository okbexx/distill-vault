# Contributing to distill-vault

Thanks for your interest! Here's how to get started.

## Quick Setup

```bash
git clone https://github.com/okbexx/distill-vault.git
cd distill-vault
pip install -e ".[dev]"
python -m pytest tests/ -q -n 4   # run the full suite
```

## Development Workflow

1. **Create a branch** from `main`: `git checkout -b feature/your-feature`
2. **Make changes** — write code + tests
3. **Run tests**: `python -m pytest tests/ -q -n 4`
4. **Commit** with clear messages (conventional commits preferred)
5. **Open a PR** against `main`

## Code Style

- Python 3.10+ (use `from __future__ import annotations` for modern type hints)
- Follow existing patterns in the codebase
- Keep functions focused and testable
- Docstrings on public APIs

## Testing

- All new features must include tests
- All bug fixes must include regression tests
- Run the full suite before opening a PR: `python -m pytest tests/ -q -n 4`
- CI runs on Python 3.10 / 3.11 / 3.12 — make sure your code works on all three

## Reporting Issues

- **Bug reports**: Include Python version, OS, steps to reproduce, and expected vs actual behavior
- **Feature requests**: Describe the use case, not just the solution
- **Questions**: No such thing as a dumb question — open an issue with the "question" label

## Project Structure

```
distill/
├── cli.py          # CLI entry point (Click)
├── pipeline.py     # 6-phase pipeline engine
├── phases.py       # Individual phase implementations
├── graph_index.py  # Typed graph facade over SQLite
├── sqlite_store.py # Rebuildable object/edge/FTS5 projection
├── snapshot.py     # Immutable single-scan vault snapshot
├── index.py        # Vault indexing and stats
├── lint.py         # Structural linting
├── health.py       # Health check logic
├── hooks.py        # Git hook management
├── skill_specs.py  # Skill system (v1-v6)
├── mcp_server.py   # Official MCP SDK server binding
└── web_server.py   # Web UI (Sigma.js)
tests/
├── test_pipeline.py
├── test_v6_platform_renderers.py
├── test_skill_cli.py
└── ... (full regression suite)
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
