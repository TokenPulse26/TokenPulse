# Getting Started with TokenPulse

This guide walks you through installing TokenPulse, configuring your AI tools to use it, and accessing the dashboard — whether you're running it on your desktop or a headless server.

---

## What TokenPulse Does

TokenPulse sits between your AI tools and the APIs they talk to. It runs a local proxy on port **4100** that intercepts every request, logs token usage and costs to a local SQLite database, and serves a live dashboard on port **4200**. Your API keys pass through transparently — nothing is stored or sent anywhere.

```
Your AI tool  →  localhost:4100  →  OpenAI / Anthropic / Google / etc.
                      ↓
                 SQLite DB  →  Dashboard (localhost:4200)
```

---

## Installation (macOS)

### Option A: Desktop App (DMG)

1. **Download** the latest `.dmg` from the [GitHub Releases page](https://github.com/tokenpulse/tokenpulse/releases)
2. **Mount** the DMG by double-clicking it
3. **Drag** TokenPulse into your Applications folder
4. **First launch:** Since the app is not signed with an Apple Developer certificate, macOS will block it. To open it:
   - Right-click (or Control-click) on TokenPulse in Applications
   - Click **Open**
   - Click **Open** again in the confirmation dialog
   - You only need to do this once — after that, it opens normally
5. TokenPulse will appear in your **menu bar** (system tray). The proxy and dashboard start automatically.

### Option B: Headless Binary (Servers)

If you're running TokenPulse on a Mac Mini, Mac Studio, DGX Spark, or any machine without a display, you can run just the binary without the desktop app.

1. **Download** the binary from the [GitHub Releases page](https://github.com/tokenpulse/tokenpulse/releases) (look for the standalone binary, not the DMG)
2. **Copy it** to a convenient location:
   ```bash
   sudo cp tokenpulse /usr/local/bin/tokenpulse
   sudo chmod +x /usr/local/bin/tokenpulse
   ```
3. **Run it** to verify it works:
   ```bash
   tokenpulse
   ```
   You should see output confirming the proxy is running on port 4100 and the dashboard on port 4200.

---

## Headless Server Setup (Auto-Start)

To keep TokenPulse running 24/7 on a headless server, set it up as a macOS launch daemon using `launchd`.

### Step 1: Create the plist file

Save the following as `~/Library/LaunchAgents/com.tokenpulse.app.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tokenpulse.app</string>

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

> **Note:** Setting `TOKENPULSE_HOST` to `0.0.0.0` allows other devices on your network to reach the proxy and dashboard. If you only need local access, you can omit this or set it to `127.0.0.1`.

### Step 2: Load the service

```bash
launchctl load ~/Library/LaunchAgents/com.tokenpulse.app.plist
```

### Step 3: Verify it's running

```bash
launchctl list | grep tokenpulse
curl http://localhost:4200
```

### Step 4: Access from another device

Open a browser on any device on the same network and go to:

```
http://<server-ip>:4200
```

Replace `<server-ip>` with the IP address of your server (e.g., `192.168.1.50`). You can find it with:

```bash
ipconfig getifaddr en0
```

### Managing the service

```bash
# Stop TokenPulse
launchctl unload ~/Library/LaunchAgents/com.tokenpulse.app.plist

# Start TokenPulse
launchctl load ~/Library/LaunchAgents/com.tokenpulse.app.plist

# Check logs
tail -f /tmp/tokenpulse.log
tail -f /tmp/tokenpulse-error.log
```

---

## Configuring Your Tools

The key idea: point your AI tools at `http://localhost:4100` instead of the provider's real API endpoint. TokenPulse forwards everything transparently — your tools won't know the difference.

### Cursor

1. Open Cursor
2. Go to **Settings** → **Models**
3. Find **OpenAI Base URL** (or equivalent)
4. Change it to: `http://localhost:4100`
5. Save and restart Cursor

### Python — OpenAI SDK

**Option A: Environment variable (affects all scripts)**

Add to your `~/.zshrc` (or `~/.bashrc`):

```bash
export OPENAI_BASE_URL=http://localhost:4100
```

Then restart your terminal or run `source ~/.zshrc`.

**Option B: In your code**

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

### Python — Anthropic SDK

**Option A: Environment variable**

```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

**Option B: In your code**

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://localhost:4100/anthropic",
    api_key="your-api-key"
)
```

### Shell / .zshrc

Add these lines to `~/.zshrc` to route all your terminal-based AI tools through TokenPulse:

```bash
# TokenPulse proxy
export OPENAI_BASE_URL=http://localhost:4100
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

Restart your terminal or run:

```bash
source ~/.zshrc
```

### Ollama

If you use tools that talk to Ollama (like Open WebUI, Continue, or custom scripts), point them at TokenPulse's Ollama endpoint instead of Ollama directly:

```
http://localhost:4100/ollama
```

This replaces the default `http://localhost:11434`. TokenPulse forwards everything to Ollama and logs the token usage.

### LM Studio

Same idea — point your tools at TokenPulse's LM Studio endpoint:

```
http://localhost:4100/lmstudio
```

This replaces the default `http://localhost:1234`.

### OpenClaw

Edit your `openclaw.json` configuration file. Find the `providers` section and update the `baseUrl` for each provider:

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

### Open WebUI

1. Log in as an admin
2. Go to **Admin** → **Connections**
3. Change the **OpenAI Base URL** to: `http://localhost:4100`
4. If using Ollama, change the **Ollama Base URL** to: `http://localhost:4100/ollama`
5. Save

### Any OpenAI-Compatible Tool

If your tool supports a custom base URL (most do), just change it to:

```
http://localhost:4100
```

That's it. TokenPulse speaks the OpenAI API format natively, so any tool that supports a custom OpenAI endpoint will work out of the box.

---

## Verifying It Works

Run this from your terminal to send a test request through the proxy:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}],"max_tokens":5}'
```

Replace `YOUR_API_KEY` with your actual OpenAI API key. You should get a normal API response back.

Now open the dashboard:

- **Desktop app:** The main window shows the dashboard
- **Browser:** Go to [http://localhost:4200](http://localhost:4200)

You should see your test request logged with the model name, token count, and estimated cost. If it shows up — you're good to go.

---

## Accessing the Dashboard

### Desktop App

The app window **is** the dashboard. It opens automatically when you launch TokenPulse. You can also access it from the system tray icon.

### Headless / Remote Access

Open a browser on any device on the same network and go to:

```
http://<server-ip>:4200
```

The web dashboard is identical to the desktop version and **auto-refreshes every 5 seconds** — just leave it open and watch your usage update in real time.

### What You'll See

- **Total spend** across all providers
- **Per-model breakdowns** with token counts and costs
- **Daily spend charts** stacked by provider
- **Time range filters** — Today, 7 Days, 30 Days, All Time
- **Request log** with timestamps, models, and token details

---

## Data Export

### CSV Export

Go to the **Settings** page in the dashboard and click **Export CSV**. This downloads a full export of all logged requests, including timestamps, models, token counts, and costs.

Use this for:
- Tracking expenses for tax purposes
- Building custom reports in a spreadsheet
- Analyzing usage patterns over time

---

## Troubleshooting

### Proxy not starting?

Check if something else is already using port 4100:

```bash
lsof -i :4100
```

If another process is using the port, stop it first or configure TokenPulse to use a different port.

### No requests showing in the dashboard?

- Make sure your tool is pointed at `http://localhost:4100` (not the provider directly)
- Double-check that the URL doesn't have a trailing slash issue
- Try the curl test above to confirm the proxy is accepting requests

### Tokens showing as 0?

Some providers and tools handle token reporting differently with streaming enabled. If your tool uses streaming responses (SSE), TokenPulse tracks tokens from the streamed chunks. If tokens still show 0:
- Check if the provider returns `usage` data in the response
- Try sending a non-streaming request to verify

### Dashboard not loading?

Try opening [http://localhost:4200](http://localhost:4200) directly in your browser. If it doesn't load:
- Make sure TokenPulse is actually running (check the system tray or run `lsof -i :4200`)
- Check the logs at `/tmp/tokenpulse.log` and `/tmp/tokenpulse-error.log`

### macOS blocks the app on first launch?

This is normal for unsigned apps. Right-click → Open → Open. You only need to do this once. See the [Installation](#option-a-desktop-app-dmg) section above.

### Need help?

Open an issue on [GitHub](https://github.com/tokenpulse/tokenpulse/issues) or visit [tokenpulse.to](https://tokenpulse.to) for more info.
