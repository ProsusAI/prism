# Security Policy

## Supported versions

Prism is released from the `main` branch. Security fixes are applied to the latest release. As an early-stage project (pre-1.0), we support only the most recent version.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, use one of the following private channels:

1. **GitHub private vulnerability reporting** (preferred): go to the **Security** tab of the repository → **Report a vulnerability**.
2. **Email:** `lara.baseggio@prosus.com`

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce or a proof of concept
- Affected version / commit
- Any suggested mitigation

We will acknowledge receipt within **5 business days** and aim to provide an assessment and remediation timeline within **15 business days**. Please give us a reasonable opportunity to address the issue before any public disclosure.

## Scope and design notes

Prism is a local-first tool. A few security-relevant design points worth knowing when assessing reports:

- **Secret scrubbing** runs before any observation is persisted. Baseline patterns are hardcoded and cannot be disabled (`lib/scrub.py`).
- **AI calls** are made only through the locally authenticated IDE CLIs (`claude` / `agent`). Prism does not handle or store API keys.
- **Hooks** only spawn background work and always exit 0; they never block the IDE.
- **The registry token** shipped in `install.sh` is a **read-only** token for the public skills registry. It grants no write access.
- **MCP server** communicates over stdio (JSON-RPC); it reads `~/.prism` and the project directory.

If you find a way to exfiltrate secrets past the scrubber, escalate registry privileges, or achieve code execution via a hook or MCP tool, we want to hear about it.
