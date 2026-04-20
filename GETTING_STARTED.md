# Getting Started with TokenPulse

This guide is the quick start for **free early access** testers.

For v1, TokenPulse supports **macOS Apple Silicon only**.
If you want the full first-tester flow, use [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md).

---

## What TokenPulse does

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

## v1 support status

**Supported for v1:**
- macOS Apple Silicon

**Coming soon:**
- Linux, Windows, and NVIDIA-based setups, join the feedback channel to be notified

---

## Recommended early-access path

The supported v1 path is:
1. run `./install.sh`
2. start the proxy and dashboard
3. route one test request through TokenPulse
4. verify it appears in the dashboard at `http://127.0.0.1:4200`

The installer is a bootstrap helper for a narrow setup. It is useful, but it is not a polished general release installer.

---

## 5-minute verification flow

### 1. Install

```bash
./install.sh
```

### 2. Start the services

```bash
~/.tokenpulse/tokenpulse
python3 ~/.tokenpulse/web-dashboard.py
```

If you are running from the repo instead, use the equivalent local paths.

### 3. Connect one route and verify

Use one route only for your first test:
- OpenAI-compatible: `http://localhost:4100`
- Anthropic: `http://localhost:4100/anthropic`
- Ollama: `http://localhost:4100/ollama`
- LM Studio: `http://localhost:4100/lmstudio`

Recommended first test:
- OpenAI-compatible for the simplest check
- Ollama if you specifically want the recommended local-model path

Example verification request:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello from TokenPulse"}],"max_tokens":10}'
```

Then open:

```text
http://127.0.0.1:4200
```

Success means:
- the request appears in recent activity
- the provider looks correct
- the model looks correct
- token and cost fields appear when that provider exposes them

For the full checklist, use [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md).

---

## Route notes

### OpenAI-compatible tools

Use:

```text
http://localhost:4100
```

### Anthropic tools

Use:

```text
http://localhost:4100/anthropic
```

### Ollama through TokenPulse

Use:

```text
http://localhost:4100/ollama
```

Ollama is the recommended local-model path for v1.

### LM Studio through TokenPulse

Use:

```text
http://localhost:4100/lmstudio
```

LM Studio is supported, but lower confidence than Ollama today.

---

## Advanced / manual paths

These paths still exist, but they are not the supported first-tester path:
- build and run from source
- run background services manually with `launchd`
- adapt for Linux manually

If you want the path with the fewest surprises, stick to `install.sh` on macOS Apple Silicon.

---

## Troubleshooting

### Proxy not starting

```bash
lsof -i :4100
```

### Dashboard not loading

Open:

```text
http://127.0.0.1:4200
```

Then check:

```bash
lsof -i :4200
```

### No requests showing up

Check these first:
- your tool is pointed at TokenPulse, not the provider directly
- you used the correct route prefix
- the proxy is actually running on port `4100`
- the dashboard is reading the same local database the proxy is writing to

---

## Feedback

Report bugs and onboarding friction here:
- `TODO: [INSERT FEEDBACK LINK]`

---

Need the full onboarding checklist? Use [FIRST_TESTER_ONBOARDING.md](FIRST_TESTER_ONBOARDING.md).
