# Netmiko MCP Server - Strategic Planning

This document outlines the high-level architecture, design considerations, and roadmap for building the Netmiko MCP (Model Context Protocol) server. Integrating an LLM with live network devices requires strict controls, efficient data handling, and robust security.

## 1. Safety, Security, and Structural Guardrails
* **Read-Only vs. Read-Write Modes:** The MCP server should have a configuration flag to run in "Read-Only" mode where `send_config_set` tools are entirely hidden from the LLM.
* **Blast Radius Limits:** Implement constraints on how many devices the LLM can touch in a single request or timeframe. [NOT DONE]
* **Human-in-the-loop (HITL):** For config changes, consider a mechanism where the MCP server stages the change, requiring a secondary approval step before actual execution. [NOT DONE AS CONFIG MODE HAS NOT BEEN IMPLEMENTED]

## 2. State Management and Connection Pooling
* **The Cost of SSH:** Establishing an SSH connection to a network device is time-consuming (often 3-10 seconds). Opening a new connection for every single tool call will result in a frustratingly slow LLM experience.
* **Concurrency:** Network I/O is slow. We should design the tools to leverage concurrency where possible (likely utilizing a threading solution), allowing the LLM to query multiple devices concurrently if needed.

See TODO.md for outstanding connection pooling and stale session detection tasks.

## 3. Handling Context Windows & Output Management
* **Structured Data (ntc-templates/TextFSM):**
    * We should heavily lean on Netmiko's built-in `use_textfsm=True` functionality using ntc-templates.
    * Returning parsed JSON lists of dictionaries is *much* more token-efficient and easier for the LLM to reason about than raw fixed-width CLI text.
    * Tools should have an option for the LLM to request raw text vs. structured data.

See TODO.md for outstanding output truncation and pagination tasks.

## 4. Device Credentials Handling
* **No Plaintext in Prompts:** The LLM should *never* be asked to generate or pass passwords as arguments to the tool.
* **Credential Resolution:** 
    * The MCP server should handle credential resolution internally. 
    * The LLM should only provide the `host` or `group` names for device identification.
    * The MCP server can look up credentials via environment variables (including .env file), a local `netmiko.yml` file with encryption support, use SSH keys, or use an SSH agent (keys). [CURRENTLY netmiko.yml w/ encryption]

## 5. Additional High-Level Topics to Consider

* **Error Handling & LLM Feedback Loop:** 
    * How do we handle SSH timeouts, auth failures, or invalid syntax? 
    * The tools must catch Netmiko exceptions (like `NetmikoTimeoutException` or `NetmikoAuthenticationException`) and return them as clear, human-readable string messages to the LLM. If the LLM sees "Authentication failed for user X", it knows to stop trying or ask the user.
* **Audit Logging:** 
    * Every command executed by the LLM MUST be logged locally (or to syslog) with timestamps. If the network goes down, the network engineers need to know exactly what the AI agent did.
* **Device Inventory (MCP Resources):** 
    * MCP supports "Resources" (read-only data) in addition to "Tools" (actions). 
    * We could expose an inventory file (like a NetBox export or a YAML inventory) as an MCP Resource. The LLM can read this resource to discover what devices exist before deciding which ones to connect to.
* **Pre-packaged Workflows (MCP Prompts):**
    * MCP supports "Prompts". We could provide built-in templates like "Troubleshoot OSPF on device X" which instructs the LLM on exactly which Netmiko tools to call in sequence to diagnose an issue effectively.
* **Idempotency & Config Rollbacks:**
    * If a configuration change is pushed, does it support rollback? For platforms that support candidate configurations (Junos, IOS-XR, EOS), we should expose tools for `commit check` and `commit confirmed` to prevent the AI from locking us out.

## 6. Deployment Considerations

* **Host Execution Isolation:**
    * Administrators deploying this MCP server must ensure the Python process does not run as root or Administrator. It should be run inside an isolated user space (or a rootless Docker container) with minimal permissions on the underlying host operating system.
* **Network Device Authorization:**
    * The network credentials supplied to the MCP server's environment configuration should belong to a dedicated service account on the network. The deployment engineer should configure this account on the AAA/TACACS+ server to have the minimum necessary permissions.
