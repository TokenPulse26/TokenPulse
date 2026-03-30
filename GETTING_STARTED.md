# Getting Started with TokenPulse

This guide walks through running TokenPulse locally, pointing your AI tools at it, and opening the dashboard.

---

## What TokenPulse Does

TokenPulse runs two local components:
- a proxy on port **4100** that sits in front of AI providers
- a web dashboard on port **4200** that reads from the local SQLite database

```text
Your AI Tools → TokenPulse Proxy (:4100) → AI Providers
                       ↓
                 SQLite Database
                       ↓
               Web Dashboard (:4200)
```

You point your tools at TokenPulse instead of the provider directly. TokenPulse forwards the request, logs usage metadata locally, and lets you inspect spend, activity, errors, budgets, and trends in the dashboard.

---

## Quick Start

1. **Start the proxy**
   ```bash
   ./tokenpulse
   ```

2. **Start the dashboard**
   ```bash
   python3 web-dashboard.py
   ```

3. **Point your tools at** `http://localhost:4100`

4. **Open the dashboard** at `http://localhost:4200`

---

## Installation Paths

## Option A: Run from the repo

This is the most accurate path if you're building from source or testing current development work.

### Requirements
- Rust (stable)
- Python 3.8+

### Build and run

```bash
git clone git@github.com:TokenPulse26/TokenPulse.git
cd TokenPulse/src-tauri
cargo build --release
cd ..
python3 web-dashboard.py
```

Then launch the built Rust binary in a second terminal, if needed for your setup.

---

## Option B: Use the installer script

The repo includes `install.sh`, which currently targets **macOS on Apple Silicon** and installs into `~/.tokenpulse`.

```bash
./install.sh
```

What the installer does today:
- downloads the current source files from the GitHub repo
- attempts to build the Rust app locally if `cargo` is installed
- installs the Python dashboard script

It is best thought of as a convenience bootstrapper, not a polished cross-platform installer yet.

---

## Option C: Run as background services

If you want TokenPulse always available on a workstation or home server, run the proxy and dashboard as services.

### macOS (launchd)

**Proxy** — save as `~/Library/LaunchAgents/com.tokenpulse.proxy.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tokenpulse.proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/absolute/path/to/tokenpulse</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/tokenpulse.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/tokenpulse-error.log</string>
</dict>
</plist>
```

**Dashboard** — save as `~/Library/LaunchAgents/com.tokenpulse.dashboard.plist`:

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
        <string>/absolute/path/to/web-dashboard.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/tokenpulse-dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/tokenpulse-dashboard-error.log</string>
</dict>
</plist>
```

Load them:

```bash
launchctl load ~/Library/LaunchAgents/com.tokenpulse.proxy.plist
launchctl load ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist
```

Check them:

```bash
launchctl list | grep tokenpulse
curl http://localhost:4200
```

### Linux (systemd)

**Proxy** — `/etc/systemd/system/tokenpulse-proxy.service`

```ini
[Unit]
Description=TokenPulse Proxy
After=network.target

[Service]
Type=simple
ExecStart=/absolute/path/to/tokenpulse
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Dashboard** — `/etc/systemd/system/tokenpulse-dashboard.service`

```ini
[Unit]
Description=TokenPulse Web Dashboard
After=network.target tokenpulse-proxy.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /absolute/path/to/web-dashboard.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tokenpulse-proxy
sudo systemctl enable --now tokenpulse-dashboard
```

---

## Accessing the Dashboard from Another Device

Open a browser on the same network and visit:

```text
http://<server-ip>:4200
```

You may need to adjust your process launch or service config so the dashboard binds to a non-loopback interface in your environment.

Find your machine IP with:

```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I
```

---

## Configuring Your Tools

### OpenAI-compatible tools

```bash
export OPENAI_BASE_URL=http://localhost:4100
```

### Anthropic tools

```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

### Ollama through TokenPulse

Use:

```text
http://localhost:4100/ollama
```

Example:

```bash
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

### LM Studio through TokenPulse

Use:

```text
http://localhost:4100/lmstudio
```

### OpenClaw

Example configuration:

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

### Any OpenAI-compatible tool

If it supports a custom base URL, set it to:

```text
http://localhost:4100
```

---

## Verification

Send a test request through the proxy:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}],"max_tokens":5}'
```

Then open:

```text
http://localhost:4200
```

Your request should appear in the dashboard after refresh / auto-refresh.

---

## What You'll See in the Dashboard

- live activity feed
- provider and model breakdowns
- project/source tagging
- 30-day heatmap
- budget tracking and alert history
- monthly spend forecasting
- reliability and error views
- optimization suggestions
- CSV export

The dashboard refreshes automatically every 30 seconds.

---

## Troubleshooting

### Proxy not starting

```bash
lsof -i :4100
```

If something else is using the port, stop it first.

### Dashboard not loading

```bash
lsof -i :4200
tail -f /tmp/tokenpulse-dashboard.log
tail -f /tmp/tokenpulse-dashboard-error.log
```

### No requests showing up

- confirm your tool is pointed at TokenPulse, not the provider directly
- run the curl test above
- give the dashboard up to 30 seconds to refresh

### Can't reach the dashboard from another device

- confirm the dashboard is not bound only to `127.0.0.1`
- verify both devices are on the same network
- check local firewall rules

---

## Notes on Current State

A few repo details are still in motion:
- the dashboard is the main user interface
- the optional Tauri app is best treated as tray/support functionality
- release/version metadata in packaging files may lag behind the latest feature work, so the source tree is the best reference for current behavior

---

Need more context? See [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), or the contributor-oriented [BRIEFING.md](BRIEFING.md).
