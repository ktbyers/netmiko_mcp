# Netmiko MCP - TODO

Items are grouped by area. Items marked **[ARCH]** are sourced from `ARCHITECTURE.md`.

---

## Security (`security.py`)

- **Transcript retention/cleanup not implemented** - The `save_channel_transcript`
  docstring states that files beyond `audit_log_retention_days` are removed on each
  write, but neither the config field nor the cleanup code exist. Transcript files
  accumulate indefinitely. Needs an `audit_log_retention_days: int` field in
  `config.py` (default 30) and a cleanup pass inside `save_channel_transcript` that
  deletes files older than the retention window before writing the new one.

- **Command abbreviation handling** `[open question in docstring]` - `sh ip int br` is not
  the same as `show ip interface brief` to the validator even though network devices accept
  both. No resolution yet - document this limitation clearly for users and consider whether
  abbreviation expansion is in scope.

- **Explicit regex support** `[open question in docstring]` - Should `allowed_commands` and
  `denied_commands` support raw regular expressions in addition to globs? Currently only
  `*` glob syntax is supported.

---

## Connection & Performance (`connection.py` / `ARCHITECTURE.md`)

- **No connection pooling** `[ARCH §2]` - A new SSH connection is opened for every
  `send_show_command` call. SSH handshakes take 3-10 seconds per device. A connection
  pool/cache with a configurable TTL (e.g. 60 seconds of inactivity) would dramatically
  improve response times for multi-step LLM interactions.

- **No stale session detection** `[ARCH §2]` - No mechanism to detect, purge, or
  re-establish SSH connections that have silently dropped.

- **Broad `except Exception` in `run_show_command`** - The catch-all hides unexpected
  errors that could indicate bugs. Should be narrowed or at minimum log the full traceback
  before returning the error string to the LLM.

---

## Output Handling (`connection.py` / `ARCHITECTURE.md`)

- **No output truncation** `[ARCH §3]` - A `show tech-support` or similar verbose command
  could return hundreds of thousands of tokens, blowing out the LLM's context window. Tools
  should enforce a configurable line/character cap and append a truncation warning that
  tells the LLM how to retrieve the remainder (e.g. via `limit`/`offset` parameters).

- **No `limit`/`offset` parameters on `send_show_command`** `[ARCH §3]` - Pagination
  support for large outputs is not implemented.

---

## Server Tools (`server.py`)

- **No read-write / config mode** `[ARCH §1]` - `send_config_set` is intentionally absent.
  A separate opt-in `send_config_command` tool behind a `allow_config: false` config flag
  would let operators explicitly unlock configuration capability when needed.

- **No blast radius limits** `[ARCH §1]` - No constraint on how many devices the LLM can
  touch in a single session or time window. A `max_devices_per_request` config setting
  would limit the damage from a runaway agent.

- **No human-in-the-loop for config changes** `[ARCH §1]` - For any future config tool,
  consider a staging/approval step: the server generates the config diff, pauses, and
  requires explicit user confirmation before pushing.

- **Audit fail-closed policy for config-write tools** `[open question]` - General policy
  is fail-closed: if audit logging is enabled and the logger fails, the MCP operation
  fails. Open question: should `allow_config` mode enforce fail-closed independently of
  any global audit setting, as an additional safeguard for configuration changes?

---

## Inventory (`inventory.py`)

- **Only `netmiko_tools` inventory type is implemented** - The `inventory_type` field in
  config is a `Literal["netmiko_tools"]` - only one value is valid. Future inventory
  backends (NetBox, Nautobot, CSV, plain YAML) are not yet supported.

- **SSH key / SSH agent support not documented** `[ARCH §4]` - Netmiko supports SSH keys
  and agents natively, but there is no documentation or explicit handling in the MCP layer
  to guide users toward keyring-based auth instead of encrypted passwords.

- **`_set_inventory_env_var()` mutates `os.environ` as a side effect** - Setting
  `NETMIKO_TOOLS_CFG` globally on every call is a side effect that could interfere with
  other parts of the process. Should be refactored to pass the path more explicitly.

---

## MCP Protocol Features (`server.py` / `ARCHITECTURE.md`)

- **No MCP Resources** `[ARCH §5]` - The device inventory could be exposed as an MCP
  Resource (read-only data) rather than only as a Tool call. This would let clients
  discover available devices without consuming tool-call budget.

- **No MCP Prompts** `[ARCH §5]` - Pre-packaged workflow prompts (e.g. "Troubleshoot OSPF
  on device X", "Collect interface stats from group Y") are not implemented. These would
  guide the LLM through multi-step diagnostic sequences reliably.


