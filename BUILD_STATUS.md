# TokenPulse — Build Status

**Last updated:** 2026-03-23
**Current phase:** Phase 2 COMPLETE ✅

---

## What's Built (Phase 2 — DONE)

All code committed at: `f213fc9 Phase 2: provider routing, streaming, pricing auto-update, live dashboard`

### Phase 1 files (still in place):
- `src-tauri/src/db.rs` — SQLite layer + new: upsert_pricing, set_setting, get_price_for_model
- `src-tauri/src/proxy.rs` — Axum proxy; all providers routed; streaming SSE forwarding; DB-aware cost calc
- `src-tauri/src/pricing.rs` — Cost engine + parse_litellm_json + calculate_cost_with_db
- `src-tauri/src/lib.rs` — Tauri commands + spawn_pricing_update background task on startup
- `src-tauri/pricing.json` — Bundled fallback pricing
- `src/App.jsx` — Live dashboard with Recharts bar chart + model breakdown

### Phase 2 additions:
- **Mistral** (`/mistral/` → `https://api.mistral.ai`) and **Groq** (`/groq/` → `https://api.groq.com`) routing
- All 7 providers routed: OpenAI, Anthropic, Google, Ollama, LM Studio, Mistral, Groq
- Streaming SSE: chunks forwarded in real-time; usage extracted from final chunk; written to DB after stream completes
- Pricing auto-update: on launch, fetches LiteLLM JSON from GitHub, upserts into DB (skips is_custom=1 rows)
- React dashboard: Recharts 7-day daily spend bar chart, model breakdown panel (30 days), real-time polling every 2s

### Compile status: ✅ PASSES (`cargo check` clean)

---

## What's NOT Built Yet

### Phase 3 — Time Range Selectors + Polish
- [ ] Time range selectors (Today / 7 Days / 30 Days / Month) in dashboard
- [ ] Streaming indicator in request table (badge showing in-flight streams)

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

### ARCHITECTURE PIVOT: Web-First Dashboard (CRITICAL — Next Session)
- Key insight: Target users (OpenClaw, Mac Mini, Mac Studio, DGX Spark) run HEADLESS servers
- Desktop GUI (Tauri) is wrong primary interface for headless machines
- Web dashboard should be the PRIMARY interface, not optional
- Architecture: Rust proxy + SQLite + embedded web server (served on port 4200)
- Accessible from any device on the network — phone, laptop, desktop
- Tauri desktop app becomes optional/secondary for users who want native
- Current quick Python web dashboard at web-dashboard.py proves the concept
- Need to build a proper React-based web dashboard served by the Rust backend
- This simplifies the product AND better serves the actual audience

### OpenClaw Native Integration (v1.1 — HIGH PRIORITY)
- Auto-setup: OpenClaw plugin that configures proxy base URLs automatically
- OpenClaw already has all the user's API keys — TokenPulse can pull them and register without manual setup
- Makes OpenClaw users the natural first beta audience
- Setup flow becomes: install TokenPulse → tell OpenClaw to connect → done
- This is a major differentiator vs. competitors that require manual config

### Live Token Visualizer (v1.1)
- Real-time activity indicator in system tray (pulses when a request is in flight)
- "Live" panel in dashboard showing current active request, which model, token counter ticking up during streaming
- Token velocity graph (tokens/second) animated during inference
- Great demo moment — watch your AI "think" in real time
- Implementation: Tauri events or WebSocket from proxy to frontend (proxy emits events per-chunk during streaming)
- Would make an excellent Product Hunt demo GIF

### Web Dashboard / Mobile Access (v1.1)
- Serve a lightweight read-only web dashboard on localhost:4200 alongside the proxy
- Accessible from any device on the same network (phone, tablet) — open browser, see dashboard
- No account, no cloud — fully local
- Perfect for checking overnight cron job activity
- Great for OpenClaw users who want to see AI activity from another device

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
- Domain: **tokenpulse.to** (purchased 2026-03-23)
- Target: developers and AI power users running hybrid cloud+local model setups
- Gap: no existing tool tracks both cloud and local in one simple non-developer-friendly dashboard
- MVP spec: /Users/openclaw/.openclaw/workspace/research/api-tokenizer-mvp-plan.md
- Market research: /Users/openclaw/.openclaw/workspace/research/api-tokenizer-dashboard-market-research.md
