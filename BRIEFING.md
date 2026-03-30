# TokenPulse — Project Briefing for New Contributors

*Last updated: 2026-03-29 by Shaka*

---

## What Is TokenPulse?

A local proxy + web dashboard that tracks AI token usage and costs across cloud APIs and local models. One dashboard instead of checking each provider separately.

**The problem it solves:** People using AI APIs have no unified way to see what they're spending, where, and whether it's worth it. You'd have to check OpenAI's dashboard, Anthropic's dashboard, etc. separately. And local models (Ollama, LM Studio) have zero cost tracking.

**How it works:**
```
Your Tools → TokenPulse Proxy (:4100) → AI Providers (OpenAI, Anthropic, etc.)
                    ↓
              SQLite Database
                    ↓
            Web Dashboard (:4200)
```

You point your AI tools at `http://localhost:4100` instead of directly at the API. TokenPulse intercepts, logs everything (tokens, cost, latency, model, provider), forwards the request, and shows it all on a web dashboard.

---

## GitHub

**Repo:** https://github.com/TokenPulse26/TokenPulse
**Version:** v0.2.0 Beta (19 commits)
**License:** MIT

---

## Architecture

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| Proxy | `src-tauri/src/proxy.rs` | 656 | Axum HTTP proxy, routes to 7 providers, extracts tokens, detects source |
| Database | `src-tauri/src/db.rs` | 620 | SQLite schema, CRUD for requests/budgets/pricing/settings |
| Tauri App | `src-tauri/src/lib.rs` | 559 | Tray-only app: proxy + macOS notifications + budget alerts |
| Pricing | `src-tauri/src/pricing.rs` | 110 | LiteLLM pricing engine, 2,100+ models, bundled 58-model fallback |
| Dashboard | `web-dashboard.py` | 3,131 | Single-file Python web dashboard, no external dependencies |
| Install | `install.sh` | ~80 | One-line install script |

**Tech stack:** Rust (Axum) proxy, Python (stdlib only) dashboard, SQLite database, Tauri for tray icon/notifications.

**No React.** We killed the React/Tauri frontend. The Python web dashboard is the sole product interface.

---

## Supported Providers (7)

| Provider | Route | Token Format |
|----------|-------|-------------|
| OpenAI | `/v1/...` | `usage.prompt_tokens` / `completion_tokens` |
| Anthropic | `/anthropic/...` | `usage.input_tokens` / `output_tokens` |
| Google Gemini | `/google/...` | `usageMetadata.promptTokenCount` |
| Mistral | `/mistral/...` | OpenAI-compat |
| Groq | `/groq/...` | OpenAI-compat |
| Ollama | `/ollama/...` | `prompt_eval_count` / `eval_count` |
| LM Studio | `/lmstudio/...` | OpenAI-compat |
| CLIProxy | `/cliproxy/...` | OpenAI-compat (subscription) |

---

## Current Features

### Free Tier (the hook)
- Proxy intercepts and logs all requests
- Web dashboard with time range filtering (Today/7d/30d/All)
- Per-model and per-provider breakdowns
- Live activity feed with animated timeline
- GitHub-style usage heatmap (30 days × 24 hours)
- SVG area charts with hover tooltips
- Auto-generated insights panel
- Token flow animation
- CSV data export (from dashboard and API)
- Auto-refresh every 30 seconds
- Responsive layout (desktop + mobile)

### Paid Tier Features (built, pricing not enforced yet)
- **Budget alerts** — set daily/weekly/monthly thresholds, get macOS push notifications when exceeded
- **Spending forecasts** — "At this rate, you'll spend $X this month"
- **Error monitoring** — error rate by model, error timeline, wasted cost on failed requests
- **Cost optimizer** — model downgrade suggestions, waste detection, provider efficiency comparison
- **Project auto-tagging** — detects source from User-Agent (Cursor, OpenClaw, Python SDK, etc.) or custom `X-TokenPulse-Project` header

### API Endpoints
- `GET /health` — version, uptime, status
- `GET /api/stats?range=7d` — usage summary with model + project breakdowns
- `GET /api/requests?limit=50&range=7d` — recent requests as JSON
- `GET /api/budgets` — budget status
- `GET /export/csv?range=7d` — CSV download (on dashboard port 4200)

---

## Database Schema

**Tables:** `requests`, `pricing`, `settings`, `budgets`, `budget_alerts`

**Key columns in `requests`:**
timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type

**`provider_type`:** `api` (costs money), `subscription` (included in plan), `local` (free)

---

## Key Decisions Made

| Decision | Reasoning |
|----------|-----------|
| Python dashboard over React | Target users run headless servers. Single-file Python is easier to deploy than a React build pipeline |
| Local proxy over cloud proxy | Privacy differentiator. "Your data never leaves your machine." |
| Freemium model ($9/mo) | Free tier is the hook (tracking). Paid = budget alerts + forecasts + optimizer |
| Tauri is tray-only | Desktop window killed. Tauri provides: proxy process, tray icon, macOS notifications |
| SQLite over Postgres | Single-file, zero config, perfect for local-first product |

---

## What's Working (verified)

- ✅ All 7 providers route correctly
- ✅ Streaming SSE with token extraction for all formats
- ✅ Ollama local model tracking (tested with qwen3.5:4b)
- ✅ Budget alerts with macOS push notifications
- ✅ Spending forecasts with projections
- ✅ Error monitoring
- ✅ Project auto-tagging
- ✅ CSV export
- ✅ JSON API endpoints
- ✅ Health check endpoint
- ✅ IPv6 dual-stack dashboard (DualStackHTTPServer)
- ✅ WAL mode SQLite for concurrent access
- ✅ XSS vulnerabilities patched
- ✅ Pricing cached in memory (not re-parsed per request)

---

## Known Issues / Technical Debt

- Zero automated tests (no unit, integration, or E2E tests)
- Single Mutex on SQLite connection (bottleneck under high concurrency)
- Dashboard uses page reload for auto-refresh (loses scroll position)
- `update.json` points to nonexistent GitHub URL for auto-updates
- No way to edit budgets after creation (must delete + recreate)
- Install script requires Rust toolchain (no pre-built binaries yet)
- `REPAIR_PLAN.md` and `REPAIR_REPORT.md` are internal dev notes still in repo

---

## Audit Reports

Full code audits saved at:
- `/Users/openclaw/.openclaw/workspace/research/tokenpulse-full-audit.md` (v1, 2026-03-25)
- `/Users/openclaw/.openclaw/workspace/research/tokenpulse-audit-v2.md` (v2, 2026-03-26)

---

## Running Locally (Ryan's Mac Mini)

- **Proxy:** port 4100 (launchd service `com.tokenpulse.proxy`)
- **Dashboard:** port 4200 (launchd service `com.tokenpulse.dashboard`)
- **Database:** `~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db`
- **OpenClaw routes through TokenPulse:** cliproxy baseUrl = `http://127.0.0.1:4100/cliproxy/v1`

---

## Business Context

- **Owner:** Ryan (PurpleTiger) via New Age Investments LLC
- **Domain:** tokenpulse.to (purchased 2026-03-23)
- **Target:** $30K/year revenue would be a success
- **Pricing plan:** Free (unlimited tracking) → Pro $9/mo (alerts + forecasts + optimizer) → Team $15/seat
- **Competitive window:** 6-12 months before Helicone, Portkey, etc. fill this niche
- **Current users:** 1 (Ryan). Zero external users yet.

---

## What's Next

1. Get real users to try it (share in AI communities)
2. Collect feedback on what's useful vs. what's noise
3. If engagement: build paid tier enforcement, pre-built binaries, Docker image
4. If no engagement: analyze why and decide whether to pivot or shelve

---

*This briefing was written by Shaka for any agent or contributor joining the project.*
