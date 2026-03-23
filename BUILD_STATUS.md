# TokenPulse — Build Status

**Last updated:** 2026-03-23 14:40 ET  
**Current phase:** Phase 1 COMPLETE ✅  

---

## What's Built (Phase 1 — DONE)

All code committed at: `c672378 Phase 1: proxy server, SQLite database, pricing engine, and basic React dashboard`

### Files created:
- `src-tauri/src/db.rs` — SQLite database layer (init, insert_request, get_recent_requests, get_daily_stats, get_model_breakdown)
- `src-tauri/src/proxy.rs` — Axum HTTP proxy server on port 4100, provider detection, request forwarding, usage extraction for all providers
- `src-tauri/src/pricing.rs` — Cost calculation engine, LiteLLM JSON loader
- `src-tauri/src/lib.rs` — Tauri commands (get_recent_requests, get_daily_stats, get_model_breakdown, get_proxy_status)
- `src-tauri/pricing.json` — Bundled pricing data (gpt-4o, gpt-4o-mini, claude-sonnet-4-6, claude-haiku-3-5, gemini-1.5-pro, gemini-1.5-flash)
- `src/App.jsx` — Dark-mode React dashboard with stat cards and live request table

### Compile status: ✅ PASSES (`cargo check` clean, 1 harmless unused-fn warning)

---

## What's NOT Built Yet

### Phase 2 — Provider Coverage (next)
- [ ] Anthropic routing and response parsing (separate from OpenAI format)
- [ ] Google routing and response parsing
- [ ] Ollama/LM Studio direct detection
- [ ] Streaming response handling (SSE buffering + real-time forwarding)
- [ ] Pull fresh LiteLLM pricing JSON from GitHub on launch

### Phase 3 — Full Dashboard
- [ ] Replace mock data with real SQLite queries in frontend
- [ ] Live-polling for recent requests table (2-second interval)
- [ ] Daily spend bar chart (Recharts)
- [ ] Model breakdown chart (Recharts)
- [ ] Time range selectors (Today / 7 Days / 30 Days / Month)

### Phase 4 — Setup UX
- [ ] Welcome/onboarding screen
- [ ] Setup screen with tool selector (Cursor, Python SDK, shell, etc.)
- [ ] Copy-to-clipboard env variable buttons
- [ ] Test proxy button
- [ ] Empty state design

### Phase 5 — System Tray + Polish
- [ ] System tray integration (Tauri plugin)
- [ ] Launch at login
- [ ] Settings screen (port config, pricing overrides, data retention)
- [ ] CSV export

### Phase 6 — Release Prep
- [ ] Auto-update (Tauri updater + GitHub Releases)
- [ ] macOS code signing
- [ ] Windows and Linux build testing
- [ ] Performance profiling

---

## How to Resume Building

### To run the app:
```bash
cd /Users/openclaw/.openclaw/workspace/projects/tokenpulse
source "$HOME/.cargo/env"
npm run tauri dev
```

### To compile-check only (faster):
```bash
cd /Users/openclaw/.openclaw/workspace/projects/tokenpulse/src-tauri
source "$HOME/.cargo/env"
cargo check
```

### Next Claude Code prompt: Phase 2 (Provider Coverage + Streaming)

Hand this to Claude Code:

```
Continue building TokenPulse. Phase 1 (proxy server, SQLite, pricing, React dashboard) is complete and compiling.

PROJECT: /Users/openclaw/.openclaw/workspace/projects/tokenpulse
BUILD STATUS: /Users/openclaw/.openclaw/workspace/projects/tokenpulse/BUILD_STATUS.md
FULL MVP SPEC: /Users/openclaw/.openclaw/workspace/research/api-tokenizer-mvp-plan.md

PHASE 2 TASKS:

1. Improve provider detection and routing in src-tauri/src/proxy.rs:
   - Ensure Anthropic requests (Authorization: Bearer sk-ant-*) route to https://api.anthropic.com and responses parse usage.input_tokens / usage.output_tokens
   - Ensure Google requests (Authorization: Bearer AIza*) route to https://generativelanguage.googleapis.com and parse usageMetadata.promptTokenCount / usageMetadata.candidatesTokenCount  
   - Ensure Ollama (localhost:11434) and LM Studio (localhost:1234) are handled via OpenAI-compat format (prompt_tokens/completion_tokens)
   - Mistral (api.mistral.ai) and Groq (api.groq.com) routing

2. Implement proper streaming (SSE) handling:
   - For streaming requests, forward SSE chunks to the client in real time as they arrive
   - For OpenAI streaming, inject stream_options: {"include_usage": true} into the request body so the final chunk includes usage data
   - Buffer chunks to find the final [DONE] chunk and extract usage from it
   - Write to SQLite only after stream is complete (mark is_complete=1, is_streaming=1)
   - If stream interrupted before final chunk, write partial record with is_complete=0

3. Add pricing auto-update on app launch:
   - On startup, spawn a background task that fetches https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
   - Parse it and upsert into the pricing table (skip rows where is_custom=1)
   - Non-blocking — don't delay app startup
   - Store last_updated timestamp in settings table

4. Wire the React dashboard to real SQLite data:
   - Replace any mock/static data in App.jsx with real Tauri invoke() calls
   - get_recent_requests(50) for the table, polled every 2 seconds
   - get_daily_stats(7) for the summary stats
   - Show "No requests yet" empty state if table is empty

After all changes: run `source $HOME/.cargo/env && cargo check` in src-tauri/ and fix any errors. Then commit: "Phase 2: provider coverage, streaming, pricing auto-update, live dashboard data"

When completely finished: openclaw system event --text "TokenPulse Phase 2 complete: provider routing, streaming, pricing auto-update, live dashboard" --mode now
```

---

## Future Feature Ideas (Post-Launch)

### Image & Video Generation Tracking (v1.2+ idea)
- Ryan suggested tracking image/video generation APIs alongside LLM token tracking
- Examples: Replicate, fal.ai, RunwayML, Seedance 2.0 (video), Stable Diffusion APIs, Imagen
- Pricing model is different — per image, per second of video, or per compute unit (not tokens)
- Schema would need a `cost_unit` field (tokens / images / seconds / compute_units)
- Proxy architecture handles this the same way — intercept request, parse response, calculate cost
- Good v1.2 feature once core LLM tracking is solid

---

## Key Design Decisions (reference)

- **Proxy port:** 4100 (configurable later)
- **Local DB path:** `~/Library/Application Support/com.tokenpulse.app/tokenpulse.db` (macOS)
- **Pricing source:** LiteLLM `model_prices_and_context_window.json` on GitHub
- **Streaming:** OpenAI requires `stream_options: {include_usage: true}` injected
- **Free tier limit:** 2 cloud providers (implement in Phase 5 with freemium gate)
- **Tech stack:** Tauri 2.x + Axum + rusqlite (bundled) + React + Recharts

---

## Revenue Model (reference)

- Free: unlimited local models, 1 cloud provider, 30 days history
- Pro: $9/month or $79/year — unlimited everything + budget alerts + CSV export
- Launch lifetime deal: $89

## Business Context

- Product name: **TokenPulse**
- Target: developers and AI power users running hybrid cloud+local model setups
- Gap: no existing tool tracks both cloud and local in one simple non-developer-friendly dashboard
- MVP spec: /Users/openclaw/.openclaw/workspace/research/api-tokenizer-mvp-plan.md
- Market research: /Users/openclaw/.openclaw/workspace/research/api-tokenizer-dashboard-market-research.md
