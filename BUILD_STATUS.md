# TokenPulse — Build Status

**Last updated:** 2026-04-12
**Current architecture:** Rust proxy (port 4100) + Python web dashboard (port 4200)
**Services:** Both run as launchd services (com.tokenpulse.proxy, com.tokenpulse.dashboard)

---

## What's Built and Working

### Core Proxy (Rust — src-tauri/)
- Axum-based HTTP proxy on port 4100, binds to 127.0.0.1
- Provider routing: OpenAI, Anthropic, Google, Ollama, LM Studio, Mistral, Groq, CLIProxy, OpenRouter, OpenAI-Codex
- Local-model posture: Ollama is the strongest verified local-model path today, while LM Studio route support exists but remains more lightly verified
- Streaming SSE handling with per-provider usage extraction (Anthropic, OpenAI, Responses API)
- Non-streaming request capture with full token/cost tracking
- SQLite local database for all request records
- Internal API endpoints: /api/stats, /api/requests, /api/reliability, /api/notifications, /api/budgets, /api/budget-forecasts, /api/context-audit
- CORS restricted to localhost origins
- Pricing auto-update from LiteLLM on startup
- Source tag detection (Cursor, VSCode, OpenClaw, Python SDK, Node SDK)

### Web Dashboard (Python — web-dashboard.py)
- Full analytics dashboard served on port 4200
- Threaded HTTP server (ThreadingHTTPServer)
- Sections: Overview, Activity, Models, Providers, Reliability, Budgets, Context Audit, Cost Optimizer
- Time range filtering (Today, 7 Days, 30 Days, All)
- Budget management (create, edit, delete budgets with alerts)
- CSV export for request history
- Dark theme, responsive layout

### Infrastructure
- Both services managed by launchd (auto-start on boot)
- Database: ~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db
- Domain: tokenpulse.to (purchased 2026-03-23)

---

## Known Issues Being Fixed

- /api/health route falls through to forward proxy
- Stale pricing data for some newer model families
- Some dashboard sections don't honor time range filter consistently
- LM Studio support posture still needs stronger end-to-end verification than Ollama before it should be described as equally proven

---

## Not Built Yet (Deferred)

- One-command install script beyond the current narrow bootstrap path
- Provider registry (configurable providers)
- Public GitHub release

## Built, but still being tightened

- Landing page for tokenpulse.to exists, but positioning/onboarding copy is still being refined
- Verification guidance exists in `VERIFICATION_FLOW_V1.md`, but a more polished in-product verification experience is still deferred
- Getting started and first-tester onboarding docs now exist (`GETTING_STARTED.md`, `FIRST_TESTER_ONBOARDING.md`), but they are still being tightened for launch-readiness
- Local-model docs now consistently frame Ollama as the stronger verified path and LM Studio as supported but lighter-confidence until more direct verification is logged

---

## How to Run

### Both services (already configured as launchd):
Services auto-start. Check status:
```bash
launchctl list | grep tokenpulse
```

### Manual (if needed):
```bash
# Proxy
cd /Users/openclaw/.openclaw/workspace/projects/tokenpulse
./src-tauri/target/release/tokenpulse

# Dashboard
python3 web-dashboard.py
```

### Compile proxy:
```bash
cd src-tauri && source $HOME/.cargo/env && cargo build --release
```

---

## Key Design Decisions

- **Proxy port:** 4100
- **Dashboard port:** 4200
- **Architecture:** Rust proxy handles all traffic forwarding + data capture. Python dashboard is read-only analytics UI that queries the same SQLite DB.
- **Local DB path:** ~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db
- **Pricing source:** LiteLLM model_prices_and_context_window.json (auto-fetched on startup)
