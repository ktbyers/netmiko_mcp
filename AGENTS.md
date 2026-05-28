# Netmiko MCP Agent Instructions

## Architecture & Design

- Refer to the `ARCHITECTURE.md` file in the root directory for high-level architecture decisions, structural guardrails, state management, and security constraints.

## Package Management

- ONLY use uv, NEVER pip
- Installation: `uv add <package>`
- Running tools: `uv run --frozen <tool>`. Always pass `--frozen` so uv doesn't
  rewrite `uv.lock` as a side effect.
- Upgrading: `uv lock --upgrade-package <package>`
