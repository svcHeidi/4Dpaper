# Security Policy

## Supported versions

Security fixes are applied to the latest tagged release and the `main` branch.
Older releases may not receive fixes.

## Deployment scope

4Dpapers v0.1 is a single-user, single-workspace application intended for local
use or a private host. It is not a multi-tenant service. Do not expose the
dashboard directly to the public internet. Follow the
[Docker deployment guide](docs/docker-deployment.md), use HTTPS, set a strong
`FOURD_API_KEY`, and keep the workspace and signing keys private.

Opening a workspace lets the application read and render its files. Only open
workspaces and datasets you trust, and back them up before rendering or
upgrading. The public GitHub Pages demo is static and does not expose the
dashboard APIs.

AI features are optional. Prompts and selected paper context are sent to the
configured provider; consult that provider's data policy before using private,
embargoed, or regulated research data. Ollama can be used for a local model.

## Reporting a vulnerability

Please report vulnerabilities privately with a
[GitHub security advisory](https://github.com/4dpapers/4dpapers/security/advisories/new).
Include the affected version, deployment configuration, reproduction steps,
and impact. Do not include real credentials, private datasets, or unpublished
papers.

Please do not open a public issue for an unpatched vulnerability. You can
expect an acknowledgement within seven days, but this community project does
not currently offer a security SLA.
