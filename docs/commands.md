# Netmiko MCP — commands.yml

The `commands.yml` file defines what the LLM is and is not allowed to send to network
devices. By default the server denies **all** commands — nothing is permitted until you
explicitly allow it.

The path to this file is controlled by the `command_file` setting in your
[configuration file](configuration.md). It defaults to `~/commands.yml`.

---

## File Structure

```yaml
---
allowed_commands:
  - "show version"
  - "show ip route *"

denied_commands:
  - "configure *"
  - "reload"
```

Both lists are optional. An empty or missing `allowed_commands` means nothing is permitted.
An empty or missing `denied_commands` means no extra blocking beyond the
[unsafe characters](#unsafe-characters) check.

---

## Matching Rules

Both `allowed_commands` and `denied_commands` use identical matching rules:

- A **plain string** matches only that exact command (case-insensitive, anchored at both ends).
- A **glob pattern** containing `*` matches the command prefix with optional arguments.
- `denied_commands` **always takes precedence** over `allowed_commands`. If a command
  matches both lists, it is denied.

### Exact matching

```yaml
allowed_commands:
  - "show version"
```

| Command sent | Result |
|---|---|
| `show version` | ✅ allowed |
| `SHOW VERSION` | ✅ allowed (case-insensitive) |
| `show version detail` | ❌ denied — extra arguments not matched |
| `show versio` | ❌ denied — must be exact |

> **Note:** Command abbreviations are not supported. `sh ver` will not match
> `show version`. Users and the LLM must send fully-expanded commands.

### Glob matching

A `*` at the end of a pattern matches the bare command **or** the command followed by any
arguments (excluding [unsafe characters](#unsafe-characters)).

```yaml
allowed_commands:
  - "show version *"
```

| Command sent | Result |
|---|---|
| `show version` | ✅ allowed (bare, no args) |
| `show version detail` | ✅ allowed |
| `show version \| include IOS` | ✅ allowed (if pipes are enabled) |

A `*` in the middle of a pattern works the same way but anchors the prefix strictly:

```yaml
allowed_commands:
  - "show ip *"
```

| Command sent | Result |
|---|---|
| `show ip route` | ✅ allowed |
| `show ip interface brief` | ✅ allowed |
| `show ip bgp neighbors 10.0.0.1` | ✅ allowed |
| `show version` | ❌ denied — prefix doesn't match |

---

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

  # Glob patterns — allow a family of commands
  - "show ip route *"
  - "show ip bgp *"
  - "show interfaces *"
  - "show logging *"

  # Multi-vendor
  - "display version"
  - "display interface brief"
  - "display ip routing-table *"
```

---

## `denied_commands`

An explicit denylist that overrides `allowed_commands`. Uses the same exact/glob matching.
Useful for blocking specific destructive commands even if a broader glob would otherwise
allow them.

### Behavior

- `"reload"` — blocks only the bare command `reload`. Does **not** block
  `show reload-cause` because matching is anchored at both ends, not a substring search.
- `"reload *"` — blocks `reload`, `reload in 5`, `reload cancel`, etc.
- `"configure *"` — blocks `configure terminal`, `configure replace flash:cfg`, etc.

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

---

## Unsafe Characters

Before any whitelist or glob matching takes place, the server scans every incoming command
for characters defined in `unsafe_chars` (configured in
[configuration.md](configuration.md)). Any match causes immediate rejection.

**Default unsafe characters:** `;`  `\n` (newline)  `\r` (carriage return)  `&`

These block the most common shell-style command injection vectors:

| Character | Injection technique blocked |
|---|---|
| `;` | `show version; reload` |
| `\n` | Multi-line command injection |
| `\r` | Carriage-return injection |
| `&` | Background execution (`show version && reload`) |

This check happens **before** `denied_commands` and before `allowed_commands`. A command
containing an unsafe character is rejected regardless of what is in either list.

### Adding unsafe characters

If your environment requires additional blocking (e.g. you want to prevent all pipe usage
at the character level rather than via `allow_pipe`), you can add `|` to the list:

```yaml
# in ~/.netmiko-mcp.yml
unsafe_chars: [";", "\n", "\r", "&", "|"]
```

> **Warning:** Do not remove the defaults. Only add to this list.

---

## Pipe Support

By default, pipe operators (`|`) are **disabled**. Enable them in your
[configuration file](configuration.md):

```yaml
allow_pipe: true
```

### How pipe validation works

When a pipe is present the server:

1. Splits the command on the **first** `|` only.
2. Validates the **base command** (left of `|`) against `allowed_commands` as normal.
3. Checks that there is exactly **one** pipe — multiple pipes are always blocked.
4. Extracts the first keyword after the pipe and checks it against `pipe_modifiers`.
5. Rejects if the modifier keyword is not in the list or if nothing follows the pipe.

### `pipe_modifiers`

Controls which keywords are permitted after `|`. Default (IOS/IOS-XE):

```yaml
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]
```

Extend for NX-OS or other platforms:

```yaml
pipe_modifiers:
  - "include"
  - "exclude"
  - "section"
  - "begin"
  - "count"
  - "grep"
  - "egrep"
  - "json"
  - "json-pretty"
  - "xml"
  - "no-more"
  - "head"
  - "tail"
```

### Pipe examples

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

---

## Globbing Reference

The `*` wildcard in patterns is intentionally restricted — it will **never** match
[unsafe characters](#unsafe-characters). This means a wildcard can never be tricked into
spanning a command separator even if the unsafe character check were somehow bypassed.

| Pattern | Matches | Does not match |
|---|---|---|
| `"show version"` | `show version` | `show version detail`, `sh ver` |
| `"show version *"` | `show version`, `show version detail` | `show versio` |
| `"show ip *"` | `show ip route`, `show ip int brief`, `show ip bgp summary` | `show version`, `show ipv6 *` |
| `"show *"` | `show version`, `show ip route`, `show` | `sh ver`, `configure terminal` |
| `"debug *"` | `debug`, `debug ip packet`, `debug ip ospf adj` | `show debug` |
| `"show ip route *"` | `show ip route`, `show ip route 10.0.0.0` | `show ip interface` |

### Interaction between `allowed_commands` and `denied_commands` globs

```yaml
allowed_commands:
  - "show *"          # allow all show commands

denied_commands:
  - "show running-config"   # carve out this specific one
  - "show startup-config"   # and this one
```

| Command | Outcome |
|---|---|
| `show version` | ✅ allowed by `show *` |
| `show ip interface brief` | ✅ allowed by `show *` |
| `show running-config` | ❌ denied — exact deny overrides the glob allow |
| `show startup-config` | ❌ denied — exact deny overrides the glob allow |

---

## Validation Pipeline

Every command passes through these checks in order. The first failure stops processing.

```
1. Unsafe character check   — rejects if any unsafe_chars character is present
2. denied_commands check    — rejects if the full command matches any denied pattern
3. Pipe check               — rejects if pipe exists and allow_pipe is false,
                              or if the modifier is not in pipe_modifiers,
                              or if there are multiple pipes,
                              or if nothing follows the pipe
4. allowed_commands check   — rejects if the base command matches no allowed pattern
```

---

## Full Example

A production-style `commands.yml` for a read-only monitoring use case:

```yaml
---
# ~/commands.yml
# Read-only monitoring — IOS/IOS-XE and NX-OS

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
  - "show ip route *"
  - "show ip bgp *"
  - "show ip ospf *"
  - "show ip eigrp *"

  # Switching
  - "show vlan *"
  - "show mac address-table *"
  - "show spanning-tree *"

  # Device discovery
  - "show cdp neighbors *"
  - "show lldp neighbors *"

  # Logs
  - "show logging *"

  # NX-OS
  - "show vpc *"
  - "show port-channel *"

denied_commands:
  # Never allow config or destructive commands even if a broad glob matched
  - "show running-config"
  - "show startup-config"
```
