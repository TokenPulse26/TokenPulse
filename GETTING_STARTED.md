# Getting Started with TokenPulse

This guide walks you through installing TokenPulse, configuring your AI tools to use it, and accessing the web dashboard.

---

## What TokenPulse Does

TokenPulse sits between your AI tools and the APIs they talk to. It runs a local proxy on port **4100** that intercepts every request, logs token usage and costs to a local SQLite database, and serves a live web dashboard on port **4200**. Your API keys pass through transparently — nothing is stored or sent anywhere.

```
Your AI Tools → TokenPulse Proxy (:4100) → AI Providers
                       ↓
                 SQLite Database
                       ↓
               Web Dashboard (:4200)
```

---

## Quick Start

Three steps to get running:

1. **Start the proxy:**
   ```bash
   ./tokenpulse
   ```

2. **Start the dashboard:**
   ```bash
   python3 web-dashboard.py
   ```

3. **Point your tools at** `http://localhost:4100`

That's it. Open `http://localhost:4200` in any browser to see your usage.

---

## Installation Options

### Option A: Standalone (Recommended for Servers)

Best for Mac Minis, Mac Studios, Linux servers, or any always-on machine.

**1. Download**

Download the `tokenpulse` proxy binary and `web-dashboard.py` from the [GitHub Releases page](https://github.com/tokenpulse/tokenpulse/releases).

```bash
sudo cp tokenpulse /usr/local/bin/tokenpulse
sudo chmod +x /usr/local/bin/tokenpulse
cp web-dashboard.py /usr/local/bin/web-dashboard.py
```

**2. Verify both work**

```bash
# Terminal 1: Start the proxy
tokenpulse

# Terminal 2: Start the dashboard
python3 /usr/local/bin/web-dashboard.py
```

You should see the proxy running on port 4100 and the dashboard on port 4200.

**3. Set up as services (auto-start on boot)**

<details>
<summary><strong>macOS (launchd)</strong></summary>

**Proxy service** — save as `~/Library/LaunchAgents/com.tokenpulse.proxy.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tokenpulse.proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/tokenpulse</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/tokenpulse.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/tokenpulse-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TOKENPULSE_HOST</key>
        <string>0.0.0.0</string>
    </dict>
</dict>
</plist>
```

**Dashboard service** — save as `~/Library/LaunchAgents/com.tokenpulse.dashboard.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tokenpulse.dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/usr/local/bin/web-dashboard.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/tokenpulse-dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/tokenpulse-dashboard-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TOKENPULSE_HOST</key>
        <string>0.0.0.0</string>
    </dict>
</dict>
</plist>
```

Load both services:

```bash
launchctl load ~/Library/LaunchAgents/com.tokenpulse.proxy.plist
launchctl load ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist
```

Verify:

```bash
launchctl list | grep tokenpulse
curl http://localhost:4200
```

Manage services:

```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.tokenpulse.proxy.plist
launchctl unload ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist

# Restart (unload then load)
launchctl unload ~/Library/LaunchAgents/com.tokenpulse.proxy.plist && \
launchctl load ~/Library/LaunchAgents/com.tokenpulse.proxy.plist

# Check logs
tail -f /tmp/tokenpulse.log
tail -f /tmp/tokenpulse-dashboard.log
```

</details>

<details>
<summary><strong>Linux (systemd)</strong></summary>

**Proxy service** — save as `/etc/systemd/system/tokenpulse-proxy.service`:

```ini
[Unit]
Description=TokenPulse Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/tokenpulse
Restart=always
RestartSec=5
Environment=TOKENPULSE_HOST=0.0.0.0

[Install]
WantedBy=multi-user.target
```

**Dashboard service** — save as `/etc/systemd/system/tokenpulse-dashboard.service`:

```ini
[Unit]
Description=TokenPulse Web Dashboard
After=network.target tokenpulse-proxy.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/web-dashboard.py
Restart=always
RestartSec=5
Environment=TOKENPULSE_HOST=0.0.0.0

[Install]
WantedBy=multi-user.target
```

Enable and start both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tokenpulse-proxy
sudo systemctl enable --now tokenpulse-dashboard
```

Check status:

```bash
sudo systemctl status tokenpulse-proxy
sudo systemctl status tokenpulse-dashboard
journalctl -u tokenpulse-proxy -f
```

</details>

**4. Access from another device**

Open a browser on any device on the same network:

```
http://<server-ip>:4200
```

Find your server's IP with:

```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I
```

> **Note:** Setting `TOKENPULSE_HOST` to `0.0.0.0` (as shown in the service configs above) allows access from other devices on your network. Omit it or set to `127.0.0.1` for local-only access.

---

### Option B: Desktop App (macOS)

The desktop app provides a **system tray icon** with quick status, budget notifications, and a button to open the dashboard in your browser. The proxy runs automatically when the tray app is active.

> **Note:** The dashboard itself is the web dashboard at `:4200` — the tray app opens it in your default browser. You still need to run `web-dashboard.py` separately.

1. **Download** the latest `.dmg` from the [GitHub Releases page](https://github.com/tokenpulse/tokenpulse/releases)
2. **Mount** the DMG and drag TokenPulse into Applications
3. **First launch:** macOS will block the unsigned app. Right-click → **Open** → **Open** again. Only needed once.
4. TokenPulse appears in your **menu bar** with:
   - Today's spend: **"Today: $X.XX"**
   - **"Open Dashboard"** — opens `http://localhost:4200` in your browser
   - Budget alert notifications (macOS push notifications)
5. **Start the dashboard separately:**
   ```bash
   python3 web-dashboard.py
   ```
   Or set it up as a launchd service (see Option A above).

---

## Configuring Your Tools

Point your AI tools at `http://localhost:4100` instead of the provider's real API endpoint. TokenPulse forwards everything transparently — your tools won't know the difference.

The dashboard is at `http://localhost:4200` — open it in any browser.

---

### Cursor

1. Open Cursor → **Settings** → **Models**
2. Set **OpenAI Base URL** to: `http://localhost:4100`
3. Save and restart Cursor

---

### Python — OpenAI SDK

**Environment variable (recommended):**

```bash
export OPENAI_BASE_URL=http://localhost:4100
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent.

**In code:**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4100",
    api_key="your-api-key"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

---

### Python — Anthropic SDK

**Environment variable:**

```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

**In code:**

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://localhost:4100/anthropic",
    api_key="your-api-key"
)
```

---

### Shell / CLI

Add to `~/.zshrc` or `~/.bashrc`:

```bash
# TokenPulse proxy
export OPENAI_BASE_URL=http://localhost:4100
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

Then `source ~/.zshrc`.

---

### Ollama

Point tools that talk to Ollama at TokenPulse's Ollama endpoint instead of Ollama directly:

```
http://localhost:4100/ollama
```

This replaces the default `http://localhost:11434`. TokenPulse forwards everything to Ollama and logs token usage. Tested and verified with local models.

**Example (curl):**

```bash
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

---

### LM Studio

Point your tools at TokenPulse's LM Studio endpoint:

```
http://localhost:4100/lmstudio
```

This replaces the default `http://localhost:1234`.

---

### OpenClaw

Edit your `openclaw.json` configuration:

```json
{
  "providers": {
    "openai": {
      "baseUrl": "http://localhost:4100"
    },
    "anthropic": {
      "baseUrl": "http://localhost:4100/anthropic"
    }
  }
}
```

---

### Open WebUI

1. Log in as admin → **Admin** → **Connections**
2. Set **OpenAI Base URL** to: `http://localhost:4100`
3. Set **Ollama Base URL** to: `http://localhost:4100/ollama` (if using Ollama)
4. Save

---

### Any OpenAI-Compatible Tool

If your tool supports a custom base URL, change it to:

```
http://localhost:4100
```

TokenPulse speaks the OpenAI API format natively. Any tool that supports a custom OpenAI endpoint works out of the box.

---

## Verification

Send a test request through the proxy to confirm everything is working:

```bash
# Test cloud API (OpenAI)
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}],"max_tokens":5}'
```

```bash
# Test local model (Ollama)
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

You should get a normal API response back. Now open the dashboard:

```
http://localhost:4200
```

Your test request should appear in the activity feed with the model name, token count, and estimated cost. If it shows up — you're good to go.

---

## Dashboard Features

The web dashboard at `:4200` gives you full visibility into your AI usage:

- **Real-time activity feed** — live-updating timeline of all requests with animated entries
- **Cost tracking** — API spend vs subscription vs local, with per-model and per-provider breakdowns
- **Budget alerts** — set spending limits with macOS push notifications when thresholds are reached
- **Spending forecasts** — projected costs based on your usage patterns
- **Error monitoring** — per-model error rates, error timeline, and troubleshooting info
- **Model comparison** — side-by-side cost and usage breakdown across all models
- **Project/source tagging** — automatic tagging via User-Agent detection and custom headers
- **Activity heatmap** — GitHub-style 30-day × 24-hour usage visualization
- **Cost optimization recommendations** — actionable suggestions to reduce spend
- **Auto-generated insights** — trends, anomalies, and usage patterns surfaced automatically
- **CSV data export** — download all request data for your own analysis
- **Time range filtering** — Today, 7 Days, 30 Days, All Time
- **Expandable request details** — click any request to see full token breakdown
- **SVG charts** — area charts with hover tooltips for spend over time

The dashboard auto-refreshes every 30 seconds. Just leave it open.

---

## Data Export

Click **Export CSV** in the dashboard to download all logged requests — timestamps, models, token counts (including cached and reasoning tokens), costs, source tags, and more. Use it for:

- Tracking expenses for tax purposes
- Building custom reports in a spreadsheet
- Analyzing usage patterns over time

---

## Troubleshooting

### Proxy not starting?

Check if port 4100 is already in use:

```bash
lsof -i :4100
```

If another process holds the port, stop it first. TokenPulse uses `SO_REUSEADDR` to prevent conflicts on restart, but another active listener will still block it.

### Dashboard not loading?

```bash
# Check if web-dashboard.py is running
lsof -i :4200

# Check dashboard logs
tail -f /tmp/tokenpulse-dashboard.log
tail -f /tmp/tokenpulse-dashboard-error.log
```

Make sure you're running `python3 web-dashboard.py` — the dashboard is a separate process from the proxy.

### No requests showing in the dashboard?

- Confirm your tool is pointed at `http://localhost:4100` (not the provider directly)
- Check for trailing slash issues in the URL
- Run the curl verification test above to confirm the proxy is accepting requests
- Wait up to 30 seconds for the dashboard to auto-refresh (or refresh manually)

### Tokens showing as 0?

Some providers handle token reporting differently with streaming. TokenPulse extracts tokens from streamed chunks for OpenAI, Anthropic, Groq, and Mistral. If tokens still show 0:

- Check if the provider returns `usage` data in the response
- Try a non-streaming request to verify

### Can't access dashboard from another device?

- Make sure `TOKENPULSE_HOST` is set to `0.0.0.0` (not `127.0.0.1`)
- Verify both devices are on the same network
- Check your firewall settings
- Try accessing via the server's IP: `http://<server-ip>:4200`

### macOS blocks the app on first launch?

Normal for unsigned apps. Right-click → Open → Open. Only needed once.

### Need help?

Open an issue on [GitHub](https://github.com/tokenpulse/tokenpulse/issues) or visit [tokenpulse.to](https://tokenpulse.to).
