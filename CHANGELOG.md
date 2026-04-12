# Changelog

All notable changes to TokenPulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.3.0] - 2026-04-12 (Early Access)

### Added
- OpenRouter and OpenAI Codex proxy routes
- Responses API usage extraction for Codex/OpenAI streaming traffic
- Context Audit dashboard panel — heuristic analysis of prompt waste, model mismatches, and cache underuse
- Ollama token extraction for local model tracking
- First tester onboarding guide and verification flow docs
- Landing page for tokenpulse.to

### Fixed
- **Anthropic streaming token extraction** — refactored SSE parser to handle partial/multi-line events; 100% token capture rate on Anthropic traffic (was ~13%)
- SSE chunk boundary bug — events split across TCP chunks were silently dropped
- `stream_options` rejection on Codex Responses API — refactored gating from provider-name list to API shape detection
- `accept-encoding` header now stripped before forwarding to prevent compressed SSE breaking stream parsing
- Dashboard security: removed wildcard CORS, bound to localhost-only, eliminated LAN exposure
- `/api/health` route no longer falls through to forward proxy
- `/api/notifications` endpoint crash (undefined variable)

### Changed
- Dashboard UI overhaul: collapsible sections, tiered layout, ghost filtering, improved visual hierarchy
- All documentation tightened for launch readiness — route-specific onboarding, honest early-access framing
- Ollama documented as strongest verified local-model path; LM Studio described as implemented but lighter-confidence
- Dashboard binds to `127.0.0.1:4200` (was `::` / all interfaces)

---

## [0.2.0] - 2026-03-27 (Beta)

### Added
- Budget alerts with macOS push notifications
- Spending forecast and cost projections
- Error monitoring with per-model error rates and timeline
- Cost optimization recommendations engine
- Project/source auto-tagging (User-Agent detection + custom headers)
- Live activity feed with animated timeline
- GitHub-style usage heatmap (30 days × 24 hours)
- Auto-generated insights panel
- SVG area charts with hover tooltips
- Expandable request detail rows
- Sticky navigation on scroll
- Token flow animation

### Changed
- Web dashboard is now the primary interface (was React/Tauri)
- Tauri app converted to tray-only mode (proxy + notifications)
- Auto-refresh interval: 30 seconds (was 5 seconds)
- Activity feed shows last 5 minutes (was 60 seconds)

### Fixed
- XSS vulnerability in cost optimizer descriptions
- Bundled pricing now cached in memory (was re-parsed per request)
- SQLite WAL mode enabled for concurrent read performance
- CSV export includes all fields (cached tokens, reasoning tokens, source tag, etc.)
- SO_REUSEADDR prevents port conflicts on restart
- Streaming token extraction for Groq/Mistral (was only OpenAI/cliproxy)
- Google Gemini model name extraction from URL path
- Data retention actually enforced on startup

### Removed
- React/Tauri windowed dashboard (replaced by web dashboard)
- Non-functional proxy port setting in UI

---

## [0.1.0] - 2026-03-25 (Beta)

### Added
- Local HTTP proxy on port 4100 for transparent API call interception
- Support for 7 AI providers: OpenAI, Anthropic, Google, Mistral, Groq, Ollama, LM Studio
- Real-time token tracking (input/output) with cost calculation
- SQLite-based persistent request logging
- Auto-updating pricing from LiteLLM database (2,500+ models)
- Bundled fallback pricing for 50+ common models
- Web dashboard on port 4200 for local browser access
- Desktop dashboard (Tauri) with system tray integration
- Setup wizard with per-tool configuration guides
- Time range filtering (Today / 7 Days / 30 Days / All Time)
- Provider-type categorization (API / Subscription / Local)
- CSV data export
- Streaming SSE support with real-time chunk forwarding
- Dark mode UI with provider-colored charts
- macOS launchd integration for headless servers
- Data retention enforcement
