# TokenPulse — Agent Setup Guide

This guide is optimized for AI agents (Claude, GPT, Codex, local models) setting up TokenPulse on behalf of a user. Every step includes exact commands with no ambiguity.

## What This Sets Up

TokenPulse has two components:
1. **Proxy** (Rust binary) — listens on `http://localhost:4100`, intercepts AI API requests, logs usage to SQLite
2. **Dashboard** (Python script) — serves a web UI on `http://127.0.0.1:4200`, reads from the same SQLite database

Both must be running for TokenPulse to work.

---

## Prerequisites

Check that required tools are installed before proceeding:

```bash
# Check Rust toolchain
rustc --version    # Requires Rust stable (1.70+)
cargo --version

# Check Python
python3 --version  # Requires Python 3.8+

# Check git
git --version
```

**If Rust is missing**, install it:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

**If Python 3 is missing**, install it via your system package manager (`brew install python3` on macOS, `apt install python3` on Debian/Ubuntu).

---

## Step 1: Clone and Build

```bash
# Clone the repository
git clone https://github.com/TokenPulse26/TokenPulse.git
cd TokenPulse

# Build the Rust proxy (this takes 1-3 minutes on first build)
cd src-tauri
cargo build --release

# Verify the binary was built
ls -la target/release/tokenpulse
# Expected: a ~19MB executable file

# Return to repo root
cd ..
```

After this step, you should have:
- The proxy binary at `TokenPulse/src-tauri/target/release/tokenpulse`
- The dashboard script at `TokenPulse/web-dashboard.py`

---

## Step 2: Start the Proxy

```bash
# From the repo root (TokenPulse/)
./src-tauri/target/release/tokenpulse &

# Verify it's running
sleep 2
curl -s http://localhost:4100/health
```

Expected response:
```json
{"status":"ok","service":"tokenpulse-proxy","port":4100,"total_requests_tracked":0}
```

If port 4100 is already in use:
```bash
lsof -i :4100
# Kill the conflicting process, then retry
```

---

## Step 3: Start the Dashboard

```bash
# From the repo root (TokenPulse/)
python3 web-dashboard.py &

# Verify it's running
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4200/
```

Expected response: `200`

If port 4200 is already in use:
```bash
lsof -i :4200
```

---

## Step 4: Connect AI Tools

Change the base URL of whichever AI tool/provider the user wants to track. **Use the correct route for each provider type:**

| Provider Type | TokenPulse Route | Environment Variable |
|---|---|---|
| OpenAI / OpenAI-compatible | `http://localhost:4100` | `OPENAI_BASE_URL=http://localhost:4100` |
| Anthropic | `http://localhost:4100/anthropic` | `ANTHROPIC_BASE_URL=http://localhost:4100/anthropic` |
| Google Gemini | `http://localhost:4100/google` | Set base URL in client config |
| Ollama | `http://localhost:4100/ollama` | `OLLAMA_HOST=http://localhost:4100/ollama` |
| LM Studio | `http://localhost:4100/lmstudio` | Set base URL in client config |
| Mistral | `http://localhost:4100/mistral` | Set base URL in client config |
| Groq | `http://localhost:4100/groq` | Set base URL in client config |
| OpenRouter | `http://localhost:4100/openrouter` | Set base URL in client config |

**Important:** Do not send Anthropic-format requests to the root route. Anthropic clients must use `/anthropic`. Do not send Ollama requests to the root route. Ollama clients must use `/ollama`.

### Common tool configurations

**OpenClaw** — edit `openclaw.json` or equivalent config:
```json
{
  "providers": {
    "openai": { "baseUrl": "http://localhost:4100" },
    "anthropic": { "baseUrl": "http://localhost:4100/anthropic" }
  }
}
```

**Cursor** — Settings → Models → OpenAI Base URL → `http://localhost:4100`

**Claude Code CLI** — set environment variable:
```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

**Any OpenAI-compatible tool** — set the base URL to `http://localhost:4100`

---

## Step 5: Verify It Works

Send a test request through TokenPulse and confirm it appears in the dashboard.

**OpenAI-compatible test** (requires a valid OpenAI API key):
```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

**Anthropic test** (requires a valid Anthropic API key):
```bash
curl http://localhost:4100/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":5,"messages":[{"role":"user","content":"ping"}]}'
```

**Ollama test** (requires Ollama running locally on port 11434):
```bash
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"ping"}],"stream":false}'
```

**Check the dashboard for the request:**
```bash
# Check via API that the request was logged
curl -s http://localhost:4100/api/requests?limit=1 | python3 -m json.tool
```

Or tell the user to open `http://127.0.0.1:4200` in a browser.

---

## Step 6 (Optional): Run as Background Services

### macOS (launchd)

Replace `TOKENPULSE_DIR` with the actual absolute path to the cloned repo:

```bash
TOKENPULSE_DIR="$(pwd)"  # Run this from the TokenPulse repo root

# Create proxy service
cat > ~/Library/LaunchAgents/com.tokenpulse.proxy.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tokenpulse.proxy</string>
    <key>ProgramArguments</key>
    <array><string>${TOKENPULSE_DIR}/src-tauri/target/release/tokenpulse</string></array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/tokenpulse.log</string>
    <key>StandardErrorPath</key><string>/tmp/tokenpulse-error.log</string>
</dict>
</plist>
EOF

# Create dashboard service
cat > ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tokenpulse.dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${TOKENPULSE_DIR}/web-dashboard.py</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/tokenpulse-dashboard.log</string>
    <key>StandardErrorPath</key><string>/tmp/tokenpulse-dashboard-error.log</string>
</dict>
</plist>
EOF

# Load services
launchctl load ~/Library/LaunchAgents/com.tokenpulse.proxy.plist
launchctl load ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist

# Verify
launchctl list | grep tokenpulse
```

### Linux (systemd)

```bash
TOKENPULSE_DIR="$(pwd)"  # Run this from the TokenPulse repo root

sudo tee /etc/systemd/system/tokenpulse-proxy.service << EOF
[Unit]
Description=TokenPulse Proxy
After=network.target
[Service]
Type=simple
ExecStart=${TOKENPULSE_DIR}/src-tauri/target/release/tokenpulse
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/tokenpulse-dashboard.service << EOF
[Unit]
Description=TokenPulse Web Dashboard
After=network.target tokenpulse-proxy.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 ${TOKENPULSE_DIR}/web-dashboard.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now tokenpulse-proxy tokenpulse-dashboard

# Verify
systemctl status tokenpulse-proxy tokenpulse-dashboard
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `cargo build` fails | Rust not installed or outdated | `rustup update stable` |
| Port 4100 in use | Another process on that port | `lsof -i :4100` then kill it |
| Port 4200 in use | Another process on that port | `lsof -i :4200` then kill it |
| Dashboard returns empty | No requests routed through proxy yet | Send a test request per Step 5 |
| Request succeeds but not in dashboard | Tool bypassing TokenPulse | Verify the tool's base URL points to `localhost:4100` |
| Anthropic requests fail | Using wrong route | Must use `/anthropic` route, not root |
| Ollama requests fail | Ollama not running on 11434 | Start Ollama first: `ollama serve` |
| Token counts show 0 | Normal for some request types | Embeddings and some streaming patterns may not report tokens |

---

## Architecture Notes for Agents

- The proxy binary is a standalone Rust executable. It does not need Cargo or Rust at runtime — only for building.
- The dashboard is a single Python file with zero external dependencies (standard library only).
- Data is stored in SQLite at `~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db` (macOS) or equivalent.
- The proxy and dashboard are independent processes that share the SQLite database file.
- The proxy forwards all requests transparently — API keys pass through in headers and are never stored.
- Both processes must be running simultaneously for the full experience.
- The dashboard auto-refreshes every 30 seconds.

---

## Quick Reference

| Component | Port | URL | Start Command |
|---|---|---|---|
| Proxy | 4100 | `http://localhost:4100` | `./src-tauri/target/release/tokenpulse` |
| Dashboard | 4200 | `http://127.0.0.1:4200` | `python3 web-dashboard.py` |
| Health check | — | `http://localhost:4100/health` | `curl http://localhost:4100/health` |
