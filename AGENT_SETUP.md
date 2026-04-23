# TokenPulse — Agent Setup Guide

**If you are an AI agent installing TokenPulse for a user, follow this file.**

TokenPulse is a local-first AI usage tracking proxy + dashboard. This guide walks you through a complete install in under 3 minutes on macOS Apple Silicon.

---

## What gets installed

| Component | Purpose | Port |
|---|---|---|
| **Proxy** (Rust binary) | Sits between AI tools and providers, logs every request to SQLite | 4100 |
| **Dashboard** (Python script) | Web UI showing spend, activity, errors, trends | 4200 |

Both run as launchd services (auto-start on boot, auto-restart on crash).
All data stays local. API keys pass through and are never stored.

---

## Prerequisites

**Required:**
- macOS with Apple Silicon (M1/M2/M3/M4)
- Internet connection (to download the binary)
- `curl` (pre-installed on macOS)

**Recommended:**
- Python 3 (for the dashboard — pre-installed on macOS 12.3+, or via `brew install python3`)

**Not required:**
- Rust, Cargo, or any build tools (the installer downloads a pre-built binary)
- Node.js, npm, or any JavaScript runtime
- Docker or containers

---

## Step 1: Install

Run this single command:

```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
```

**What this does:**
1. Verifies macOS Apple Silicon
2. Downloads the pre-built proxy binary from GitHub Releases
3. Verifies SHA256 checksum
4. Downloads the dashboard script and docs
5. Installs launchd services for both proxy and dashboard
6. Starts both services
7. Health-checks both endpoints
8. Prints success with URLs and next steps

**Expected output on success:**
```
✅ Proxy binary installed: /Users/<you>/.tokenpulse/tokenpulse
✅ Python 3 found: /opt/homebrew/bin/python3 (Python 3.x.x)
✅ proxy healthy at http://127.0.0.1:4100/health
✅ dashboard healthy at http://127.0.0.1:4200/
🟢 TokenPulse is running
```

**If the install fails:** Check the error output. Common issues:
- Port 4100 or 4200 already in use → stop the conflicting process
- No network → check internet connectivity
- Python 3 missing → proxy installs fine, dashboard won't start. Install Python 3 and re-run.

**macOS security note:** The binary is not codesigned. On first run, macOS may block it. Go to System Settings → Privacy & Security → scroll down → click "Allow Anyway" for tokenpulse. Then re-run the installer or restart the launchd service.

### Installer flags

| Flag | Effect |
|---|---|
| `--from-source` | Skip pre-built binary, build from source (requires Rust) |
| `--no-autostart` | Install files but don't create launchd services |

Pass flags via: `curl -fsSL ... | bash -s -- --no-autostart`

---

## Step 2: Verify the install

```bash
curl -s http://127.0.0.1:4100/health | python3 -m json.tool
```

**Expected response:**
```json
{
    "status": "ok",
    "service": "tokenpulse-proxy",
    "port": 4100,
    "version": "0.3.1",
    "dashboard_url": "http://127.0.0.1:4200",
    "proxy_paused": false,
    "total_requests_tracked": 0,
    "uptime_seconds": 5
}
```

**Success criteria:**
- `"status": "ok"` — proxy is running
- `"total_requests_tracked"` — starts at 0 for fresh install
- Dashboard loads at `http://127.0.0.1:4200` (verify with `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4200/` — expect `200`)

If either check fails, inspect logs:
```bash
tail -20 ~/.tokenpulse/logs/proxy.error.log
tail -20 ~/.tokenpulse/logs/dashboard.error.log
```

---

## Step 3: Route one AI tool through TokenPulse

Change the base URL of the user's AI tool to point at TokenPulse instead of the provider directly.

### Route table

| Provider Type | TokenPulse Route |
|---|---|
| OpenAI / OpenAI-compatible | `http://localhost:4100` |
| Anthropic | `http://localhost:4100/anthropic` |
| Google Gemini | `http://localhost:4100/google` |
| Ollama (local) | `http://localhost:4100/ollama` |
| LM Studio (local) | `http://localhost:4100/lmstudio` |
| Mistral | `http://localhost:4100/mistral` |
| Groq | `http://localhost:4100/groq` |
| OpenRouter | `http://localhost:4100/openrouter` |

**Critical:** Each provider type MUST use its specific route. Anthropic requests to the root route will fail. Ollama requests to the root route will fail.

### Common tool configurations

**Environment variables (most tools):**
```bash
export OPENAI_BASE_URL=http://localhost:4100
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
export OLLAMA_HOST=http://localhost:4100/ollama
```

**OpenClaw** — edit the provider config:
```json
{
  "providers": {
    "openai": { "baseUrl": "http://localhost:4100" },
    "anthropic": { "baseUrl": "http://localhost:4100/anthropic" }
  }
}
```

**Cursor** — Settings → Models → OpenAI Base URL → `http://localhost:4100`

**Claude Code CLI:**
```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

---

## Step 4: Send a test request and confirm tracking

**OpenAI-compatible test:**
```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

**Anthropic test:**
```bash
curl http://localhost:4100/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":5,"messages":[{"role":"user","content":"ping"}]}'
```

**Ollama test (requires Ollama running on 11434):**
```bash
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"ping"}],"stream":false}'
```

**Verify it was tracked:**
```bash
curl -s "http://localhost:4100/api/requests?limit=1" | python3 -m json.tool
```

**Expected:** The request appears with provider, model, timestamp, and token counts (when available).

Or tell the user to open `http://127.0.0.1:4200` in a browser — the request should be visible in the activity feed.

---

## Step 5: Done

TokenPulse is installed, running, and tracking. The user can:
- View their dashboard at `http://127.0.0.1:4200`
- Route additional tools through port 4100
- Check proxy health anytime: `curl http://127.0.0.1:4100/health`

Services auto-start on boot via launchd. No further maintenance needed.

---

## Uninstall

One command removes everything:

```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --yes
```

To keep the usage database before removing:
```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --keep-data
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Install fails: "port 4100 in use" | Another process on that port | `lsof -i :4100` → kill it → re-run install |
| Install fails: "port 4200 in use" | Another process on that port | `lsof -i :4200` → kill it → re-run install |
| macOS blocks the binary | Unsigned binary | System Settings → Privacy & Security → Allow Anyway |
| Dashboard shows no data | No requests routed yet | Send a test request per Step 4 |
| Requests succeed but don't appear | Tool bypassing TokenPulse | Verify tool's base URL points to `localhost:4100`, not the provider |
| Anthropic requests fail | Wrong route | Must use `/anthropic` route, not root |
| Ollama requests fail | Ollama not running | Start Ollama first: `ollama serve` |
| Token counts show 0 | Normal for some request types | Embeddings and health checks don't report tokens |
| `/health` returns error | Proxy not running | `launchctl list | grep tokenpulse` to check; re-run install to fix |

---

## Architecture notes (for agents)

- The proxy is a standalone Rust binary. No runtime dependencies.
- The dashboard is a single Python file using only the standard library. No pip packages needed.
- Data lives in SQLite at `~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db`
- The proxy and dashboard share the SQLite file but are independent processes.
- API keys pass through in headers and are **never stored** — only metadata (model, tokens, cost, timestamps) is logged.
- The dashboard auto-refreshes every 30 seconds.
- Install directory: `~/.tokenpulse/`
- Logs: `~/.tokenpulse/logs/`
- launchd labels: `com.tokenpulse.proxy`, `com.tokenpulse.dashboard`

---

## Feedback

Report bugs and onboarding friction: [github.com/TokenPulse26/TokenPulse/issues](https://github.com/TokenPulse26/TokenPulse/issues)
