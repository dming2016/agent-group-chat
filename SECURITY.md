# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.x     | ✅        |

## Reporting a Vulnerability

Do **not** open a public issue. Email the maintainer directly.

This service is designed for **local development and single-machine multi-agent collaboration**. It has no authentication layer by design.

## Known Limitations

- **No authentication** — all API endpoints are open to any process on the machine. CORS is restricted to `localhost`.
- **File-based storage** — no encryption at rest.
- **No rate limiting** — a malicious local process could flood the SSE or message endpoints.

## What We Do

- XSS prevention: frontend uses `textContent` exclusively (no `innerHTML` for user data)
- Group ID validation: restricted to `[a-zA-Z0-9\-_.]`
- Message size limits: configurable truncation (default 5000 chars)
- Agent identity enforcement: server overrides `from_name`/`role` from `agents.json`, agents cannot impersonate

## Production Use

If you expose this to a network, add at minimum:
1. Reverse proxy with authentication (e.g. nginx + basic auth)
2. TLS termination
3. Rate limiting
