# Netmiko MCP Agent Instructions

## Package Management

- ONLY use uv, NEVER pip
- Installation: `uv add <package>`
- Running tools: `uv run --frozen <tool>`. Always pass `--frozen` so uv doesn't
  rewrite `uv.lock` as a side effect.
