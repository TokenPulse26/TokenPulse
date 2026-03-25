# TokenPulse

**Track every AI token you spend — across every model, in one place.**

TokenPulse is a lightweight local proxy that sits between your AI tools and the APIs they talk to. It captures every request, tracks token usage and costs in real time, and serves a live dashboard — all without sending a single byte of your data anywhere.

![Dashboard](docs/dashboard-screenshot.png)

---

## Features

- **Multi-provider tracking** — OpenAI, Anthropic, Google Gemini, Mistral, Groq, and more
- **Local model support** — Ollama, LM Studio, and any OpenAI-compatible endpoint
- **Real-time cost calculation** — auto-updated pricing from the LiteLLM community database (2,500+ models)
- **Per-model breakdowns** — see exactly what each model costs you
- **Daily spend charts** — stacked by provider with dark mode UI and provider-colored charts
- **Time range filters** — Today, 7 Days, 30 Days, All Time
- **Streaming support** — full SSE pass-through with real-time chunk forwarding
- **Web dashboard** — accessible from any device on your network at port 4200
- **Desktop app** — native macOS app with system tray integration
- **Setup wizard** — guided per-tool configuration right in the app
- **CSV data export** — export all requests for your own analysis
- **Headless mode** — run on a Mac Mini, Mac Studio, or any server with launchd auto-start
- **Data retention** — automatic cleanup of old data based on your preferences

---

## How It Works

TokenPulse runs a local HTTP proxy on port `4100`. Point your AI tools at this proxy instead of the real API endpoint. The proxy forwards requests normally and captures the response metadata — token counts, model name, latency, and cost — recording everything to a local SQLite database.

```
Your AI tool  →  localhost:4100  →  OpenAI / Anthropic / Google / etc.
                      ↓
                 SQLite DB  →  Dashboard (localhost:4200)
```

Your API keys pass through transparently. They are never stored or logged.

---

## Quick Start

**1. Install**

Download the latest `.dmg` from the [Releases page](https://github.com/tokenpulse/tokenpulse/releases), mount it, and drag TokenPulse to your Applications folder. On first launch, right-click → Open (since the app isn't signed yet).

**2. Configure**

Point your AI tools at the TokenPulse proxy. For most tools, just change the base URL:

```bash
# OpenAI-compatible tools
export OPENAI_BASE_URL=http://localhost:4100

# Anthropic tools (Claude Code, etc.)
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

**3. Monitor**

Open the dashboard at [http://localhost:4200](http://localhost:4200) (or use the desktop app window). Watch your token usage and costs update in real time.

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
- **Ollama** — any model running locally via Ollama
- **LM Studio** — any model loaded in LM Studio

### Any OpenAI-Compatible Endpoint
If it speaks the OpenAI API format, TokenPulse can proxy and track it.

---

## Tech Stack

- **Desktop shell:** Tauri 2.x (Rust + React)
- **Frontend:** React 19, Recharts
- **Proxy server:** Axum (async Rust HTTP)
- **Database:** SQLite via rusqlite (bundled, zero setup)
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

Requirements: [Rust](https://rustup.rs) (stable), [Node.js](https://nodejs.org) 18+

```bash
git clone https://github.com/tokenpulse/tokenpulse
cd tokenpulse
npm install
npm run tauri build
```

The built app will be in `src-tauri/target/release/bundle/`.

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
