# Security Policy

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Use the private contact form at:

**https://sostcore.com/sost-contact.html**

Select "Security Vulnerability Report" as the subject. This ensures the report reaches maintainers privately before any public disclosure.

## What to include

- Description of the vulnerability
- Steps to reproduce
- Affected component (node, miner, wallet, P2P, RPC, consensus)
- Severity estimate (critical / high / medium / low)

## Response

- We will acknowledge receipt within 72 hours.
- Critical vulnerabilities (consensus bypass, key compromise, remote code execution) are prioritized for immediate fix.
- A public advisory will be published after the fix is released.

## Scope

| In scope | Out of scope |
|----------|-------------|
| Consensus rule bypass | Social engineering |
| Private key exposure | Attacks requiring physical access |
| Remote code execution | Third-party dependencies (report upstream) |
| P2P protocol exploits | Denial of service via network flooding |
| RPC authentication bypass | Issues in the explorer HTML (client-side only) |
| Wallet encryption weakness | |

## Contact

- **Security vulnerabilities:** Private contact form at sostcore.com/sost-contact.html
- **General bugs and feature requests:** https://github.com/Neob1844/sost-core/issues (public)
