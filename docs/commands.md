# Netmiko MCP — commands.yml

The `commands.yml` file defines what the LLM is and is not allowed to send to network
devices. By default the server should deny all commands. No commands should be permitted 
until you explicitly allow it.

The path to this file is controlled by the `command_file` setting in your
[configuration file](configuration.md). It defaults to `~/commands.yml`.

> **Note:** `commands.yml` is loaded and cached at startup. Changes to the file require a server restart to take effect — there is no live reload.
<br />
<br />

## File Structure

```yaml
---
allowed_commands:
  - "show version"
  - "show ip route *"

denied_commands:
  - "configure*"
  - "reload*"
```

Both lists are optional. An empty or missing `allowed_commands` means nothing is permitted.

An empty or missing `denied_commands` means no extra command blocking. Even with an empty
`denied_commands` list, the command must still pass allowed_commands check. Additionally,
it must also pass through the [allowed characters](#allowed-characters) check and
[allow pipe](configuration.md).
<br />
<br />

## Matching Rules

Both `allowed_commands` and `denied_commands` use identical matching rules:

- A **plain string** matches only that exact command (case-insensitive, anchored at both ends).
- A **glob pattern** containing `*` matches the command prefix plus additional text.
- `denied_commands` **always takes precedence** over `allowed_commands`. If a pattern
  matches both lists, it is denied.
<br />
<br />

### Exact matching

```yaml
allowed_commands:
  - "show version"
```

| Command sent | Result |
|---|---|
| `show version` | ✅ allowed |
| `SHOW VERSION` | ✅ allowed (case-insensitive) |
| `show version detail` | ❌ denied — extra text not matched |
| `show versio` | ❌ denied — must be exact |

> **Note:** Command abbreviations are not supported. `sh ver` will not match
> `show version`. Users and the LLM should send fully-expanded commands.
<br />
<br />

### Glob matching

Two glob forms are supported:

- **Inline glob** (`"show version*"`) — matches the bare prefix and any suffix:
  `show version`, `show versions`, and `show version detail` all match.
- **Space glob** (`"show version *"`) — requires at least one additional word after
  the prefix: `show version detail` matches, but `show version` alone does **not**.

```yaml
allowed_commands:
  - "show version *"
```

| Command sent | Result |
|---|---|
| `show version` | ❌ denied — space-glob requires at least one extra word |
| `show version detail` | ✅ allowed |
| `show version \| include IOS` | ✅ allowed (if pipes are enabled) |

Use an inline glob to also permit the bare command:

```yaml
allowed_commands:
  - "show version*"
```

| Command sent | Result |
|---|---|
| `show version` | ✅ allowed |
| `show versions` | ✅ allowed |
| `show version detail` | ✅ allowed |


```yaml
allowed_commands:
  - "show ip *"
```

| Command sent | Result |
|---|---|
| `show ip route` | ✅ allowed — "route" satisfies the extra word |
| `show ip interface brief` | ✅ allowed |
| `show ip bgp neighbors 10.0.0.1` | ✅ allowed |
| `show ip` | ❌ denied — space-glob requires at least one extra word |
| `show version` | ❌ denied — prefix doesn't match |
<br />
<br />

## `allowed_commands`

The explicit whitelist. The LLM may only send commands that match at least one entry. The
base command (the part before any `|` pipe) is what is matched.

### Realistic example

```yaml
allowed_commands:
  # Exact matches
  - "show version"
  - "show ip interface brief"
  - "show interfaces"
  - "show cdp neighbors detail"

  # Inline glob — matches bare command and any arguments
  - "show ip route*"
  - "show ip bgp*"
  - "show interfaces*"
  - "show logging*"

  # Multi-vendor
  - "display version"
  - "display interface brief"
  - "display ip routing-table*"
```
<br />
<br />

## `denied_commands`

An explicit denylist that has precedence over `allowed_commands`. Uses the same 
exact/glob matching. Useful for blocking specific destructive commands even if a 
broader glob would otherwise allow them.
<br />
<br />

### Behavior

- `"reload"` — blocks only the bare command `reload`. Does **not** block
  `show reload-cause` because matching is anchored at both ends, not a substring search.
- `"reload *"` — blocks `reload in 5`, `reload cancel`, etc. Does **not** block bare
  `reload` alone — use `"reload"` or `"reload*"` for that.
- `"reload*"` — blocks `reload`, `reload in 5`, `reload cancel`, etc.
- `"configure *"` — blocks `configure terminal`, `configure replace flash:cfg`, etc.
  Does **not** block bare `configure` alone.

### Example

```yaml
denied_commands:
  - "configure *"    # blocks all configure variants
  - "reload"         # blocks only the bare reload command
  - "reload *"       # blocks reload with any arguments
  - "clear *"        # blocks all clear commands
  - "debug *"        # blocks all debug commands
  - "no *"           # blocks all no commands
```

> **Tip:** `denied_commands` is most useful when you have broad glob patterns in
> `allowed_commands` and want to carve out specific exceptions. For example, allowing
> `"show *"` while denying `"show running-config"`.
<br />
<br />

## Allowed Characters

Before any whitelist or glob matching takes place, every incoming command is checked
against `allowed_command_chars` (configured in [configuration.md](configuration.md)).
Any character not in the allowed set causes immediate rejection.

This allowlist approach is more robust than enumerating forbidden characters — it
handles Unicode space lookalikes, and novel injection characters without (hopefully)
requiring updates to the character list.

**Default allowed characters:** `a-z A-Z 0-9` and `<space> . / : _ - , "`

Notably absent from the default (rejected unless explicitly added):

| Character(s) | Why excluded |
|---|---|
| `;` `&` | Command chaining / background execution injection |
| `\|` | Managed separately via `allow_pipe` |
| `\t` `\n` `\r` and other whitespace | Normalized to space before the check (see below) |
| Unicode spaces (NBSP, ideographic, etc.) | Handled by normalization or rejected as disallowed |
| `'` `` ` `` `$` `!` `\\` | Shell metacharacters |
<br />
<br />

### Whitespace normalization

Before the character check, the server normalizes all whitespace in the command:
- All runs of ASCII whitespace (spaces, tabs, `\t`, `\n`, `\r`, `\x0b`, etc.) are
  collapsed to a single ASCII space.
- Leading and trailing whitespace is stripped.

This normalized form is what is validated against the allowed/denied lists **and what
is forwarded to the network device**. Capitalization is preserved exactly as submitted.

> **Example:** `"Show   IP   Route"` is normalized to `"Show IP Route"` before
> matching and before being sent to the device.
<br />
<br />

### Extending the allowed character set

If your platform requires characters not in the default set (e.g. `"` for IOS-XR
inline egrep patterns, or `[` `]` for Junos range syntax), add them in
`~/.netmiko-mcp.yml`:

```yaml
# in ~/.netmiko-mcp.yml
allowed_command_chars: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,\""
```

> **Note:** The pipe character `|` must not be added here when `allow_pipe` is `false`.
> Enable pipe support via `allow_pipe: true` — the server adds `|` to the effective
> allowed set automatically.
<br />
<br />

## Pipe Support

By default, pipe operators (`|`) are **disabled**. Enable them in your
[configuration file](configuration.md):

```yaml
allow_pipe: true
```
<br />
<br />

### `pipe_modifiers`

Controls which keywords are permitted after `|`. Default (IOS/IOS-XE):

```yaml
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]
```

```
# allow_pipe: true, pipe_modifiers includes "include" and "section"

show version | include IOS          ✅ allowed
show ip route | section 10.0.0      ✅ allowed
show version | count                ✅ allowed
show bgp summary | include Active   ✅ allowed (if "show bgp *" is in allowed_commands)

show version |                      ❌ denied — nothing after pipe
show version | include IOS | count  ❌ denied — multiple pipes
show version | grep IOS             ❌ denied — "grep" not in default pipe_modifiers
show running-config | include int   ❌ denied — base command not in allowed_commands
show version | awk '{print $1}'     ❌ denied — "awk" not in pipe_modifiers
```
<br />
<br />


## Globbing Reference

The `*` wildcard in patterns matches any character. Commands are validated against
`allowed_command_chars` before glob matching, so the wildcard can only ever expand
across characters already confirmed to be permitted.

| Pattern | Matches | Does not match |
|---|---|---|
| `"show version"` | `show version` | `show version detail`, `sh ver` |
| `"show version*"` | `show version`, `show versions`, `show version detail` | `sh ver`, `show ip route` |
| `"show version *"` | `show version detail` | `show version`, `show versio`, `sh ver detail` |
| `"show ip *"` | `show ip route`, `show ip int brief`, `show ip bgp summary` | `show ip`, `show version`, `show ipv6 route` |
| `"show *"` | `show version`, `show ip route` | `show`, `sh ver`, `configure terminal` |
| `"debug *"` | `debug ip packet`, `debug ip ospf adj` | `debug`, `show debug` |
| `"show ip route *"` | `show ip route 10.0.0.0` | `show ip route`, `show ip interface` |
<br />
<br />

### Interaction between `allowed_commands` and `denied_commands` globs

```yaml
allowed_commands:
  - "show *"          # allow all show commands

denied_commands:
  - "show r*"   # Deny show run variants (tricky due to command abbreviations)
  - "show s*"   # Deny show start variants (tricky due to command abbreviations)
```

| Command | Outcome |
|---|---|
| `show version` | ✅ allowed by `show *` |
| `show ip interface brief` | ✅ allowed by `show *` |
| `show running-config` | ❌ denied — deny overrides the glob allow |
| `show startup-config` | ❌ denied — deny overrides the glob allow |
<br />
<br />


## Validation Pipeline

Every command passes through these steps in order. The first failure stops processing.

```
1. Whitespace normalization  — collapse all ASCII whitespace runs to single space,
                               strip leading/trailing whitespace
2. Allowed character check   — rejects if any character is not in allowed_command_chars
                               (plus '|' when allow_pipe is true)
3. denied_commands check     — rejects if the base command (before any pipe) matches
                               any denied pattern
4. Pipe check                — rejects if pipe modifier is not in pipe_modifiers,
                               or if there are multiple pipes,
                               or if nothing follows the pipe
5. allowed_commands check    — rejects if the base command matches no allowed pattern
```
<br />
<br />


## Full Example

```yaml
---
# ~/commands.yml

allowed_commands:
  # System state
  - "show version"
  - "show clock"
  - "show uptime"

  # Interfaces
  - "show interfaces *"
  - "show ip interface *"
  - "show interface status"

  # Routing
  - "show ip route*"
  - "show ip bgp*"
  - "show ip ospf*"
  - "show ip eigrp*"

  # Switching
  - "show vlan*"
  - "show mac address-table*"
  - "show spanning-tree*"

  # Device discovery
  - "show cdp neighbors*"
  - "show lldp neighbors*"

  # Logs
  - "show logging*"

denied_commands:
  # Never allow show run or show start (tricky because of command abbreviations).
  - "show r*"
  - "show st*"
```
