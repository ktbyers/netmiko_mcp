# Netmiko MCP Agent Instructions

## Architecture & Design

- Refer to the `ARCHITECTURE.md` file in the root directory for high-level architecture
  decisions, structural guardrails, state management, and security constraints.

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
- Always run "uv run" with the --frozen argument (unless you are explicitly trying to
  upgrade the lock file).
- `uv run --frozen ruff check` and `uv run --frozen ruff format --check` must 100% pass
   before committing.
- `uv run --frozen mypy src tests` must 100% pass before committing.
- `uv run --frozen pytest -v` must 100% pass before committing. Note: Live integration tests are protected via `@pytest.mark.skipif(not os.environ.get("RUN_LIVE_TESTS"), ...)`.

## Configuration & Paths
- **Global Config:** The MCP Server uses `pydantic-settings` centralized in `src/netmiko_mcp/config.py`. It reads from `~/.netmiko-mcp.yml` or overrides via `NETMIKO_MCP_` environment variables.
- **Paths:** Always use the `pathlib.Path` module for file operations instead of `os.path`.
- **Security:** Commands are strictly validated via exact matching against a whitelist defined in the configuration YAML (`commands.yml`). Default is deny-all.

