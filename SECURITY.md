# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's
[private vulnerability reporting](https://github.com/TokenPulse26/TokenPulse/security/advisories/new)
rather than opening a public issue. You should receive a response within a few
days. Please include reproduction steps and the TokenPulse version
(`cat ~/.tokenpulse/VERSION` or the dashboard footer).

## What TokenPulse does with your data

- The proxy and dashboard bind to `127.0.0.1` only — nothing is exposed to
  your network.
- Request/response **bodies are not stored**; only usage metadata (tokens,
  model, provider, cost, latency) is written to a local SQLite database.
- API keys are forwarded to the upstream provider you addressed and are
  **redacted** before anything is logged or stored.
- Release binaries are built by GitHub Actions from the tagged source and
  published with SHA256 checksums that `install.sh` verifies before
  installing.

## Dependency posture

Dependencies are scanned against the OSV database. Advisories with available
fixes are patched promptly. Some `unmaintained`-class advisories remain on
transitive Linux-only GTK bindings pinned by the Tauri framework; they are not
compiled into the shipped macOS binary and clear automatically when the Tauri
stack updates.
