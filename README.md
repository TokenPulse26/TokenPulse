# TokenPulse

**Track every AI token you spend — across providers, models, and projects — on your own machine.**

TokenPulse is a local-first AI usage tracker built around two parts:
- a **Rust proxy** on port `4100` that sits between your tools and AI providers
- a **Python web dashboard** on port `4200` that shows usage, costs, errors, budgets, and trends

It records request metadata locally in SQLite so you can see what you're spending without hopping between provider dashboards.

---

## How It Works

```text
Your Tools → TokenPulse Proxy (route on :4100) → AI Providers
                    ↓
              SQLite Database
                    ↓
            Web Dashboard (:4200)
```

Point your tools at the correct TokenPulse route on `http://localhost:4100` instead of the provider directly. For example: root for OpenAI-compatible traffic, `/anthropic` for Anthropic-native clients, `/ollama` for Ollama, and `/lmstudio` for LM Studio. TokenPulse forwards requests, extracts usage metadata when providers expose it, calculates cost where pricing is available, and stores the results locally.

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
- LM Studio (implemented route, lighter verification confidence today)
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
- context audit heuristics for prompt waste / model misuse / cache underuse
- CSV export

---

## Current Product Shape

TokenPulse currently ships as:
- a **headless-friendly local proxy**
- a **browser-based dashboard**
- a **macOS Tauri app codebase** used for local packaging, updater plumbing, and tray/app-shell behavior

The browser dashboard is still the primary day-to-day interface.

The Tauri side should currently be described as **supporting app-shell/tray infrastructure, not a separate polished desktop dashboard experience**. Repo packaging/config still exists there, so avoid implying the Tauri layer is absent. The safer claim today is that the browser dashboard is primary, while the Tauri app remains secondary and less central to the product experience.

---

## Best-Supported Setup Today

Today, the most reliable TokenPulse path is:
- a technical early tester
- running locally
- starting from the repo or a source-based bootstrap install
- using the browser dashboard as the main interface

TokenPulse is **not yet a polished cross-platform one-click install product**. The current installer is a convenience bootstrapper for a narrow setup, not a finished general release flow.

## Quick Start

If you are comfortable running from source, this is the clearest current path.

**Start the proxy**

```bash
./tokenpulse
```

**Start the dashboard**

```bash
python3 web-dashboard.py
```

**Point one tool at the correct TokenPulse route**

```text
OpenAI-compatible: http://localhost:4100
Anthropic:         http://localhost:4100/anthropic
Ollama:            http://localhost:4100/ollama
LM Studio:         http://localhost:4100/lmstudio
```

If you want the cleanest first local-model test, start with **Ollama first** and treat LM Studio as a second-step route until it is re-verified successfully.

Then send one recognizable test request and open <http://127.0.0.1:4200>.

For the full recommended flow, install-path details, and a first-run verification check, see [GETTING_STARTED.md](GETTING_STARTED.md).

If you want the single clearest early-access path, start with [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md).

If you want the smallest honest proof-of-life check for v1, see [VERIFICATION_FLOW_V1.md](VERIFICATION_FLOW_V1.md).

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
- **Ollama:** `http://localhost:4100/ollama` , currently the strongest verified local-model path
- **LM Studio:** `http://localhost:4100/lmstudio` , route support exists, but this path should still be treated as a lighter-confidence route until it is re-verified successfully on a live upstream

If a tool supports a custom OpenAI-compatible base URL, TokenPulse can usually sit in front of it.

For current local-model tracking details, see the [Getting Started guide](GETTING_STARTED.md).

---

## Tech Stack

- **Proxy:** Rust + Axum
- **Dashboard:** Python standard library HTTP server
- **Database:** SQLite
- **App shell / tray layer:** Tauri 2.x (macOS-focused, secondary to the browser dashboard)
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
git clone https://github.com/TokenPulse26/TokenPulse.git
cd TokenPulse

# Build the Rust side currently used for the local proxy and Tauri app shell
cd src-tauri
cargo build --release
cd ..

# Run the dashboard
python3 web-dashboard.py
```

Depending on how you launch the built binary, the proxy will listen on port `4100`.

This source path is currently more honest and reliable than presenting TokenPulse like a fully packaged cross-platform installer product.

Note: the repo still contains active Tauri packaging/build config, including frontend build hooks. So while the browser dashboard is the main user experience today, docs should not imply the Tauri layer is gone, only that it is not yet the primary polished interface.

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
