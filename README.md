# TokenPulse

**Track every AI token you spend — across every model, in one place.**

TokenPulse is a lightweight desktop app that tracks your AI usage and costs across cloud APIs and local models. It runs a local proxy that captures token counts, calculates costs in real time, and displays everything in a live dashboard — without sending your data anywhere.

---

## Features

- **Multi-provider tracking** — OpenAI, Anthropic, Google, Mistral, Groq, and more
- **Local model support** — Ollama, LM Studio, vLLM, llama.cpp
- **Real-time cost calculation** — auto-updated pricing from the LiteLLM community database
- **Per-model breakdowns** — see exactly what each model costs you
- **Daily spend charts** — stacked by provider, filterable by time range
- **Time range filters** — Today, 7 days, 30 days, All time
- **CSV data export** — export all requests for your own analysis
- **System tray** — live spend tracking without keeping the window open
- **Launch on login** — always running, never in the way
- **Dark mode dashboard** — easy on the eyes

---

## How It Works

TokenPulse runs a local HTTP proxy on port `4100`. You point your AI tools at this proxy instead of the real API endpoint. The proxy forwards your requests normally, but captures the response metadata (token counts, model name, latency) and records it to a local SQLite database. Your API keys pass through transparently and are never stored or logged.

```
Your tool  →  localhost:4100  →  api.openai.com (or any provider)
                    ↓
              SQLite DB  →  Dashboard
```

---

## Quick Start

> **Download:** Coming soon — check the [Releases](https://github.com/tokenpulse/tokenpulse/releases) page.

1. Download and open `TokenPulse.dmg`
2. Drag TokenPulse to your Applications folder
3. Launch TokenPulse — it will appear in your menu bar
4. Open the dashboard and click **Setup** to configure your tools

---

## Configuring Your Tools

Point each tool at the TokenPulse proxy instead of the provider directly:

| Provider | Original endpoint | TokenPulse proxy |
|---|---|---|
| OpenAI | `https://api.openai.com` | `http://localhost:4100/openai` |
| Anthropic | `https://api.anthropic.com` | `http://localhost:4100/anthropic` |
| Google Gemini | `https://generativelanguage.googleapis.com` | `http://localhost:4100/google` |
| Mistral | `https://api.mistral.ai` | `http://localhost:4100/mistral` |
| Groq | `https://api.groq.com` | `http://localhost:4100/groq` |
| Ollama | `http://localhost:11434` | `http://localhost:4100/ollama` |
| LM Studio | `http://localhost:1234` | `http://localhost:4100/lmstudio` |

Most tools that support a custom base URL work with TokenPulse out of the box.

### Example: Claude Code

```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
claude
```

### Example: OpenAI Python SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:4100/openai", api_key="your-key")
```

### Example: curl

```bash
curl http://localhost:4100/openai/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

---

## Screenshots

> Coming soon.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop shell | Tauri 2.x (Rust + React) |
| Frontend | React 19, Recharts |
| Database | SQLite (via rusqlite, bundled) |
| Proxy server | Axum (async Rust HTTP) |
| Pricing data | LiteLLM community pricing database |

---

## Privacy

TokenPulse runs entirely on your machine. No usage data, API keys, or request content is ever sent to any external server. The only network requests TokenPulse makes are:

1. Forwarding your AI API calls to the provider (same as before)
2. Fetching updated pricing data from the LiteLLM GitHub repository (read-only, no auth)
3. Checking for app updates from this repository (version number only)

Your data lives at: `~/Library/Application Support/com.tokenpulse.app/tokenpulse.db`

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

## License

MIT
