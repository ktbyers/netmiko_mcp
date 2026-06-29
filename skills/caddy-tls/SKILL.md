---
name: caddy-tls
description: TLS termination for netmiko-mcp using Caddy as a reverse proxy. Covers installation on Debian/Ubuntu and Fedora/RHEL, Caddyfile configuration for internal CA (lab use) and public Let's Encrypt, startup options, NODE_EXTRA_CA_CERTS for Node-based MCP clients, and WSL2/Windows split-host setup.
---

> **For humans:** This file is reference documentation for setting up TLS with Caddy in front of netmiko-mcp. You can read it directly, but its real purpose is to be installed as a skill in your AI client — once loaded into your AI client's context, you can ask it to walk you through the setup and it already has all the details.

# TLS Termination with Caddy

> **Note:** Package names, repository URLs, and install commands change over time.
> Before running any install steps below, check the official Caddy documentation
> at https://caddyserver.com/docs/install for the current procedure.

Caddy is a reverse proxy that handles certificate provisioning automatically —
either via Let's Encrypt for public domains or an internal CA for private/lab use.

---

## Install Caddy

```bash
# Debian/Ubuntu
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# Fedora/RHEL/CentOS
sudo dnf install -y 'dnf-command(copr)'
sudo dnf copr enable -y @caddy/caddy
sudo dnf install -y caddy
```

---

## Caddyfile — internal CA (self-signed, lab use)

Bind the MCP server to loopback only (`http_host: "127.0.0.1"`), then let Caddy
accept external HTTPS and forward to it:

```
your-mcp-server.example.com {
    tls internal
    reverse_proxy localhost:8000
}
```

Caddy generates a local CA and issues a certificate automatically. The CA root is
stored at:

```
$(caddy environ | grep CADDY_DATA)/pki/authorities/local/root.crt
# Typically: ~/.local/share/caddy/pki/authorities/local/root.crt
```

---

## Caddyfile — public domain (automatic Let's Encrypt)

```
your-mcp-server.example.com {
    reverse_proxy localhost:8000
}
```

Caddy obtains and renews a public certificate automatically. Port 80 and 443 must
be reachable from the internet.

---

## Start Caddy

```bash
# Run in foreground
caddy run --config /path/to/Caddyfile

# Or as a systemd service (if installed via package manager)
sudo systemctl enable --now caddy
```

The MCP endpoint is then reachable at `https://your-mcp-server.example.com/mcp`.
The netmiko-mcp bearer auth is still enforced through the proxy.

---

## NODE_EXTRA_CA_CERTS (internal CA only)

Node.js-based MCP clients (mcp-remote, Claude Code's MCP layer, etc.) use Node's
own CA bundle rather than the OS trust store. When using `tls internal`, the Caddy
root cert must be passed explicitly or the client will reject the TLS connection.

Set `NODE_EXTRA_CA_CERTS` to the Caddy root cert path in the client's environment:

**Claude Code:**
```bash
claude mcp add -s user \
  -e NODE_EXTRA_CA_CERTS="$HOME/.local/share/caddy/pki/authorities/local/root.crt" \
  -e NETMIKO_MCP_HTTP_BEARER_TOKEN="Bearer your-token-here" \
  netmiko-mcp -- uv run netmiko-mcp
```

**Claude Desktop (via mcp-remote) — add to the `env` block:**
```json
"env": {
  "NODE_EXTRA_CA_CERTS": "/home/user/.local/share/caddy/pki/authorities/local/root.crt",
  "NETMIKO_MCP_HTTP_BEARER_TOKEN": "Bearer your-token-here"
}
```

`NODE_EXTRA_CA_CERTS` is not needed when using a public Let's Encrypt certificate —
Let's Encrypt is already trusted by Node's CA bundle.

---

## WSL2 / Windows Split-Host Setup

When Caddy and the netmiko-mcp server run inside WSL2 and the MCP client runs on
Windows:

**Localhost forwarding:** WSL2 forwards `127.0.0.1` from Windows to the WSL
listener automatically. Binding the MCP server to `127.0.0.1` (the default) is
sufficient — setting `http_host: "0.0.0.0"` is not necessary.

**CA cert:** The Caddy root cert lives inside the WSL filesystem. Copy it to a
Windows-accessible path and reference that path in `NODE_EXTRA_CA_CERTS`:

```bash
# Copy from WSL to Windows (run inside WSL)
cp ~/.local/share/caddy/pki/authorities/local/root.crt \
   /mnt/c/Users/<YourWindowsUsername>/caddy-root.crt
```

Then set in the Windows-side client config:
```
NODE_EXTRA_CA_CERTS=C:\Users\<YourWindowsUsername>\caddy-root.crt
```
