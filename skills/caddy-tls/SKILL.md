---
name: caddy-tls
description: TLS termination for netmiko-mcp using Caddy as a reverse proxy. Covers installation on Debian/Ubuntu and Fedora/RHEL, Caddyfile configuration for internal CA (lab use) and public Let's Encrypt, and startup options.
---

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
