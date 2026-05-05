# TokenPulse + OpenClaw Setup Guide

This guide shows how to route OpenClaw traffic through TokenPulse so usage is tracked in one local dashboard.

## What TokenPulse does for OpenClaw

When OpenClaw calls models through TokenPulse, TokenPulse can track:
- requests by provider and model
- token usage (when providers return usage fields)
- estimated API cost
- source/project tags for per-workflow attribution

TokenPulse stays local:
- Proxy: `http://127.0.0.1:4100`
- Dashboard: `http://127.0.0.1:4200`

## 1) Install TokenPulse

```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
```

## 2) Verify install

If present, run the built-in verifier:

```bash
~/.tokenpulse/agent_verify.py
```

If `agent_verify.py` is not present, use manual checks:

```bash
curl -s http://127.0.0.1:4100/health | python3 -m json.tool
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4200/
```

## 3) Configure OpenClaw provider base URLs

Use provider-specific TokenPulse routes:

- OpenAI-compatible base URL: `http://localhost:4100`
- Anthropic base URL: `http://localhost:4100/anthropic`
- Ollama base URL: `http://localhost:4100/ollama`
- LM Studio base URL: `http://localhost:4100/lmstudio`

Example config snippet:

```json
{
  "providers": {
    "openai": { "baseUrl": "http://localhost:4100" },
    "anthropic": { "baseUrl": "http://localhost:4100/anthropic" },
    "ollama": { "baseUrl": "http://localhost:4100/ollama" },
    "lmstudio": { "baseUrl": "http://localhost:4100/lmstudio" }
  }
}
```

## 4) Add source tags (recommended)

Add one of these headers in OpenClaw request paths when possible:
- `x-tokenpulse-project: openclaw-prod` (recommended for stable project grouping)
- `x-tokenpulse-tag: planner-agent` (recommended for per-agent/per-task grouping)

Suggested pattern:
- project header for the OpenClaw deployment/workspace
- tag header for each agent role (planner, coder, reviewer, etc.)

## 5) Confirm OpenClaw traffic appears in TokenPulse

1. Trigger one OpenClaw request through each configured provider route.
2. Open `http://127.0.0.1:4200`.
3. Confirm requests appear in:
   - Overview totals
   - Connections panel (provider row seen)
   - Recent Requests table
   - Sources detected list (if source tags are present)

Optional API check:

```bash
curl -s "http://localhost:4100/api/requests?limit=5" | python3 -m json.tool
```

## OpenClaw troubleshooting

### Traffic bypassing TokenPulse
- Symptom: OpenClaw requests succeed but do not appear in dashboard.
- Fix: Ensure OpenClaw provider `baseUrl` points to TokenPulse `localhost:4100` routes, not provider direct endpoints.

### Wrong provider route
- Symptom: request errors or unexpected provider parsing.
- Fix: Use route-specific base URLs:
  - Anthropic -> `/anthropic`
  - Ollama -> `/ollama`
  - LM Studio -> `/lmstudio`

### Ollama not running
- Symptom: Ollama route fails.
- Fix: start Ollama service first (for example `ollama serve`) and retry.

### Token counts missing
- Symptom: requests appear but token fields are zero/empty.
- Fix: some request types/providers do not always return usage fields; compare across providers and verify model route.

### Dashboard empty
- Symptom: dashboard loads but no requests appear.
- Fix: run `~/.tokenpulse/agent_verify.py`, verify proxy health, then send a known test request through TokenPulse.
