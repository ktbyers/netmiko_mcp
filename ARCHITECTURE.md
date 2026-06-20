# Netmiko MCP Server - Strategic Planning

This document outlines the high-level architecture, design considerations, and roadmap for building the Netmiko MCP (Model Context Protocol) server. Integrating an LLM with live network devices requires strict controls, efficient data handling, and robust security.

## 1. Additional High-Level Topics to Consider

* **Idempotency & Config Rollbacks:**
    * If a configuration change is pushed, does it support rollback? For platforms that support candidate configurations (Junos, IOS-XR, EOS), we should expose tools for `commit check` and `commit confirmed` to prevent the AI from locking us out.

## 2. Deployment Considerations

* **Host Execution Isolation:**
    * Administrators deploying this MCP server must ensure the Python process does not run as root or Administrator. It should be run inside an isolated user space (or a rootless Docker container) with minimal permissions on the underlying host operating system.
* **Network Device Authorization:**
    * The network credentials supplied to the MCP server's environment configuration should belong to a dedicated service account on the network. The deployment engineer should configure this account on the AAA/TACACS+ server to have the minimum necessary permissions.
