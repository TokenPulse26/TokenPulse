# TokenPulse

**TokenPulse — the accounting layer for AI. Know where every token goes.**

TokenPulse is a local-first proxy and dashboard that helps you see AI usage across providers, models, and projects on your own machine.

For v1, this is a **free early access** release for technical testers on **macOS Apple Silicon**.

---

## Who this is for

TokenPulse is for technical users on macOS Apple Silicon who want local-first visibility into AI spend across cloud and local providers.

It is a fit if you want to:
- route AI traffic through one local proxy
- see usage and estimated cost in one dashboard
- compare cloud and local model activity in one place
- keep request history on your own machine

If you are looking for a polished cross-platform SaaS product, this is not that release.

---

## v1 support status

**Supported for v1:**
- macOS Apple Silicon

**Coming soon:**
- Linux, Windows, and NVIDIA-based setups, join the feedback channel to be notified

TokenPulse currently ships as:
- a Rust proxy on port `4100`
- a Python browser dashboard on port `4200`
- a secondary macOS Tauri app-shell / tray layer

The browser dashboard is the primary interface today.

---

## How it works

```text
Your Tools → TokenPulse Proxy (route on :4100) → AI Providers
                    ↓
              SQLite Database
                    ↓
            Web Dashboard (:4200)
```

Point your tools at the correct TokenPulse route on `http://localhost:4100` instead of the provider directly. For example: root for OpenAI-compatible traffic, `/anthropic` for Anthropic-native clients, `/ollama` for Ollama, and `/lmstudio` for LM Studio.

TokenPulse forwards requests, extracts usage metadata when providers expose it, calculates cost where pricing is available, and stores the results locally.

---

## Install

### Recommended v1 path

The one supported install path for v1 is:
- **macOS Apple Silicon via `install.sh`**

```bash
./install.sh
```

Then follow the full setup and verification flow in [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md).

### Advanced / manual paths

These paths still exist, but treat them as advanced/manual:
- run from source
- set up background services manually with `launchd`

If you only want the clearest early-access path, use `install.sh` first.

---

## First verification path

The fastest proof-of-life flow is:
1. install with `install.sh`
2. start the proxy and dashboard
3. point one tool at one TokenPulse route
4. send one recognizable test request
5. confirm it appears in the dashboard at `http://127.0.0.1:4200`

Use [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md) as the source of truth.

---

## Supported routes

### Cloud APIs
- **OpenAI-compatible:** `http://localhost:4100`
- **Anthropic:** `http://localhost:4100/anthropic`
- **Google Gemini:** `http://localhost:4100/google`
- **Mistral:** `http://localhost:4100/mistral`
- **Groq:** `http://localhost:4100/groq`
- **CLIProxy:** `http://localhost:4100/cliproxy`

### Local models
- **Ollama:** `http://localhost:4100/ollama` , recommended local-model path for v1
- **LM Studio:** `http://localhost:4100/lmstudio` , supported but lower confidence than Ollama today

If a tool supports a custom OpenAI-compatible base URL, TokenPulse can usually sit in front of it.

---

## What TokenPulse tracks

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
- context audit heuristics
- CSV export

---

## Known limitations

Current early-access limitations:
- macOS Apple Silicon is the only supported v1 platform
- Ollama is the recommended local-model path today
- LM Studio is supported, but lower confidence than Ollama
- pricing data can be stale for some newer model families
- some dashboard time-range filters may not fully apply
- the Tauri app-shell is secondary, the browser dashboard is the main surface
- the installer is still a narrow bootstrap path, not a polished general release installer

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

## Build from source (advanced/manual)

Requirements:
- Rust (stable)
- Python 3.8+

```bash
git clone https://github.com/TokenPulse26/TokenPulse.git
cd TokenPulse
cd src-tauri
cargo build --release
cd ..
python3 web-dashboard.py
```

Depending on how you launch the built binary, the proxy will listen on port `4100`.

This path is valid, but for first testers the supported v1 path is still `install.sh` on macOS Apple Silicon.

---

## Feedback

Report bugs and onboarding friction here:
- [github.com/TokenPulse26/TokenPulse/issues](https://github.com/TokenPulse26/TokenPulse/issues)

---

**Website:** <https://tokenpulse.to>  
**First Tester Onboarding:** [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md)  
**Getting Started:** [GETTING_STARTED.md](GETTING_STARTED.md)  
**Agent Setup Guide:** [AGENT_SETUP.md](AGENT_SETUP.md)  
**Repository:** <https://github.com/TokenPulse26/TokenPulse>
