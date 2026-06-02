# Netmiko MCP Server

> **WARNING:** You can make serious, incredibly detrimental mistakes by using this tool. This tool could cause massive outages in your environment. You, and you alone, are solely responsible for using this tool. Don't say I didn't warn you.

## Configuration

The Netmiko MCP Server requires configuration to understand where your inventory lives and what commands are permitted.

### 1. Global Configuration File
By default, the server looks for a configuration file at **`~/.netmiko-mcp.yml`** (in your home directory).
You can override this location by setting the **`NETMIKO_MCP_CONFIG`** environment variable.

Create a `~/.netmiko-mcp.yml` file with the following minimum required settings:

```yaml
---
inventory_type: "netmiko_tools"
# Optional: explicitly point to your .netmiko.yml inventory (defaults to standard Netmiko search paths)
inventory_file: "~/.netmiko.yml"
# Required: Explicitly point to your commands.yml whitelist
command_file: "~/commands.yml"
# Optional: Allow safe piping logic (e.g. | include)
allow_pipe: true
```

*Note: Environment variables prefixed with `NETMIKO_MCP_` (e.g., `NETMIKO_MCP_ALLOW_PIPE=false`) will always override the values inside the YAML file.*

### 2. Device Inventory and Credentials
Because `inventory_type` is set to `netmiko_tools`, the server natively uses the standard Netmiko Tools YAML inventory format.
- Create your `~/.netmiko.yml` file containing your devices and encrypted credentials.
- Ensure you have the `NETMIKO_TOOLS_KEY` environment variable exported in the shell where your MCP client runs so the server can decrypt the credentials securely.

### 3. Security Whitelist
Create a `~/commands.yml` file to restrict what the LLM is allowed to do. By default, the server strictly denies *all* commands unless they are explicitly whitelisted.

```yaml
---
# Exact matches or globs (*) permitted
allowed_commands:
  - "show version *"
  - "show ip interface brief"

# Commands that are instantly blocked regardless of whitelist
denied_commands:
  - "configure terminal"
  - "reload"
```
