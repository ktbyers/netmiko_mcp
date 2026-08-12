# Stateless MCP — Implementation Plan (mcp 2.0.0 / protocol 2026-07-28)

Status: **APPROVED to proceed with the FastMCP → MCPServer migration (Q-C approved).**
A few implementation-shaping questions remain (Q-A, Q-D, Q-F) — see Section 6.
This is a MAJOR REFACTOR (FastMCP → MCPServer).

Scope changed after upgrading the SDK. Original goal: add a backwards-compatible
stateless mode to the existing FastMCP-based Streamable HTTP transport, defaulting to
stateless. Upon upgrading to `mcp` 2.0.0 we discovered `FastMCP` is removed entirely and
the SDK now natively implements the stateless `2026-07-28` protocol. Delivering
statelessness therefore requires migrating the server off `FastMCP` onto the new
`MCPServer` API.

**Done so far (dependency only, no source changes):**
- `pyproject.toml`: `mcp>=1.27.1` → `mcp>=2.0.0`.
- `uv.lock`: re-locked via `uv lock`. `mcp` 1.28.0 → 2.0.0.

**Not done:** any source changes. `src/netmiko_mcp/server.py` currently fails to import
under 2.0.0 (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`).

---

## 1. Background / Spec Review

### 1.1 What "stateless" means

The MCP `2026-07-28` revision transitions the protocol from a stateful,
connection-oriented model to a stateless request/response model:

- No `initialize` handshake required for the modern envelope; protocol version, client
  identity, and capabilities ride in per-request metadata.
- No `Mcp-Session-Id` / sticky sessions / shared session store; each HTTP request stands
  on its own, enabling round-robin load balancers and serverless execution.
- Routable HTTP headers (`Mcp-Method`, `Mcp-Name`) let gateways/WAFs route and rate-limit
  without parsing JSON-RPC bodies.
- Multi Round-Trip Requests (MRTR): mid-execution input requests use an
  `input_required` result + opaque request state instead of a long-lived stream.
- Cacheable discovery: tool/resource listings support cache hints (TTL, deterministic
  ordering) so clients can cache capabilities.

### 1.2 Verification against installed `mcp` 2.0.0 (this checkout)

Confirmed by inspecting the locked/synced package:

- `mcp_types.version`: `KNOWN_PROTOCOL_VERSIONS` ends with `2026-07-28`;
  `MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)` = "stateless per-request envelope";
  `HANDSHAKE_PROTOCOL_VERSIONS` = the legacy `2024-11-05 … 2025-11-25` revisions.
- Routable headers present: `mcp.shared.inbound.MCP_METHOD_HEADER` (`mcp-method`),
  `MCP_NAME_HEADER` (`mcp-name`).
- MRTR present: `mcp_types.InputRequiredResult`; `ctx.input_responses` /
  `ctx.request_state` on the new `Context`.
- Cacheable discovery present: `mcp.server.CacheHint`, `cache_hints`, `CacheableMethod`.
- `FastMCP` is **removed**: `mcp.server.fastmcp` does not exist. Replacement is
  `mcp.server.MCPServer`.

**Reconciliation of the earlier "contradiction":** the Gemini summary of the
`2026-07-28` spec is substantially accurate — it only conflicted with `mcp` **1.28.0**,
which predated that revision (its latest was `2025-11-25`). `mcp` 2.0.0 implements it.

### 1.3 Why netmiko-mcp is safe to run stateless (unchanged)

Every tool call already opens a fresh SSH connection via `_managed_connection`,
executes, and disconnects. Saved output is keyed by device name on disk, not by MCP
session. No cross-request server-side session state, no server-initiated notifications,
no resumable streams are relied upon. netmiko-mcp tools are single request/response and
do not need MRTR. Statelessness removes nothing the tools use.

### 1.4 New SDK API surface (mcp 2.0.0)

- Import: `from mcp.server import MCPServer` (and `from mcp.server.mcpserver.context
  import Context` if a tool ever needs it — none currently do).
- Construction: `MCPServer(name=..., instructions=..., version=...)`. Note: the
  constructor **no longer accepts** `host` / `port` / `streamable_http_path`; those move
  to the run/app methods.
- Tool registration: `@server.tool()` decorator — signature-compatible with our current
  usage, so the `@check_startup_error` inner-decorator pattern is preserved
  (`@mcp.tool()` outermost, `@check_startup_error` innermost).
- stdio: `server.run(transport="stdio")` — unchanged call shape.
- HTTP ASGI app (what we need to wrap with `BearerTokenMiddleware` + uvicorn):
  `server.streamable_http_app(streamable_http_path=..., json_response=...,
  stateless_http=..., host=...)`.
- Convenience runner (not used by us because we wrap auth ourselves):
  `server.run(transport="streamable-http", host=, port=, streamable_http_path=,
  json_response=, stateless_http=, ...)`.

### 1.5 Dependency churn introduced by the upgrade (must be validated)

From `uv lock` output: `httpx` → `httpx2`, added `httpcore2`, `mcp-types`,
`opentelemetry-api`, `truststore`, `httpx2-jsfetch`; removed `httpx-sse`; `uvicorn`
0.48 → 0.49. Impacts to check: dev tests import `httpx` directly (`test_http_auth.py`,
`test_http_server.py`, and the new HTTP live harness); `pip-audit` results; and whether
`uvicorn>=0.48.0` floor in `pyproject.toml` should move to `>=0.49.0`.

### 1.6 Current code baseline

- `src/netmiko_mcp/server.py`: builds `mcp = FastMCP(...)` at import time (host/port/path
  passed to constructor), registers tools via `@mcp.tool()` + `@check_startup_error`,
  `_run_http()` wraps `mcp.streamable_http_app()` in `BearerTokenMiddleware` under
  uvicorn, `main()` dispatches stdio vs streamable-http. **Fails to import on 2.0.0.**
- `src/netmiko_mcp/config.py`: `McpConfig` HTTP fields (`transport`, `http_host`,
  `http_port`, `http_path`, `http_auth_enabled`); no statelessness fields yet.
- `src/netmiko_mcp/http_auth.py`: pure-ASGI `BearerTokenMiddleware` — transport-agnostic,
  expected to work unchanged against the new ASGI app.
- Tests: HTTP covered only by mocked unit tests; live suite (`test_integration.py`) is
  stdio-only.

---

## 2. Design

### 2.1 New configuration fields (decided)

Add to `McpConfig` "Transport" section:

- `http_stateless: bool = Field(default=True)` — env `NETMIKO_MCP_HTTP_STATELESS`.
  Stateless by default.
- `http_json_response: bool = Field(default=True)` — env
  `NETMIKO_MCP_HTTP_JSON_RESPONSE`. Plain `application/json` responses by default (most
  proxy/LB friendly; netmiko-mcp tools are single-response so nothing is lost).

Both are HTTP-transport-only; no effect under `stdio` (same as the other `http_*` fields).

### 2.2 FastMCP → MCPServer migration (the major change)

- Replace `from mcp.server.fastmcp import FastMCP` with `from mcp.server import MCPServer`.
- Replace `mcp = FastMCP("netmiko-mcp", instructions=..., host=, port=,
  streamable_http_path=)` with `mcp = MCPServer(name="netmiko-mcp", instructions=...,
  version=<pkg version>)` — drop host/port/path from construction.
- Keep all `@mcp.tool()` + `@check_startup_error` decorators as-is (verify the tool
  return-type handling in 2.0.0 accepts our `str | list | dict` returns; adjust
  `structured_output` per-tool only if needed).
- Rework `_run_http()`: build the ASGI app via
  `mcp.streamable_http_app(streamable_http_path=settings.http_path,
  json_response=settings.http_json_response, stateless_http=settings.http_stateless,
  host=settings.http_host)`, then wrap with `BearerTokenMiddleware` (unchanged) and run
  under uvicorn with `settings.http_host`/`settings.http_port`.
- Keep stdio path `mcp.run(transport="stdio")`.
- Per prior decision (Option A), keep construction in place at module import time; do not
  introduce a `build_mcp_server()` factory (recorded as a future-refactor issue in
  `AGENTS.md`). Note testability caveat still applies.

### 2.3 Backwards compatibility

- Tool names, arguments, and behavior: unchanged.
- stdio: unchanged behavior.
- HTTP operators can restore stateful/handshake behavior via `http_stateless: false`
  (subject to what the 2.0.0 SDK actually supports — see Open Questions Q-A).
- Bearer-token auth, host/port/path, audit logging: unchanged.

### 2.4 Out of scope (explicitly not implemented now)

Not implementing custom use of MRTR (`input_required`), routable-header-based routing,
or cacheable-discovery hints. netmiko-mcp tools do not need them. They are noted as
possible future enhancements only.

---

## 3. Task List

### Task 0 — Dependency upgrade (DONE, pending validation)
- [x] `pyproject.toml` `mcp>=2.0.0`; `uv lock`; `uv sync --frozen`.
- [ ] Decide/adjust `uvicorn` floor (`>=0.48.0` → `>=0.49.0`?).
- [ ] `uv run --frozen pip-audit --ignore-vuln ...` clean on the new tree.
- **Verify:** lock resolves; environment syncs (both confirmed).

### Task 1 — Config fields  *(DONE)*
- [x] Add `http_stateless` (default `True`) and `http_json_response` (default `True`) to
      `McpConfig` under the Transport section, with explanatory comments.
- [x] Add config unit test `test_mcp_config_http_stateless_env_and_yaml` (defaults, YAML,
      env-over-YAML precedence) and extend `test_mcp_config_defaults`.
- **Verified:** `ruff format --check` + `ruff check` clean; `mypy src/netmiko_mcp/config.py
      tests/test_config.py` clean; `pytest tests/test_config.py` 16 passed.
- **Env note:** the `.venv` was built on CPython 3.13.0b2 (beta), whose missing
      `_PyBytes_Join` symbol broke mypy's compiled binary (and pytest via the pytest-mypy
      plugin). Rebuilt the venv on stable `/usr/bin/python3.13` (3.13.14) from the frozen
      lock (`uv sync --frozen -p /usr/bin/python3.13`) — no dependency changes.
- **Note:** full-suite `mypy src tests` / `pytest` still fail until Task 2, because
      `server.py` imports the removed `mcp.server.fastmcp`.

### Task 2 — Migrate `server.py` FastMCP → MCPServer  *(DONE — approved)*
- [x] Swapped import (`from mcp.server import MCPServer`) and construction
      (`MCPServer(name=, instructions=, version=)`; version resolved via
      `importlib.metadata`). Dropped host/port/path from construction.
- [x] Preserved all 7 tools + `@check_startup_error`; `list_tools()` generates schemas
      cleanly for the `str | list | dict` return types (no `structured_output` overrides
      needed).
- [x] Reworked `_run_http()` to call `streamable_http_app(streamable_http_path=,
      json_response=settings.http_json_response, stateless_http=settings.http_stateless,
      host=settings.http_host)` then wrap with `BearerTokenMiddleware` + uvicorn. Passing
      `host` preserves the SDK's localhost DNS-rebinding auto-protection.
- [x] Kept stdio dispatch (`mcp.run(transport="stdio")`).
- **Verified:** import OK; `ruff format --check` + `ruff check` clean; `mypy src tests`
      clean (18 files); full unit suite `428 passed, 13 skipped`; coverage 99.03%
      (server.py 100%).

### Task 3 — `_run_http()` / startup validation review  *(DONE)*
- [x] `_validate_startup`, `_get_bearer_token`, and audit config unchanged and verified
      by the existing `test_server.py` / `test_http_server.py` (73 passed).
- [x] `BearerTokenMiddleware` wraps the new ASGI app identically (verified by
      `test_run_http_wraps_app_with_auth_middleware_when_enabled`).

### Task 4 — Config unit tests (`tests/test_config.py`)  *(DONE — in Task 1 commit)*
- [x] Defaults `http_stateless is True`, `http_json_response is True`
      (`test_mcp_config_defaults`).
- [x] YAML sets the NON-default (`False`) and env overrides it (`True`) proving both
      YAML read and env>YAML precedence (`test_mcp_config_http_stateless_yaml_and_env_
      precedence`). Validity proven via mutation testing (yaml-ignored / env-ignored /
      wrong-default all fail the tests).
- **Verified:** `pytest tests/test_config.py` 16 passed.

### Task 5 — Server/HTTP unit tests  *(DONE)*
- [x] Updated FastMCP→MCPServer references in `test_server.py` docstrings
      (`test_mcp_initialization`, decorator-metadata test).
- [x] `_run_http()` still wraps `BearerTokenMiddleware` when auth enabled — existing
      `test_run_http_wraps_app_with_auth_middleware_when_enabled` retained and passing.
- [x] Added `test_run_http_forwards_transport_settings_to_streamable_http_app` and a
      complementary `test_run_http_forwards_stateless_true_json_true` proving
      `http_path` / `http_json_response` / `http_stateless` / `http_host` flow into
      `mcp.streamable_http_app(...)`. Non-default values used so the assertions are
      non-tautological; proven by mutation (hard-coding `stateless_http=True` fails the
      test).
- **Verified:** `pytest tests/test_server.py tests/test_http_server.py` 91 passed; full
      suite 430 passed / 13 skipped; coverage 99.03% (server.py 100%).

### Task 6 — Behavioral HTTP test (in-process ASGI, no device)
- [ ] Drive `mcp.streamable_http_app(stateless_http=True, json_response=True, ...)` in
      process via an HTTP client; verify `initialize`/`tools/list`/`ping` succeed without
      requiring `Mcp-Session-Id`, and response content-type is `application/json`.
- [ ] Contrast case with `stateless_http=False` (session behavior), if supported by 2.0.0.
- **Verify:** `uv run --frozen pytest -v` on the new module.

### Task 7 — Live integration verification (`RUN_LIVE_TESTS=1`)
- [ ] Add a NEW subprocess-based HTTP live fixture in `conftest.py` (loopback host/port,
      generated `NETMIKO_MCP_HTTP_BEARER_TOKEN`, reusing the existing test config wiring
      and `_require_inventory()` guard). Drive via the 2.0.0 HTTP client.
- [ ] Test body: (1) 401 on wrong/missing token; (2) initialize with valid token;
      (3) assert statelessness on the wire (no required session id);
      (4) `ping` → `"pong"`; (5) `send_show_command` `show version` on `cisco1` contains
      `show_version_contains`; (6) optional `application/json` content-type assertion.
- [ ] Optional contrast: `http_stateless=false` variant.
- [ ] `show version` already whitelisted in `tests/etc/commands.yml`; add commands only
      if a new case requires it.
- **Verify:** `RUN_LIVE_TESTS=1 uv run --frozen pytest -v tests/test_integration.py`
      (full suite, stdio + new HTTP cases).

### Task 8 — Documentation updates
- [ ] `docs/configuration.md`: add `http_stateless` / `http_json_response` (table +
      details), measured language, no absolutes.
- [ ] `skills/netmiko-mcp/SKILL.md`: add fields; note `mcp>=2.0.0` / MCPServer.
- [ ] `skills/mcp-http-transport/SKILL.md`: correct the SSE-vs-Streamable table;
      describe stateless-by-default (`2026-07-28`) vs legacy handshake, trade-offs, and
      the opt-out.
- [ ] `README.md`: update HTTP "How This Works"; bump any stated client/version support
      only where tested.
- [ ] `tests/etc/netmiko-mcp.yml`: commented example of the new fields.
- **Verify:** manual review; cross-links resolve; no secrets; only document what's tested.

### Task 9 — Version + changelog
- [ ] Bump `pyproject.toml` project version `0.2.0` → `0.3.0`.
- [ ] Update `TODO.md`/changelog notes as applicable.
- **Verify:** `git diff` review.

### Task 10 — Full quality gate before commit
- [ ] `cd netmiko_mcp && ./tests.sh` (ruff format, ruff check, mypy, pytest).
- [ ] `uv run --frozen ruff format --check .` / `ruff check .` / `mypy src tests`.
- [ ] `uv run --frozen pytest -v`; then `RUN_LIVE_TESTS=1 uv run --frozen pytest -v
      tests/test_integration.py` (significant change).
- [ ] Coverage still ≥ `fail_under = 98`.
- [ ] `uv run --frozen pip-audit --ignore-vuln ...` clean.
- [ ] `git diff` / `git status` review; no secrets staged.
- **Verify:** all gates green.

---

## 4. Risks / Considerations

- **Major SDK breaking change:** whole server transport layer moves FastMCP → MCPServer.
  Higher blast radius than the original flag-only plan; needs approval.
- **Dependency churn:** `httpx`→`httpx2`, new `opentelemetry-api`/`truststore`/`mcp-types`.
  Test code and `pip-audit` must be re-validated; possible transitive incompatibilities.
- **Client compatibility:** clients must speak the `2026-07-28` stateless envelope (or the
  server must still negotiate legacy handshake revisions). Confirm which clients in the
  README support matrix have been verified against 2.0.0 before claiming support.
- **`json_response=true` default:** second behavior change; per-client validation needed.
- **Coverage target (98%):** new branches must be exercised.
- **Import-time construction (Option A):** flag-value unit testing relies on config tests
  + call-arg spying + the behavioral test, not direct reconstruction.

---

## 5. Decisions (locked)

- **D1 Field name:** `http_stateless` (env `NETMIKO_MCP_HTTP_STATELESS`).
- **D2 json_response:** add `http_json_response`, default `true` (plain JSON).
- **D3 Default:** stateless by default for all HTTP deployments; stateful opt-out.
- **D4 Scope:** HTTP-transport-only; no effect under stdio.
- **D5 Refactor approach:** Option A (minimal in-place; no factory). Factory recorded as
  a future-refactor issue in `AGENTS.md`. (Note: the FastMCP→MCPServer migration itself
  is unavoidably larger than "in-place flag add" and needs approval — see Q-C.)
- **D6 Version:** `pyproject.toml` `0.2.0` → `0.3.0`.
- **D7 SDK:** upgrade to `mcp>=2.0.0` (done in pyproject + lock).
- **D8 Live HTTP test:** new subprocess-based streamable-http live harness against
  `cisco1`, body as in Task 7.
- **D9 Opt-out (Q-A):** keep the `http_stateless` config field (default `true`) for
  backwards compatibility; on 2.0.0 its effect is limited to legacy (2025-era) clients.
- **D10 Feature scope (Q-F):** skip MRTR, routable-header routing, and cacheable-discovery.
- **D11 Dependencies (Q-D):** accept 2.0.0 transitive churn; `uvicorn` floor → `>=0.49.0`.

## 6. Open Questions

- **Q-A Legacy handshake / backwards compat semantics** — mechanics now VERIFIED in
  `mcp/server/streamable_http_manager.py`. Dispatch is per-request by the client's
  `MCP-Protocol-Version` header:
  - Client declares `2026-07-28` (modern) → always the modern **stateless** envelope
    (`handle_modern_request`); `http_stateless` is **ignored** for these clients.
  - Client declares a legacy version (`2024-11-05`…`2025-11-25`) or none →
    `http_stateless=True` gives a legacy-**stateless** path (`mcp_session_id=None`, no
    tracking); `http_stateless=False` gives the legacy-**stateful** path (`Mcp-Session-Id`,
    session tracking, idle timeout, event store / resumable streams).
  So `http_stateless` only governs **legacy handshake-era clients**, and only for features
  netmiko-mcp does not use. **DECIDED:** keep the `http_stateless` field (default `true`)
  as a backwards-compat opt-out for legacy clients. Docs must state that on `mcp` 2.0.0
  the flag only affects legacy (2025-era) clients — modern `2026-07-28` clients are always
  stateless — and that `http_stateless=false` requires LB session affinity.

- **Q-B Client support matrix:** The README lists verified clients (Claude Code, Desktop,
  Cursor, Devin, VS Code). Have any been tested against a `2026-07-28` / `mcp` 2.0.0
  stateless server, or should the support matrix be marked "pending re-verification"
  until we test?

- ~~**Q-C Refactor approval**~~ — **APPROVED:** proceed with Task 2 (FastMCP → MCPServer
  migration, Option A, in-place `MCPServer`).

- ~~**Q-D Dependency posture**~~ — **DECIDED (accepted):** accept the `httpx`→`httpx2`,
  `opentelemetry-api`, `truststore`, `mcp-types`, `httpcore2` transitive changes from
  2.0.0; `uvicorn` floor bumped `>=0.48.0` → `>=0.49.0` in `pyproject.toml` (done).
  Still to verify during implementation: dev tests importing `httpx` and a clean
  `pip-audit`.

- **Q-E Spec citation in docs:** Now that the SDK genuinely implements `2026-07-28`, may I
  cite that revision explicitly in the docs (it is verifiable in `mcp_types.version`), or
  still prefer generic "stateless deployment" wording per the measured-language rule?

- ~~**Q-F Feature adoption**~~ — **DECIDED (skip all three):** NOT adopting MRTR
  (`input_required`), routable-header routing, or cacheable-discovery in this change.
  Scope = statelessness + JSON responses + FastMCP→MCPServer migration only. The three
  are noted as possible future enhancements (§2.4).
