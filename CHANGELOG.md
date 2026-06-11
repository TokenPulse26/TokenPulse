# Changelog

All notable changes to TokenPulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

---

## [0.4.2] - 2026-06-11 (Early Access)

### Fixed
- **Ollama native streaming token capture** — Ollama's `/api/chat` and `/api/generate` stream NDJSON (bare JSON per line), not SSE. The stream parser only consumed `data:`-framed lines, so streamed local-model requests recorded 0 tokens. NDJSON lines are now treated as complete events and the final chunk's `prompt_eval_count` / `eval_count` are captured. Found by live end-to-end testing during the v0.4.1 install verification.

---

## [0.4.1] - 2026-06-11 (Early Access)

### Added
- **xAI (Grok) provider route** — `http://localhost:4100/xai` forwards to `api.x.ai`; `xai-` bearer keys are also auto-detected on the root route and redacted in logs. Bundled pricing for grok-4 / grok-3 / grok-3-mini.
- CI workflow: every push and pull request now runs the Rust test suite, a compiler-warnings gate, dashboard/script compile checks, and pricing data validation.
- `SECURITY.md` — private vulnerability reporting and the project's data-handling posture.

### Fixed
- Dependency security pass (OSV scan of the full lockfile): updated tauri to 2.11.1 (origin-confusion advisory), openssl, rustls-webpki, tar, and rand to patched versions. All advisories with available fixes are cleared.

### Changed
- The orphaned secondary landing page in `docs/` now redirects to tokenpulse.to instead of carrying a divergent brand.
- README: xAI route documented, known-limitations section refreshed (time-range filter caveat removed after validation; estimated-price marker and codesigning status documented).

---

## [0.4.0] - 2026-06-11 (Early Access)

### Fixed
- **Cache token pricing** — cached tokens are now billed at provider-correct rates instead of being ignored. Anthropic cache reads are priced at 0.1× input and cache writes (`cache_creation_input_tokens`, previously not even extracted) at 1.25× input; OpenAI-style cached tokens are deducted from the full-rate input count and billed at the cache-read rate. Cache rates come from the LiteLLM pricing refresh when available, with provider heuristics as fallback. For agentic workloads (Claude Code, Codex) that run 80–90% cached tokens, this materially corrects the headline cost number in both directions.
- **Estimated prices are now flagged** — when a model is priced by fuzzy name match (e.g. an unknown `o1-pro` variant matching the `o1` entry) or by approximated cache rates, the request is marked `cost_estimated` in the database, shown with a `~` prefix in the dashboard, and exported in CSV. Fuzzy matching also now prefers the most specific (longest) model-name match.

### Added
- GitHub Actions release workflow that builds a macOS Apple Silicon proxy binary on every `v*.*.*` tag and publishes it as a GitHub Release asset (`tokenpulse-macos-arm64` + `.sha256`).
- `web-dashboard.py` and `agent_verify.py` ship as checksummed release assets, and `install.sh` installs them from the same release as the proxy binary — proxy and dashboard always arrive as a version-matched pair.
- `install.sh` downloads the pre-built binary from the latest GitHub Release and verifies its SHA256, removing the hard Rust toolchain dependency from the default install path.
- `install.sh --from-source` flag for the advanced build-from-source path.
- New per-request fields: `cache_creation_tokens` and `cost_estimated` (DB migration is automatic; CSV export includes both).
- MIT `LICENSE` file.
- Unit tests pinning known request costs for Anthropic (cache read/write), OpenAI (cached discount), fuzzy-match flagging, and LiteLLM cache-rate parsing.

### Changed
- Default `install.sh` path no longer compiles Rust on the tester's machine.
- README and GETTING_STARTED updated to reflect the pre-built binary install flow.
- Removed machine-specific local model entries from the bundled `pricing.json`.

### Notes
- Proxy binary is not codesigned for v1 early access; macOS may require an “Allow Anyway” step on first run.

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
