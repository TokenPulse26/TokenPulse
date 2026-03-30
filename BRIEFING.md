# TokenPulse — Contributor Briefing

> Internal contributor context for people working on the repo.
> This is not the primary end-user document; use `README.md` and `GETTING_STARTED.md` for public-facing setup guidance.

*Last updated: 2026-03-30*

---

## What TokenPulse Is

TokenPulse is a **local-first AI usage tracker** built from:
- a Rust proxy on port `4100`
- a Python web dashboard on port `4200`
- an optional Tauri/macOS tray app layer for notifications and quick access

Core job: sit between AI tools and providers, log request metadata locally, and make spend / usage visible in one place.

```text
Your Tools → TokenPulse Proxy (:4100) → AI Providers
                    ↓
              SQLite Database
                    ↓
            Web Dashboard (:4200)
```

The browser dashboard is the main product interface today.

---

## Repo Snapshot

- **Repo:** `git@github.com:TokenPulse26/TokenPulse.git`
- **Website:** <https://tokenpulse.to>
- **Product state:** beta / active iteration
- **Runtime truth note:** feature work in the source tree is ahead of some packaging metadata (`src-tauri/Cargo.toml`, `tauri.conf.json`, `update.json` still show `0.1.0` while the proxy health endpoint reports `0.2.0`)

If docs and packaging/version files disagree, trust the implementation first and confirm against the current code paths.

---

## Architecture

### Main components
- `src-tauri/src/proxy.rs` — Axum proxy, provider routing, request logging, health/stats/budget APIs
- `src-tauri/src/db.rs` — SQLite schema, request storage, pricing, budgets, notifications, forecasts
- `src-tauri/src/lib.rs` — Tauri tray app shell, pricing refresh, update check, notification wiring
- `src-tauri/src/pricing.rs` — pricing lookup and bundled fallback parsing
- `web-dashboard.py` — single-file Python dashboard and companion HTTP endpoints
- `install.sh` — bootstrap installer for current macOS Apple Silicon workflow

### Product shape
- **Primary UI:** web dashboard
- **Optional support UI:** macOS tray app
- **Persistence:** SQLite
- **Pricing source:** LiteLLM pricing data plus bundled fallback data

---

## Supported Routes / Providers

- OpenAI-compatible: `/v1/...`
- Anthropic: `/anthropic/...`
- Google Gemini: `/google/...`
- Mistral: `/mistral/...`
- Groq: `/groq/...`
- Ollama: `/ollama/...`
- LM Studio: `/lmstudio/...`
- CLIProxy: `/cliproxy/...`

Provider handling is not perfectly uniform because upstream APIs expose usage in different formats.

---

## What the Current Build Already Does

### Usage tracking
- logs request metadata to SQLite
- captures input/output tokens and extra token fields where available
- calculates cost using stored or bundled pricing data
- tags source/project data from User-Agent or custom header metadata
- tracks request timing and errors

### Dashboard
- summary cards and trend views
- live activity feed
- per-model / per-provider breakdowns
- project/source sections
- 30-day heatmap
- budget management UI
- budget alert history
- spending forecasts
- reliability / error views
- optimizer suggestions
- CSV export

### Tray app / native layer
- opens dashboard in browser
- shows spend in tray/menu bar
- runs periodic budget checks
- triggers macOS notifications for budget events

---

## Useful Endpoints

Served by the proxy/dashboard stack today:
- `GET /health`
- `GET /api/stats?range=7d`
- `GET /api/requests?limit=50&range=7d`
- `GET /api/budgets`
- `GET /api/budget-alerts`
- `GET /api/budget-forecasts`
- `GET /export/csv?range=7d`

---

## Data Model Highlights

Primary tables:
- `requests`
- `pricing`
- `settings`
- `budgets`
- `budget_alerts`
- `notifications`

Important `requests` fields include:
- `timestamp`
- `provider`
- `model`
- `input_tokens`
- `output_tokens`
- `cached_tokens`
- `reasoning_tokens`
- `cost_usd`
- `latency_ms`
- `time_to_first_token_ms`
- `source_tag`
- `error_message`
- `provider_type`

Current default local DB path in the app/dashboard code:

```text
~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db
```

---

## Known Rough Edges

- packaging/update metadata still references `0.1.0`
- repo presentation has been improved, but some internal project-history files remain in the root
- installer is still a convenience bootstrap script, not a polished cross-platform release installer
- automated test coverage exists in parts of the Rust code, but overall project testing is still light compared with product surface area

---

## Internal Files Worth Knowing About

- `BUILD_STATUS.md` — internal build snapshot / progress context
- `REPAIR_PLAN.md` — internal maintenance notes
- `REPAIR_REPORT.md` — internal maintenance notes

These are intentionally retained for project history, but they are not the documents to link new users to.

---

## Recommended Reading Order

For end users:
1. `README.md`
2. `GETTING_STARTED.md`
3. `CHANGELOG.md`

For contributors:
1. this file
2. `README.md`
3. `src-tauri/src/proxy.rs`
4. `src-tauri/src/db.rs`
5. `web-dashboard.py`

---

## Practical Truths for Anyone Touching This Repo

- The product is fundamentally **local-first**, not SaaS-first.
- The **web dashboard** is the main user experience.
- The **tray app is supportive infrastructure**, not the core UI.
- If you see a mismatch between docs, packaging metadata, and code behavior, verify against the implementation before making claims.
