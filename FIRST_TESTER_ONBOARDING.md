# TokenPulse First Tester Onboarding

This is the **single source of truth** for first-tester onboarding.

For v1, TokenPulse is **free early access** for technical testers on **macOS Apple Silicon only**.

**Feedback:** [github.com/TokenPulse26/TokenPulse/issues](https://github.com/TokenPulse26/TokenPulse/issues)

Linux, Windows, and NVIDIA-based setups are not part of the supported v1 path yet.

---

## What TokenPulse is today

TokenPulse is currently:
- a local AI proxy on port `4100`
- a browser dashboard on port `4200`
- a secondary macOS Tauri app-shell / tray layer

The browser dashboard is the primary interface.

The install flow is now agent-installable for the supported macOS Apple Silicon path, but this is still early access rather than a polished mass-market installer.

---

## Best-supported path

Use this order:
1. install with the one-command installer
2. let the installer auto-start the proxy and dashboard
3. verify `/health`
4. open the dashboard
5. send one test request through the proxy
6. confirm it appears in the dashboard

Do not start by wiring up multiple tools or providers. Get one clean request first.

---

## Checklist

### 1. Install TokenPulse

Recommended one-command install:

```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
```

If you already cloned the repo, this is also fine:

```bash
./install.sh
```

The installer should:
- check basic prerequisites
- download the pre-built macOS ARM release binary
- install the dashboard files
- create launchd services
- start the proxy and dashboard
- run a health check
- print the dashboard URL

If you do not want auto-start, use:

```bash
./install.sh --no-autostart
```

### 2. Verify the proxy is healthy

Run:

```bash
curl -fsS http://127.0.0.1:4100/health
```

Success means you see JSON with:
- `"status":"ok"`
- `"service":"tokenpulse-proxy"`
- `"dashboard_url":"http://127.0.0.1:4200"`

### 3. Open the dashboard

Open:

```text
http://127.0.0.1:4200
```

Success means the TokenPulse dashboard loads locally in your browser.

### 4. Point one tool at TokenPulse

Use one route only for your first test:
- OpenAI-compatible: `http://localhost:4100`
- Anthropic: `http://localhost:4100/anthropic`
- Ollama: `http://localhost:4100/ollama`
- LM Studio: `http://localhost:4100/lmstudio`

Recommended first choices:
- OpenAI-compatible for the simplest API-style check
- Ollama for the recommended local-model path

LM Studio is supported, but lower confidence than Ollama today.

### 5. Make one recognizable test request

Example OpenAI-compatible request:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello from TokenPulse"}],"max_tokens":10}'
```

### 6. Confirm it appears in the dashboard

Open or refresh:

```text
http://127.0.0.1:4200
```

Success looks like:
- a new request appears in recent activity
- the provider looks correct
- the model looks correct
- token and cost fields appear when that provider exposes them
- the timestamp is fresh and matches your test

If that works, you have a valid first success.

---

## Uninstall / Reset

Clean uninstall:

```bash
~/.tokenpulse/uninstall.sh
```

Keep your local data:

```bash
~/.tokenpulse/uninstall.sh --keep-data
```

Non-interactive uninstall:

```bash
~/.tokenpulse/uninstall.sh --yes
```

---

## Known limitations

Current early-access limitations:
- macOS Apple Silicon is the only supported v1 platform
- Ollama is the recommended local-model path today
- LM Studio is supported, but lower confidence than Ollama
- pricing data can lag for some newer model families
- the Tauri app-shell is secondary; the browser dashboard is the main surface
- codesigning/notarization is skipped for early access, so macOS may require manually allowing the binary

---

## Troubleshooting

### If the dashboard does not load

Check services:

```bash
launchctl list | grep tokenpulse
```

Check proxy health:

```bash
curl -fsS http://127.0.0.1:4100/health
```

### If the dashboard loads but looks empty

That usually means either:
- no request has actually gone through TokenPulse yet, or
- the request bypassed the proxy

### If the AI request succeeds but nothing appears in TokenPulse

Check these first:
- your tool is pointed at TokenPulse, not the provider directly
- you used the correct route prefix
- the proxy is actually running on port `4100`
- the dashboard is reading the same local database the proxy is writing to

### If tokens or cost do not appear

That does not always mean failure. Some provider paths expose usage more clearly than others. First confirm the request itself appears correctly.

---

## Feedback

If you hit a bug, onboarding confusion, or data mismatch, report it here:
- [github.com/TokenPulse26/TokenPulse/issues](https://github.com/TokenPulse26/TokenPulse/issues)

Useful bug reports include:
- your route used
- what command or tool you tested with
- what you expected to see
- what actually happened
- screenshots if the dashboard looked wrong

---

## What to do next after first success

Once one request appears correctly, the next best tests are:
1. one real request from the AI tool you care about most
2. one second provider route if you use a hybrid setup
3. Ollama if local tracking matters most
4. LM Studio after that if you want to test the lower-confidence local path

Keep scope narrow until the first success is solid.
