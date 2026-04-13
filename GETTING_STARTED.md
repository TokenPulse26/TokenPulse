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

## Recommended Early-Access Path

For now, the clearest TokenPulse path is:
- a technical early tester
- running locally
- using the browser dashboard as the primary interface
- starting either from the repo or the narrow bootstrap installer

If you want the path with the fewest surprises, prefer the **run-from-source flow** first.

The repo still includes Tauri packaging/app-shell configuration, but that should currently be treated as secondary to the browser dashboard rather than as the main polished user surface.

## Quick Start

1. **Start the proxy**
   ```bash
   ./tokenpulse
   ```

2. **Start the dashboard**
   ```bash
   python3 web-dashboard.py
   ```

3. **Connect one tool using the correct TokenPulse route**
   - OpenAI-compatible: `http://localhost:4100`
   - Anthropic: `http://localhost:4100/anthropic`
   - Ollama: `http://localhost:4100/ollama`
   - LM Studio: `http://localhost:4100/lmstudio`

4. **Open the dashboard** at `http://127.0.0.1:4200`

5. **Run one recognizable verification request** so you can confirm traffic is actually appearing in TokenPulse

---

## Installation Paths

## Option A: Run from the repo

This is the most accurate path if you're building from source or testing current development work.

### Requirements
- Rust (stable)
- Python 3.8+

### Build and run

```bash
git clone https://github.com/TokenPulse26/TokenPulse.git
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

This is a **bootstrap helper for a narrow setup**, not a polished packaged installer or a broad cross-platform release flow. If you are evaluating TokenPulse as an outside tester, keep that expectation in mind.

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
curl http://127.0.0.1:4200
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

By default, the current dashboard binds to `127.0.0.1:4200` only.

That means the stock TokenPulse dashboard is currently meant for local access on the same machine:

```text
http://127.0.0.1:4200
```

If you want LAN access from another device, treat that as a manual modification rather than a built-in default. The current docs should not imply that remote dashboard access already works out of the box.

Find your machine IP with:

```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I
```

---

## Configuring Your Tools

Use one route first, then verify it before widening scope.

### OpenAI-compatible tools

```bash
export OPENAI_BASE_URL=http://localhost:4100
```

Use this for tools that expect an OpenAI-style `/v1/...` API.

### Anthropic tools

```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

Use the `/anthropic` route for Anthropic-native clients. Do not assume the plain root route is interchangeable here.

### Ollama through TokenPulse

Use:

```text
http://localhost:4100/ollama
```

Ollama is currently the strongest verified local-model path in TokenPulse.

### LM Studio through TokenPulse

Use:

```text
http://localhost:4100/lmstudio
```

LM Studio route support exists, but it is currently less verified than Ollama. On this host, recent LM Studio failures matched the LM Studio upstream not running on port `1234`, not a confirmed TokenPulse routing bug.

### Example local-model verification request

```bash
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

If the request appears in the dashboard but token fields are incomplete, treat that first as a routing success. Local-model usage fields depend on what the upstream response exposes.

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

The minimum success check for TokenPulse today is simple:

1. start the proxy
2. start the dashboard
3. send one known request through the correct TokenPulse route
4. open the dashboard
5. confirm the request appears with the expected provider/model details

Example test request through the OpenAI-compatible route:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}],"max_tokens":5}'
```

Then open:

```text
http://127.0.0.1:4200
```

What success looks like:
- the request appears in the dashboard after refresh / auto-refresh
- the provider/model fields look correct
- tokens and cost appear when the upstream/provider path exposes that data

If the request works upstream but does not show clearly in TokenPulse, troubleshoot route/bypass issues first before assuming the dashboard is wrong.

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
- the repo still contains active Tauri app-shell/packaging config, but that layer is secondary to the browser dashboard in current product positioning
- the installer is still a narrow bootstrap path, not a finished general-user install experience
- release/version metadata in packaging files may lag behind the latest feature work, so the source tree is the best reference for current behavior

---

Need more context? See [README.md](README.md), [AGENT_SETUP.md](AGENT_SETUP.md), or [CHANGELOG.md](CHANGELOG.md).
