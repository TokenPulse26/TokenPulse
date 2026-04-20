# TokenPulse First Tester Onboarding

This is the **single source of truth** for first-tester onboarding.

For v1, TokenPulse is **free early access** for technical testers on **macOS Apple Silicon only**.

**Feedback:** `TODO: [INSERT FEEDBACK LINK]`

Linux, Windows, and NVIDIA-based setups are not part of the supported v1 path yet.

---

## What TokenPulse is today

TokenPulse is currently:
- a local proxy on port `4100`
- a browser dashboard on port `4200`
- a secondary macOS Tauri app-shell / tray layer

The browser dashboard is the primary interface.

This is not yet a polished mass-market installer flow. The goal of this onboarding guide is to get you from zero to one verified request as quickly and honestly as possible.

---

## Best-supported path

Use this order:
1. install with `install.sh`
2. start the proxy
3. start the dashboard
4. verify the dashboard loads
5. send one test request through the proxy
6. confirm it appears in the dashboard

Do not start by wiring up multiple tools or providers.

---

## Checklist

### 1. Install TokenPulse

Run:

```bash
./install.sh
```

This is the supported v1 install path for macOS Apple Silicon.

### 2. Start the proxy

```bash
~/.tokenpulse/tokenpulse
```

You want TokenPulse listening on:

```text
http://localhost:4100
```

### 3. Start the dashboard

```bash
python3 ~/.tokenpulse/web-dashboard.py
```

Then open:

```text
http://127.0.0.1:4200
```

### 4. Verify the dashboard loads

Success means the dashboard opens locally at:

```text
http://127.0.0.1:4200
```

### 5. Point one tool at TokenPulse

Use one route only for your first test:
- OpenAI-compatible: `http://localhost:4100`
- Anthropic: `http://localhost:4100/anthropic`
- Ollama: `http://localhost:4100/ollama`
- LM Studio: `http://localhost:4100/lmstudio`

Recommended first choices:
- OpenAI-compatible for the simplest first check
- Ollama for the recommended local-model path

LM Studio is supported, but lower confidence than Ollama today.

### 6. Make one recognizable test request

Example:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello from TokenPulse"}],"max_tokens":10}'
```

### 7. Confirm it appears in the dashboard

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

## Known limitations

Current early-access limitations:
- macOS Apple Silicon is the only supported v1 platform
- Ollama is the recommended local-model path today
- LM Studio is supported, but lower confidence than Ollama
- pricing data can be stale for some newer model families
- some dashboard time-range filters may not fully apply
- the Tauri app-shell is secondary, the browser dashboard is the main surface
- the installer is still a bootstrap helper, not a polished general release installer

---

## Troubleshooting

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
That does not always mean failure.
Some provider paths expose usage more clearly than others. First confirm the request itself appears correctly.

### If the installer path feels rough
That is expected today.
The installer is useful, but it is not yet a polished general-user install experience.

---

## Feedback

If you hit a bug, onboarding confusion, or data mismatch, report it here:
- `TODO: [INSERT FEEDBACK LINK]`

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
