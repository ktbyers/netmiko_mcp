---
name: netmiko-tools-yml
description: Workflows and references for using the Netmiko CLI tools .netmiko.yml format for device inventory, credential management, and encryption.
---

> **For humans:** This file is reference documentation for the device inventory format used by netmiko-mcp. It is intended to be read and used by LLMs.

# Netmiko Tools YAML (.netmiko.yml)

The `.netmiko.yml` file is the standard inventory and credential storage mechanism for Netmiko's built-in CLI tools (`netmiko-show`, `netmiko-cfg`, `netmiko-grep`). For the Netmiko MCP server, this format is used to securely load device details without forcing the LLM to handle plaintext passwords.

## File Format

Contains an optional `__meta__` encryption config block and device blocks. Device blocks are dictionaries that unpack directly into Netmiko's `ConnectHandler`.

```yaml
__meta__:
  encryption: true
  encryption_type: fernet  # Options: fernet, aes128

cisco_router_1:
  device_type: cisco_ios
  host: 192.168.1.1
  username: admin
  password: >
    __encrypt__gAAAAABn... # Long encrypted string
```

## Environment Variables

- `NETMIKO_TOOLS_CFG`: Overrides the path to the configuration file (default behavior searches the current directory `./.netmiko.yml` then the home directory `~/.netmiko.yml`).
- `NETMIKO_TOOLS_KEY`: Master passphrase for encrypting/decrypting `__encrypt__` fields. Netmiko derives a cryptographic key from it using PBKDF2HMAC and a random salt.

## Python API for Loading (Important for MCP)

Use these built-in functions to resolve device names to connection parameters:

```python
from netmiko.utilities import find_cfg_file, load_yaml_file, obtain_all_devices

# Find the .netmiko.yml file while respecting the NETMIKO_TOOLS_CFG setting
try:
    cfg_file = find_cfg_file()
except ValueError as e:
    # Handle case where file is not found
    pass

# Parse the YAML file into a standard dictionary
parsed_yaml = load_yaml_file(cfg_file)

# Extract devices and decrypt their credentials.
# This automatically checks for NETMIKO_TOOLS_KEY and decrypts fields starting with __encrypt__
# and returns a dictionary of device connection parameters.
devices = obtain_all_devices(parsed_yaml)
```

## Encryption Management (CLI)

CLI utilities for encrypting passwords:
- `netmiko-encrypt <password>`: Encrypts a single string using the `NETMIKO_TOOLS_KEY` environment variable. It will output the `__encrypt__` string to be pasted into the YAML file.
- `netmiko-bulk-encrypt --input_file <file> --output_file <file>`: Safely encrypts an entire `.netmiko.yml` file in place.

---

## Credential Management

### What does NOT work

`${ENV_VAR}` interpolation in `.netmiko.yml` does not work. Netmiko uses `yaml.safe_load()` which parses values literally — the string `"${CORE01_PASSWORD}"` is passed directly to `ConnectHandler` as the password.

### Option 1: Netmiko built-in Fernet encryption (recommended for individuals/small teams)

Passwords in `~/.netmiko.yml` are replaced with `__encrypt__` ciphertext. The only secret to protect is `NETMIKO_TOOLS_KEY`. The encrypted inventory file is safe to commit.

**Step 1 — Create plaintext inventory with `__meta__` block:**
```yaml
---
__meta__:
  encryption: false
  encryption_type: fernet

core01:
  device_type: cisco_ios
  host: 192.168.1.1
  username: admin
  password: plaintext_password_here
  secret: plaintext_enable_secret_here
```

**Step 2 — Set passphrase and make it permanent:**
```bash
export NETMIKO_TOOLS_KEY="some long and strong passphrase"
echo 'export NETMIKO_TOOLS_KEY="some long and strong passphrase"' >> ~/.zshrc
```

**Step 3 — Encrypt (write to temp file first, verify, then replace):**
```bash
uv run netmiko-bulk-encrypt --input_file ~/.netmiko.yml --output_file ~/.netmiko_encrypted.yml
cat ~/.netmiko_encrypted.yml
cp ~/.netmiko_encrypted.yml ~/.netmiko.yml && rm ~/.netmiko_encrypted.yml
```

Do not use the same path for `--input_file` and `--output_file`.

**Step 4 — Manually update `__meta__`** (`netmiko-bulk-encrypt` does NOT do this automatically):
```yaml
__meta__:
  encryption: true   # must change false -> true or all connections will fail
  encryption_type: fernet
```

**Step 5 — Verify:** run `list devices` through the MCP server. Auth failures mean `__meta__` is still `false` or `NETMIKO_TOOLS_KEY` doesn’t match the passphrase used during encryption.

**Encrypt a single password:**
```bash
uv run netmiko-encrypt "the_password_to_encrypt"
# Output: __encrypt__<salt>:<ciphertext>
# Paste the full __encrypt__... string as the YAML value
```

Passing a password on the command line may save it in shell history — clear with `history -d $(history 1)`. Using `netmiko-bulk-encrypt` on the whole file avoids this.

**Trade-offs:**
- No external dependencies
- Passphrase is the single point of protection — if lost, encrypted credentials cannot be recovered without the original plaintext
- Passphrase must be distributed to every machine running the server

---

### Option 2: Generate inventory from a secrets manager (recommended for teams/production)

Pull credentials from an external store and write `.netmiko.yml` dynamically at startup. The on-disk file is ephemeral and never committed.

**1Password CLI:**
```bash
op item get "core01" --fields username,password --format json \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
creds = {f['label']: f['value'] for f in d}
print(f'''---
core01:
  device_type: cisco_ios
  host: 192.168.1.1
  username: {creds['username']}
  password: {creds['password']}
''')
" > ~/.netmiko.yml
uv run netmiko-mcp
```

**AWS Secrets Manager:**
```bash
SECRET=$(aws secretsmanager get-secret-value \
  --secret-id netmiko/core01 --query SecretString --output text)
python3 -c "
import json
d = json.loads('''$SECRET''')
print(f'''---
core01:
  device_type: cisco_ios
  host: 192.168.1.1
  username: {d['username']}
  password: {d['password']}
''')
" > ~/.netmiko.yml
uv run netmiko-mcp
```

**Trade-offs:**
- Credentials never touch disk long-term
- Requires secrets manager CLI/SDK on host
- Generated file exists in plaintext during server runtime — ensure `chmod 600 ~/.netmiko.yml`

---

### Comparison

| | Built-in encryption | Secrets manager |
|---|---|---|
| External dependency | None | Vault / 1Password / AWS / etc. |
| Secret to protect | `NETMIKO_TOOLS_KEY` | Secrets manager auth token |
| Plaintext on disk | Never | During server runtime only |
| Safe to commit | Yes (ciphertext) | No |
| Best for | Individual / small team | Team / production |

### What to avoid

- Plaintext passwords in `.netmiko.yml` — even in a private repo
- Credentials hardcoded in MCP client config files (`.cursor/mcp.json`, `claude_desktop_config.json`) — these files are often synced or backed up
- `NETMIKO_TOOLS_KEY` in a `.env` file that is committed — defeats encryption entirely
