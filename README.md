# TokenPulse

**Track every AI token you spend — across every model, in one place.**

TokenPulse is a lightweight local proxy that sits between your AI tools and the APIs they talk to. It captures every request, tracks token usage and costs in real time, and serves a live web dashboard — all without sending a single byte of your data anywhere.

![Dashboard](docs/dashboard-screenshot.png)

---

## How It Works

```
Your Tools → TokenPulse Proxy (:4100) → AI Providers
                    ↓
              SQLite Database
                    ↓
            Web Dashboard (:4200)
```

Point your AI tools at `localhost:4100` instead of the real API. TokenPulse forwards requests transparently, captures response metadata — token counts, model name, latency, cost — and records everything to a local SQLite database. Your API keys pass through without being stored or logged.

The **web dashboard** on port 4200 gives you full visibility from any browser on your network.

---

## Features

### Tracking & Analytics
- **Multi-provider support** — OpenAI, Anthropic, Google Gemini, Mistral, Groq, and any OpenAI-compatible endpoint
- **Local model support** — Ollama, LM Studio, and self-hosted models
- **Real-time cost calculation** — auto-updated pricing from the LiteLLM community database (2,500+ models)
- **Per-model breakdowns** — see exactly what each model costs you
- **Project/source auto-tagging** — automatic User-Agent detection + custom header support
- **Streaming support** — full SSE pass-through with real-time token extraction

### Dashboard
- **Live activity feed** — animated, auto-updating timeline of all requests
- **Spending forecasts** — projected costs based on your usage patterns
- **Budget alerts** — set overall or project/source-tag limits with macOS push notifications when thresholds are hit
- **Error monitoring** — per-model error rates, error timeline, and troubleshooting info
- **Cost optimization recommendations** — actionable suggestions to reduce spend
- **Activity heatmap** — GitHub-style 30-day × 24-hour usage visualization
- **Auto-generated insights** — trends, anomalies, and patterns surfaced automatically
- **SVG area charts** — interactive charts with hover tooltips
- **Expandable request details** — full token breakdown per request (cached, reasoning, etc.)
- **Time range filters** — Today, 7 Days, 30 Days, All Time
- **CSV data export** — download everything for your own analysis

### Deployment
- **Web dashboard** — accessible from any device on your network
- **Desktop tray app** (optional, macOS) — system tray icon with spend display, budget notifications, and "Open Dashboard" button
- **Headless mode** — run on any server with launchd (macOS) or systemd (Linux) auto-start
- **Data retention** — automatic cleanup of old data based on your preferences

---

## Quick Start

**1. Start the proxy**

```bash
./tokenpulse
```

**2. Start the dashboard**

```bash
python3 web-dashboard.py
```

**3. Configure your tools**

```bash
# OpenAI-compatible tools
export OPENAI_BASE_URL=http://localhost:4100

# Anthropic tools
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

**4. Open the dashboard**

Go to [http://localhost:4200](http://localhost:4200) in any browser.

→ **[Full setup guide →](GETTING_STARTED.md)**

---

## Supported Providers

### Cloud APIs
- **OpenAI** — GPT-4o, GPT-4o mini, o1, o3, and all OpenAI models
- **Anthropic** — Claude Opus, Sonnet, Haiku, and all Claude models
- **Google Gemini** — Gemini Pro, Flash, and all Gemini models
- **Mistral** — Mistral Large, Medium, Small, and all Mistral models
- **Groq** — Llama, Mixtral, and all Groq-hosted models

### Local Models
- **Ollama** — any model running locally (`localhost:4100/ollama`)
- **LM Studio** — any model loaded in LM Studio (`localhost:4100/lmstudio`)

### Any OpenAI-Compatible Endpoint
If it speaks the OpenAI API format, TokenPulse can proxy and track it.

---

## Tech Stack

- **Proxy server:** Axum (async Rust HTTP)
- **Web dashboard:** Python (single-file, zero dependencies beyond stdlib)
- **Database:** SQLite via rusqlite (bundled, zero setup)
- **Desktop tray app:** Tauri 2.x (Rust) — optional, macOS only
- **Pricing data:** LiteLLM community pricing database with bundled fallback for 50+ common models

---

## Privacy

**Runs entirely on your machine. No data sent to any server.**

The only network requests TokenPulse makes are:
1. Forwarding your AI API calls to the provider (same as without TokenPulse)
2. Fetching updated model pricing from the LiteLLM GitHub repository (read-only, public)
3. Checking for app updates (version number only)

Your data lives locally at: `~/Library/Application Support/com.tokenpulse.app/tokenpulse.db`

---

## Building from Source

Requirements: [Rust](https://rustup.rs) (stable), Python 3.8+

```bash
git clone https://github.com/tokenpulse/tokenpulse
cd tokenpulse

# Build the proxy
cargo build --release

# Run
./target/release/tokenpulse    # Proxy on :4100
python3 web-dashboard.py       # Dashboard on :4200
```

To build the optional desktop tray app (requires Node.js 18+):

```bash
npm install
npm run tauri build
```

---

## Contributing

Contributions are welcome! If you'd like to help improve TokenPulse:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

Please open an issue first to discuss any significant changes.

---

## License

[MIT](LICENSE)

---

**[Website](https://tokenpulse.to)** · **[Getting Started Guide](GETTING_STARTED.md)** · **[Changelog](CHANGELOG.md)** · **[Issues](https://github.com/tokenpulse/tokenpulse/issues)**
