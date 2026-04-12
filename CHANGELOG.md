# Changelog

All notable changes to TokenPulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Changed
- Corrected the top-level `README.md` quick start so the dashboard URL matches the current localhost-only bind on `127.0.0.1:4200`
- Cleaned up public-facing documentation to match the current local-first proxy + web dashboard product shape
- Corrected repository references, database path references, and contributor-vs-user documentation framing
- Noted that some packaging/release metadata still trails the latest feature work
- Tightened local-model support wording in onboarding docs so Ollama is presented as the strongest verified path and LM Studio is described as implemented but still less verified
- Clarified route-specific onboarding in `GETTING_STARTED.md` so first testers connect one tool through the correct OpenAI-compatible, Anthropic, Ollama, or LM Studio path before expanding scope
- Aligned `README.md` quick start with that same route-specific first-test framing, including LM Studio in the visible first-success path
- Tightened the tokenpulse.to landing page "How it works" step so website onboarding no longer implies every client should only use bare `localhost:4100`
- Removed a duplicated LM Studio subsection in `GETTING_STARTED.md` so local-model onboarding now has one clear LM Studio posture and one separate example verification request
- Corrected `BUILD_STATUS.md` so it no longer claims onboarding and verification docs are unbuilt when those repo docs now exist but are still being tightened
- Added the missing LM Studio route to `FIRST_TESTER_ONBOARDING.md` so all top-level first-run docs now show the same visible route set for early tester setup
- Corrected `GETTING_STARTED.md` so dashboard access docs match the current code, which binds the web UI to `127.0.0.1:4200` by default instead of exposing LAN access out of the box
- Corrected the older `0.1.0` changelog wording so it no longer claims the dashboard was accessible from any device, which conflicts with the current local-only dashboard posture documented elsewhere in the repo
- Added the missing LM Studio route to `VERIFICATION_FLOW_V1.md` so the minimal verification doc matches the route set already shown in onboarding and quick-start docs
- Corrected the visible `GETTING_STARTED.md` quick start and verification example URL so it now includes LM Studio and points to the current localhost-only dashboard address on `127.0.0.1:4200`
- Corrected `VERIFICATION_FLOW_V1.md` so the verification prerequisites and dashboard check now point to the current localhost-only dashboard address on `127.0.0.1:4200`
- Corrected `FIRST_TESTER_ONBOARDING.md` so the dashboard open/refresh steps now point to the current localhost-only dashboard address on `127.0.0.1:4200`
- Tightened the top-level `README.md` architecture/onboarding wording so it now teaches route-aware proxy setup instead of reinforcing a bare `localhost:4100` mental model for every provider
- Tightened `BRIEFING.md` endpoint examples so internal contributor docs now explicitly distinguish proxy health on `127.0.0.1:4100` from dashboard APIs on `127.0.0.1:4200`, reducing the chance of reintroducing stale dashboard-check assumptions
- Corrected the remaining stale dashboard health-check and local-only access examples in `GETTING_STARTED.md` so they now point to `127.0.0.1:4200`, matching the current default bind described elsewhere in the repo

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
