# Netmiko MCP Agent Instructions

## Architecture & Design

- Refer to the `ARCHITECTURE.md` file in the root directory for high-level architecture decisions, structural guardrails, state management, and security constraints.

## Package Management

- ONLY use uv, NEVER pip
- Installation: `uv add <package>`
- Running tools: `uv run --frozen <tool>`. Always pass `--frozen` so uv doesn't
  rewrite `uv.lock` as a side effect.
- Upgrading: `uv lock --upgrade-package <package>`
- FORBIDDEN: `uv pip install`, `@latest` syntax

## Code Quality

- Type hints required for all code
- `src/netmiko_mcp/__init__.py` defines the public API surface via `__all__`. Adding a
  symbol there is a deliberate API decision, not a convenience re-export.
- IMPORTANT: All imports go at the top of the file — inline imports hide
  dependencies and obscure circular-import bugs. Only exception: when a
  top-level import genuinely can't work (lazy-loading optional deps, or
  tests that re-import a module).
- `ruff check` and `ruff format --check` must 100% pass before committing.
- `mypy src` must 100% pass before committing.
