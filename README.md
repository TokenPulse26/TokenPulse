# TokenPulse

**Track every AI token you spend — across providers, models, and projects — on your own machine.**

TokenPulse is a local-first AI usage tracker built around two parts:
- a **Rust proxy** on port `4100` that sits between your tools and AI providers
- a **Python web dashboard** on port `4200` that shows usage, costs, errors, budgets, and trends

It records request metadata locally in SQLite so you can see what you're spending without hopping between provider dashboards.

---

## How It Works

```text
Your Tools → TokenPulse Proxy (:4100) → AI Providers
                    ↓
              SQLite Database
                    ↓
            Web Dashboard (:4200)
```

Point your tools at `http://localhost:4100` instead of the provider directly. TokenPulse forwards requests, extracts usage metadata when providers expose it, calculates cost where pricing is available, and stores the results locally.

Your API keys pass through to the upstream provider. TokenPulse is designed to track usage locally, not to relay data to a hosted TokenPulse service.

---

## What TokenPulse Tracks

### Providers and endpoints
- OpenAI-compatible APIs
- Anthropic
- Google Gemini
- Mistral
- Groq
- Ollama
- LM Studio
- CLIProxy / subscription-style OpenAI-compatible traffic

### Usage data
- input and output tokens
- cached and reasoning token fields when available
- estimated request cost
- latency and time-to-first-token metrics
- model and provider
- streaming vs non-streaming requests
- source / project tagging
- request errors

### Dashboard views
- live activity feed
- usage and cost summaries by provider and model
- project/source breakdowns
- 30-day activity heatmap
- budget status and budget alert history
- spending forecasts
- reliability and error monitoring
- cost optimization suggestions
- CSV export

---

## Current Product Shape

TokenPulse currently ships as:
- a **headless-friendly local proxy**
- a **browser-based dashboard**
- an **optional macOS tray app** that opens the dashboard and surfaces notifications

The browser dashboard is the primary interface. The Tauri app is not a separate desktop dashboard anymore.

---

## Quick Start

**Start the proxy**

```bash
./tokenpulse
```

**Start the dashboard**

```bash
python3 web-dashboard.py
```

**Point your tools at TokenPulse**

```bash
export OPENAI_BASE_URL=http://localhost:4100
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

Then open <http://localhost:4200>.

For full setup steps, service configuration, and tool-specific examples, see [GETTING_STARTED.md](GETTING_STARTED.md).

---

## Supported Routes

### Cloud APIs
- **OpenAI-compatible:** `http://localhost:4100`
- **Anthropic:** `http://localhost:4100/anthropic`
- **Google Gemini:** `http://localhost:4100/google`
- **Mistral:** `http://localhost:4100/mistral`
- **Groq:** `http://localhost:4100/groq`
- **CLIProxy:** `http://localhost:4100/cliproxy`

### Local models
- **Ollama:** `http://localhost:4100/ollama`
- **LM Studio:** `http://localhost:4100/lmstudio`

If a tool supports a custom OpenAI-compatible base URL, TokenPulse can usually sit in front of it.

---

## Tech Stack

- **Proxy:** Rust + Axum
- **Dashboard:** Python standard library HTTP server
- **Database:** SQLite
- **Tray app:** Tauri 2.x (optional, macOS-focused)
- **Pricing:** LiteLLM pricing data with a bundled fallback set for common models

---

## Privacy

**Runs locally. Your request history stays on your machine.**

TokenPulse may make network requests for:
1. forwarding your AI requests to the upstream provider
2. refreshing public model pricing data
3. checking the app update manifest

The default local database path used by the current app/dashboard build is:

```text
~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db
```

---

## Building from Source

Requirements:
- Rust (stable)
- Python 3.8+

```bash
git clone git@github.com:TokenPulse26/TokenPulse.git
cd TokenPulse

# Build the proxy / tray app codebase
cd src-tauri
cargo build --release
cd ..

# Run the dashboard
python3 web-dashboard.py
```

Depending on how you launch the Rust binary, the proxy will listen on port `4100`.

To build the optional Tauri app, install Node.js first, then run the usual Tauri build flow from `src-tauri` / project root as configured in the repo.

---

## Repo Notes

- [BRIEFING.md](BRIEFING.md) is a contributor-facing project brief, not end-user documentation.
- `REPAIR_PLAN.md` and `REPAIR_REPORT.md` are internal maintenance notes kept in the repo for project history.

---

## Contributing

Contributions are welcome. If you're planning a significant change, open an issue first so the implementation direction is clear before work starts.

---

**Website:** <https://tokenpulse.to>  
**Getting Started:** [GETTING_STARTED.md](GETTING_STARTED.md)  
**Changelog:** [CHANGELOG.md](CHANGELOG.md)  
**Repository:** <https://github.com/TokenPulse26/TokenPulse>
