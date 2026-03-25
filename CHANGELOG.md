# Changelog

All notable changes to TokenPulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.1.0] - 2026-03-25 (Beta)

### Added

- Local HTTP proxy on port 4100 for transparent API call interception
- Support for 7 AI providers: OpenAI, Anthropic, Google, Mistral, Groq, Ollama, LM Studio
- Real-time token tracking (input/output) with cost calculation
- SQLite-based persistent request logging
- Auto-updating pricing from LiteLLM database (2,500+ models)
- Bundled fallback pricing for 50+ common models
- Web dashboard on port 4200 accessible from any device
- Desktop dashboard (Tauri) with system tray integration
- Setup wizard with per-tool configuration guides
- Time range filtering (Today / 7 Days / 30 Days / All Time)
- Provider-type categorization (API / Subscription / Local)
- CSV data export
- Streaming SSE support with real-time chunk forwarding
- Dark mode UI with provider-colored charts
- macOS launchd integration for headless servers
- Data retention enforcement
