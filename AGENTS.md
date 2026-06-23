# Netmiko MCP Agent Instructions

## Security: Credentials and Secrets

- **NEVER send credentials, secrets, or environment variable values to an LLM.** This includes passwords, tokens, API keys, encryption keys, passphrases, and any sensitive environment variable contents.
- All solutions involving credentials or secrets must be designed so that the sensitive values remain on the server and are never included in LLM prompts, tool arguments, tool responses, or any content that flows through the MCP protocol to a model.
- When discussing or documenting credential handling, describe the mechanism (e.g. "read from environment variable") without including actual values.

## Architecture & Design

- Refer to the `ARCHITECTURE.md` file in the root directory for high-level architecture
  decisions, structural guardrails, state management, and security constraints.
- **Refactoring:** Major code refactoring must always be reviewed and approved prior to proceeding.

## Package Management

- ONLY use uv, NEVER pip
- Installation: `uv add <package>`
- Running tools: `uv run --frozen <tool>`. Always pass `--frozen` so uv doesn't
  rewrite `uv.lock` as a side effect.
- Upgrading all packages: `uv lock --upgrade`
- Upgrading a specific package: `uv lock --upgrade-package <package>`
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
- **Comment Style:** Avoid using numbered or bulleted lists in inline code comments (e.g., `# 1. This part` or `# 2. Some other part`). Write comments as descriptive paragraphs or clear, individual sentences without numeric or alphabetic step indicators.

## Skills Documentation

- All files under `skills/` are written **for LLMs, not humans**. They are injected directly into LLM context and should be optimized accordingly: dense, structured, reference-first. No orientation prose, no motivational language, no callout boxes (`>` blockquotes). Every sentence should be a fact or a rule.
- Do not add narrative introductions, "why" explanations, or human-friendly transitions to skill files. If an LLM needs to know a rule, state it directly.
- `README.md`, `ARCHITECTURE.md`, and `TODO.md` are human-facing documents and should be written accordingly. Everything else — including all files under `skills/` and `docs/` — should be written with an LLM consumer in mind.

## Documentation Style

- **Avoid absolute, black-and-white statements.** Do not write things like "this documents
  ALL settings", "the server denies **all** commands by default", or "this will always block X".
  Real-world software has edge cases, bugs, and failure modes. Use measured language that
  acknowledges this — prefer "should", "is intended to", "by default attempts to" over
  definitive absolutes. For example: "by default the server should deny all commands" rather
  than "by default the server denies all commands".
- **Do not over-promise security guarantees.** Security controls are best-effort. Document
  what the design intent is, not an absolute guarantee.
- When documenting MCP client integration, only document what has been **tested and
  confirmed to work**. Each MCP client (Claude Code, Claude Desktop, Cursor, etc.) handles
  server registration and env var inheritance differently. Use a separate doc per client
  under `docs/clients/` rather than a generic example that may not apply.

## Documentation & Examples

- **NEVER** include `NETMIKO_TOOLS_KEY` or any other secret/credential in example JSON
  snippets, MCP client config examples, or documentation. Embedding encryption keys in
  config files is a serious security anti-pattern.
- **Do NOT** document MCP client configuration using a JSON `env` block as the mechanism
  for setting `NETMIKO_MCP_CONFIG` or `NETMIKO_TOOLS_KEY`. Claude Code does not configure
  MCP servers that way. Instead, direct users to set these in their shell rc file
  (`~/.bashrc` or `~/.zshrc`) using `export NETMIKO_MCP_CONFIG="$HOME/.netmiko-mcp.yml"`.
- **GitHub Actions:** Always pin actions to full-length commit SHA hashes, never version
  tags. Verify every SHA via the GitHub API before committing. Annotated tags must be
  dereferenced to the underlying commit SHA.

## Git Commits

- **Always review `git diff` and `git status` before staging or committing.** Read every
  changed file in the diff and confirm the changes are intentional and correct.
- **NEVER commit keys, secrets, passwords, tokens, or any other highly confidential
  information.** This includes API keys, bearer tokens, encryption keys, device passwords,
  TACACS/RADIUS secrets, private keys, and certificate material — in any form, whether
  plaintext, base64-encoded, or otherwise obfuscated.
- Secrets belong exclusively in environment variables or a secrets manager. They should
  never appear in source files, config files, documentation, test fixtures, or commit
  messages.
- If a secret is ever accidentally staged, unstage it immediately with `git restore --staged`
  before committing. If it has already been committed, treat the secret as compromised and
  rotate it — git history rewrites are insufficient on their own.

## Environment Variables

- **NEVER inspect or print environment variables.** Do not run `printenv`, `env`, `echo $VAR`, or any equivalent command that would reveal environment variable values. Environment variables in this project contain secrets (encryption keys, bearer tokens, device passwords). Exposing them in output visible to an LLM is a serious security violation.

## Live Device Testing

Live integration tests require the following setup before running `RUN_LIVE_TESTS=1 pytest`:

**`tests/etc/.netmiko.yml`** — gitignored, must be created manually. This file contains device credentials and is never committed. If it does not exist, all live test fixtures will skip with a clear message rather than falling back to `~/.netmiko.yml`. The inventory must contain device entries and group definitions matching the values in `tests/etc/responses.yml` (defaults: devices `cisco1`, `cisco2`, group `cisco`).

**`NETMIKO_TOOLS_KEY`** — must be set in the environment if the inventory uses encrypted credentials.

**`tests/etc/responses.yml`** — already committed. Edit this file to adjust expected device names, group names, and output patterns to match your lab. No test code changes are needed.

Everything else (`tests/etc/netmiko-mcp.yml`, `tests/etc/commands.yml`) is committed and requires no setup.

To run the full live test suite:

```bash
RUN_LIVE_TESTS=1 uv run --frozen pytest -v tests/test_integration.py
```

To run a single live test:

```bash
RUN_LIVE_TESTS=1 uv run --frozen pytest -v tests/test_integration.py::test_live_device_connection
```

## Configuration & Paths
- **Global Config:** The MCP Server uses `pydantic-settings` centralized in `src/netmiko_mcp/config.py`. It reads natively from `~/.netmiko-mcp.yml` (and other custom profiles) with strict precedence handling managed via the `settings_customise_sources` classmethod. Environment variables prefixed with `NETMIKO_MCP_` always take precedence over keys in the physical YAML config.
- **Paths:** Always use the `pathlib.Path` module for file operations instead of `os.path`.
- **Security:** Commands are strictly validated via exact matching against a whitelist defined in the configuration YAML (`commands.yml`). Default is deny-all.

