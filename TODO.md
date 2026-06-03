# Netmiko MCP — TODO

Items are grouped by area. Items marked **[ARCH]** are sourced from `ARCHITECTURE.md`.

---

## Security (`security.py`)

- **Audit logging** `[FIX in docstring]` — Every attempted command must be logged with a
  timestamp and the reason it was accepted or rejected (rule 1 deny match, rule 2 no allow
  match, unsafe char, pipe violation, etc.). Required for compliance and incident response.
  Logging should go to a configurable destination (local file, syslog).

- **`load_commands()` caches nothing** — The commands YAML file is read and parsed from disk
  on every single call to `validate_command()`. This should be cached (e.g. with
  `functools.lru_cache` or a module-level dict invalidated on file mtime change).

- **`load_yaml_file` calls `sys.exit()` on `IOError`** — If the commands file exists but
  cannot be read (permissions, corruption), the entire server process dies. Should raise a
  recoverable exception instead and return a safe default (deny all).

- **Command abbreviation handling** `[open question in docstring]` — `sh ip int br` is not
  the same as `show ip interface brief` to the validator even though network devices accept
  both. No resolution yet — document this limitation clearly for users and consider whether
  abbreviation expansion is in scope.

- **Explicit regex support** `[open question in docstring]` — Should `allowed_commands` and
  `denied_commands` support raw regular expressions in addition to globs? Currently only
  `*` glob syntax is supported.

- **Rule 3 comment cleanup** `[FIX tag in docstring]` — The module docstring still carries
  a `[FIX]` tag on Rule 3 about expanding pipe protection to cover other multi-command
  vectors. The raw unsafe chars check now handles `;`, `\n`, `\r`, `&` — the docstring
  should be updated to reflect what is actually implemented.

---

## Configuration (`config.py`)

- **`settings` is a module-level singleton** — Loaded once at import time. Any change to
  `~/.netmiko-mcp.yml` requires a full server restart to take effect. Consider a reload
  mechanism or at minimum document this clearly.

- **No startup validation of `command_file` path** — The server starts successfully even if
  `command_file` points to a non-existent path. It silently denies all commands. Should
  warn at startup if the file is missing.

---

## Connection & Performance (`connection.py` / `ARCHITECTURE.md`)

- **No connection pooling** `[ARCH §2]` — A new SSH connection is opened for every
  `send_show_command` call. SSH handshakes take 3–10 seconds per device. A connection
  pool/cache with a configurable TTL (e.g. 60 seconds of inactivity) would dramatically
  improve response times for multi-step LLM interactions.

- **No concurrency** `[ARCH §2]` — Commands to multiple devices are sequential. A
  threading or async approach would allow the LLM to fan out queries across devices
  simultaneously.

- **No stale session detection** `[ARCH §2]` — No mechanism to detect, purge, or
  re-establish SSH connections that have silently dropped.

- **Broad `except Exception` in `run_show_command`** — The catch-all hides unexpected
  errors that could indicate bugs. Should be narrowed or at minimum log the full traceback
  before returning the error string to the LLM.

---

## Output Handling (`connection.py` / `ARCHITECTURE.md`)

- **No output truncation** `[ARCH §3]` — A `show tech-support` or similar verbose command
  could return hundreds of thousands of tokens, blowing out the LLM's context window. Tools
  should enforce a configurable line/character cap and append a truncation warning that
  tells the LLM how to retrieve the remainder (e.g. via `limit`/`offset` parameters).

- **No `limit`/`offset` parameters on `send_show_command`** `[ARCH §3]` — Pagination
  support for large outputs is not implemented.

---

## Server Tools (`server.py`)

- **No multi-device tool** — There is no tool to send the same command to multiple devices
  simultaneously. This is a common LLM workflow (e.g. "check OSPF neighbours on all
  routers in group X").

- **No read-write / config mode** `[ARCH §1]` — `send_config_set` is intentionally absent.
  A separate opt-in `send_config_command` tool behind a `allow_config: false` config flag
  would let operators explicitly unlock configuration capability when needed.

- **No blast radius limits** `[ARCH §1]` — No constraint on how many devices the LLM can
  touch in a single session or time window. A `max_devices_per_request` config setting
  would limit the damage from a runaway agent.

- **No human-in-the-loop for config changes** `[ARCH §1]` — For any future config tool,
  consider a staging/approval step: the server generates the config diff, pauses, and
  requires explicit user confirmation before pushing.

---

## Inventory (`inventory.py`)

- **Only `netmiko_tools` inventory type is implemented** — The `inventory_type` field in
  config is a `Literal["netmiko_tools"]` — only one value is valid. Future inventory
  backends (NetBox, Nautobot, CSV, plain YAML) are not yet supported.

- **SSH key / SSH agent support not documented** `[ARCH §4]` — Netmiko supports SSH keys
  and agents natively, but there is no documentation or explicit handling in the MCP layer
  to guide users toward keyring-based auth instead of encrypted passwords.

- **`_set_inventory_env_var()` mutates `os.environ` as a side effect** — Setting
  `NETMIKO_TOOLS_CFG` globally on every call is a side effect that could interfere with
  other parts of the process. Should be refactored to pass the path more explicitly.

---

## MCP Protocol Features (`server.py` / `ARCHITECTURE.md`)

- **No MCP Resources** `[ARCH §5]` — The device inventory could be exposed as an MCP
  Resource (read-only data) rather than only as a Tool call. This would let clients
  discover available devices without consuming tool-call budget.

- **No MCP Prompts** `[ARCH §5]` — Pre-packaged workflow prompts (e.g. "Troubleshoot OSPF
  on device X", "Collect interface stats from group Y") are not implemented. These would
  guide the LLM through multi-step diagnostic sequences reliably.


