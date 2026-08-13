# Code Structure

A brief overview of the Python modules in `netmiko_mcp/src/netmiko_mcp/`.

## `__init__.py`

Package marker for the `netmiko_mcp` package.

**Classes:** None.

**Functions:** None.

## `server.py`

Entry point that defines the MCP server and its tools (e.g. `send_show_command`, `list_devices`, `ping`), validates startup configuration, and runs the stdio or streamable-HTTP transport.

**Classes:** None of its own. It instantiates `MCPServer` (from the external `mcp.server` package) and, for the HTTP transport, wraps the app with `BearerTokenMiddleware` (from `http_auth.py`).

**Functions:**
- `check_startup_error(func)` — decorator that short-circuits a tool and returns the stored startup error if one is set.
- `list_groups()` — MCP tool returning the JSON-encoded list of inventory group names.
- `list_devices(device_or_group="all")` — MCP tool returning credential-sanitized inventory data as JSON.
- `send_show_command(device_name, command, use_textfsm=False, save_output=False)` — MCP tool that runs a single show command on one device.
- `send_show_command_to_group(device_or_group, command, use_textfsm=False, save_output=False)` — MCP tool that runs a show command concurrently across a group.
- `list_device_outputs(device_or_group)` — MCP tool listing saved output files for a device, group, or all devices.
- `read_device_output(device_name, filename, offset=0, limit=500)` — MCP tool returning a paginated slice of a saved output file.
- `ping()` — MCP health-check tool that returns `"pong"`.
- `_get_bearer_token()` — reads the HTTP bearer token from the environment, exiting if unset.
- `_validate_startup()` — validates required config/files before startup, raising or returning an error per transport.
- `_run_http()` — builds the ASGI app, optionally wraps it with bearer-token auth, and serves it via uvicorn.
- `main()` — entry point that validates startup, configures audit logging, and runs the selected transport.

## `config.py`

Pydantic-settings model defining all server configuration (loaded from environment variables and an optional YAML file) and the global `settings` singleton.

**Classes:**
- `McpConfig` — pydantic-settings `BaseSettings` model holding all server configuration.
  - `_check_pipe_char_consistency()` — validator that rejects `'|'` in `allowed_command_chars` when `allow_pipe` is False.
  - `settings_customise_sources(...)` — classmethod defining source precedence (env vars over the YAML config file).

**Functions:** None (module instantiates the `settings` singleton at import).

## `connection.py`

Establishes SSH sessions via Netmiko to execute show commands on single devices or concurrently across groups, and handles saving, listing, and paginated reading of large command output.

**Classes:** None.

**Functions:**
- `_managed_connection(connect_params)` — context manager that opens a Netmiko SSH session and disconnects it on exit.
- `run_show_command(...)` — validates, connects, runs a single show command, and returns output or an error string.
- `_validate_path_component(value, label)` — raises if a path component contains unsafe values or characters.
- `_sanitize_command_for_filename(command)` — converts a command string into a safe, truncated filename component.
- `_save_device_output(device_name, command, output)` — writes command output to a per-device file and returns its path.
- `list_device_outputs(device_or_group)` — returns a mapping of device name to its saved output filenames (newest first).
- `read_device_output(device_name, filename, offset=0, limit=500)` — reads a saved output file with path validation and pagination.
- `run_show_command_on_group(...)` — validates once, then runs a show command across a group concurrently via a thread pool.

## `security.py`

Command verification layer that normalizes commands and enforces the allow/deny lists (including glob and abbreviation matching) under a default-deny policy.

**Classes:**
- `ValidationResult` — dataclass returned by `validate_command` carrying the allow/deny verdict, reason, and normalized command. (No methods; dataclass fields only.)
- `TrieNode` — a single node in the character-level prefix trie used for abbreviation matching.
  - `__init__()` — initializes the node's child map and word/glob terminal flags.
- `AbbreviationDenyFilter` — builds and queries a trie of deny entries to catch abbreviated forms of denied commands.
  - `__init__()` — creates the empty root `TrieNode`.
  - `add(deny_entry)` — inserts a plain or trailing-glob deny entry into the trie hierarchy.
  - `is_denied(submitted)` — returns True if the submitted command is an abbreviation of any deny entry.
  - `match_word(trie_root, words, word_idx)` — walks the trie for one submitted word, then dispatches to `find_word_end`.
  - `find_word_end(node, words, word_idx, last_word)` — DFS from a node to reach terminal nodes and apply the deny logic.

**Functions:**
- `_invalid_glob_entries(entries)` — returns entries that violate the single trailing-only glob rule.
- `validate_allow_commands(allowed_commands)` — returns allow entries containing unsupported glob patterns.
- `validate_deny_commands(denied_commands)` — returns deny entries containing unsupported glob patterns.
- `validate_command_lists(allowed_commands, denied_commands)` — validates both lists and returns human-readable error messages.
- `glob_to_regex(glob_pattern)` — compiles a simple `*` glob pattern into a regular expression.
- `deny_check(command, denied_commands)` — returns True if the command matches any deny entry via glob/regex.
- `load_commands()` — loads and caches the allow/deny lists from the configured command file.
- `build_abbreviation_filter(denied_commands)` — builds and caches an `AbbreviationDenyFilter` from the deny list.
- `validate_command(command)` — normalizes and validates a command, returning a `ValidationResult`.

## `inventory.py`

Wraps Netmiko's tools inventory to look up device connection parameters, resolve group and device names, and return credential-sanitized inventory data.

**Classes:** None.

**Functions:**
- `_set_inventory_env_var()` — points Netmiko at the configured inventory file via `NETMIKO_TOOLS_CFG` when set.
- `get_group_names()` — returns the list of group names defined in the inventory.
- `get_device_params(device_name)` — returns full connection parameters (including credentials) for one device; internal use only.
- `get_device_names(device_or_group)` — returns the list of device names for a device or group.
- `get_all_device_params(device_or_group)` — returns full parameters for all devices in a group in one call; internal use only.
- `get_sanitized_inventory(device_or_group)` — returns inventory as JSON with credentials removed.

## `audit.py`

Fail-closed audit logging that emits structured JSON records for every command attempt, connection outcome, and tool invocation to a file and/or syslog, plus optional SSH channel transcripts.

**Classes:**
- `_AuditJsonFormatter` — `logging.Formatter` subclass that renders log records as single-line JSON.
  - `format(record)` — serializes a log record (timestamp, level, and extra fields) to a single-line JSON string.
- `_FailClosedFileHandler` — `logging.FileHandler` subclass that re-raises write errors instead of swallowing them.
  - `handleError(record)` — re-raises the underlying write exception as a `RuntimeError` so the caller fails closed.
- `_FailClosedSysLogHandler` — `logging.handlers.SysLogHandler` subclass that re-raises write errors instead of swallowing them.
  - `handleError(record)` — re-raises the underlying syslog write exception as a `RuntimeError`.
- `CommandAuditContext` — dataclass holding the shared per-invocation audit fields for a single command call.
  - `log_attempt(verdict, reason)` — emits a `command_attempt` audit record for this invocation.
  - `log_outcome(outcome, detail=None, textfsm_parse_failed=False)` — emits a `connection_outcome` audit record for this invocation.

**Functions:**
- `_build_file_handler(formatter)` — constructs a fail-closed file handler for the audit log.
- `_build_syslog_handler(formatter)` — constructs a fail-closed syslog handler for the audit log.
- `configure_audit_logger()` — attaches the configured audit handlers at startup (no-op when disabled).
- `_emit(fields)` — emits one structured audit record, propagating write failures when enabled.
- `log_command_attempt(...)` — emits an audit record for a command validation verdict.
- `log_connection_outcome(...)` — emits an audit record for a connection/command execution outcome.
- `log_tool_invocation(tool, arguments)` — emits an audit record for a non-device MCP tool invocation.
- `save_channel_transcript(correlation_id, device_name, raw_bytes)` — writes the SSH channel read transcript to a per-connection file.

## `http_auth.py`

ASGI middleware enforcing RFC 6750 bearer token authentication on the HTTP transport, using a constant-time token comparison.

**Classes:**
- `BearerTokenMiddleware` — pure ASGI middleware that enforces bearer token authentication on every HTTP request.
  - `__init__(app, token)` — stores the wrapped ASGI app and the expected token.
  - `__call__(scope, receive, send)` — rejects unauthorized HTTP requests with 401 and passes everything else through.
  - `_is_authorized(scope)` — returns True if the request carries a valid bearer token (constant-time compared).
  - `_send_401(send)` — emits an HTTP 401 Unauthorized response per RFC 6750.

**Functions:** None.

---

# How the Pieces Relate

This section describes how the modules and classes interact at both the type level (inheritance/composition) and the runtime level (call flow).

## Inheritance

Several classes extend standard-library or third-party base classes rather than relating to each other:

- `McpConfig` extends pydantic-settings `BaseSettings`.
- `_AuditJsonFormatter` extends `logging.Formatter`.
- `_FailClosedFileHandler` extends `logging.FileHandler`.
- `_FailClosedSysLogHandler` extends `logging.handlers.SysLogHandler`.

## Composition

- `AbbreviationDenyFilter` is built from many `TrieNode` objects: each node links to child `TrieNode`s (one per character) and, for multi-word deny entries, to a next-word `TrieNode`. The filter owns the root node and walks this tree to match abbreviated commands.
- In `audit.py`, `configure_audit_logger()` constructs the `_FailClosed*Handler`s and attaches an `_AuditJsonFormatter` instance to each, so every emitted record is serialized to JSON by the formatter before a handler writes it.

## The `settings` singleton is shared everywhere

`config.py` instantiates a single `McpConfig` object named `settings`. Almost every other module (`audit`, `security`, `inventory`, `connection`, `server`) imports and reads from this one instance, so configuration is global and read-only at runtime.

## Command execution flow (the core interaction)

The main runtime path ties the classes together when a device command is requested:

1. **`server.py`** exposes MCP tools on the `MCPServer` instance. A tool call such as `send_show_command` delegates to `run_show_command` in `connection.py`.
2. **`connection.py`** calls `validate_command` in `security.py`, which returns a `ValidationResult`. Validation consults both the glob/regex path and an `AbbreviationDenyFilter` (built from `TrieNode`s) to catch abbreviated deny entries.
3. `connection.py` creates a `CommandAuditContext` (from `audit.py`) and calls `log_attempt(...)` to record the allow/deny verdict, using the reason constants that `security.py` imported from `audit.py`.
4. On an allowed command, `connection.py` looks up credentials via `inventory.py`, opens a Netmiko SSH session, runs the command, then calls `CommandAuditContext.log_outcome(...)` to record success or failure.
5. Audit records flow through the configured `_FailClosed*Handler`s and `_AuditJsonFormatter`; if audit logging is enabled and a write fails, the exception propagates so the operation fails closed.

## HTTP transport wiring

When running the streamable-HTTP transport, `server.py`'s `_run_http()` wraps the ASGI application produced by `MCPServer` with a `BearerTokenMiddleware` instance (from `http_auth.py`). This class is otherwise independent of the command-execution classes — it only gates inbound HTTP requests before they reach the MCP tools.

## Startup wiring

At startup, `server.main()` calls `validate_command_lists` in `security.py` to reject malformed allow/deny globs, then `configure_audit_logger()` in `audit.py` to attach the audit handlers, before running the selected transport.
