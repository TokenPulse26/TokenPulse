# TokenPulse First Tester Onboarding

This guide is the **best-supported early-access path** for trying TokenPulse today.

It is written for a technical early tester who wants one clear setup path, one clear connection path, and one clear success check.

---

## What TokenPulse is today

TokenPulse is currently best understood as:
- a local proxy on port `4100`
- a browser dashboard on port `4200`
- a secondary macOS Tauri app-shell / tray layer

The browser dashboard is the primary interface.

The Tauri layer still exists in the repo and packaging flow, but it should not be described like the main polished product surface yet.

This is **not yet a polished mass-market installer flow**. The most reliable experience today is a local technical setup where you can run commands, point one AI tool at TokenPulse, and verify traffic in the dashboard.

---

## Best-supported path

If you want the fewest surprises, use this order:

1. run TokenPulse locally
2. start the dashboard
3. connect one tool through one TokenPulse route
4. send one test request
5. confirm it appears in the dashboard

Do not start by wiring up five tools at once.

---

## Step 1: Start TokenPulse

Start the proxy:

```bash
./tokenpulse
```

If you installed through the bootstrap installer, your path may be:

```bash
~/.tokenpulse/tokenpulse
```

You want TokenPulse listening on:

```text
http://localhost:4100
```

---

## Step 2: Start the dashboard

From the repo:

```bash
python3 web-dashboard.py
```

Or from the bootstrap install path:

```bash
python3 ~/.tokenpulse/web-dashboard.py
```

Then open:

```text
http://127.0.0.1:4200
```

---

## Step 3: Connect one tool only

Use one provider path first.

### OpenAI-compatible route

Set:

```bash
export OPENAI_BASE_URL=http://localhost:4100
```

### Anthropic route

Set:

```bash
export ANTHROPIC_BASE_URL=http://localhost:4100/anthropic
```

### Ollama route

Set your tool’s Ollama base URL to:

```text
http://localhost:4100/ollama
```

### LM Studio route

Set your LM Studio-compatible base URL to:

```text
http://localhost:4100/lmstudio
```

LM Studio route support exists, but it is still less strongly verified end-to-end than the Ollama path today. If you just want the cleanest first local-model test, start with Ollama first and treat LM Studio as a second verification step.

If your tool supports a custom OpenAI-compatible base URL, the plain TokenPulse root route is often the easiest first test:

```text
http://localhost:4100
```

---

## Step 4: Send one known test request

Here is the simplest OpenAI-compatible check:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello from TokenPulse"}],"max_tokens":10}'
```

If you are testing Anthropic instead, make sure you use the Anthropic route and credentials your tool actually expects.

The goal is not a fancy prompt. The goal is one request you can recognize in the dashboard.

---

## Step 5: Verify success in the dashboard

Open or refresh:

```text
http://127.0.0.1:4200
```

What success looks like:
- a new request appears in recent activity
- the provider looks correct
- the model looks correct
- token and cost fields appear when that upstream/provider path exposes them
- the request timing looks plausible

---

## What to do if something feels wrong

### If the AI request succeeds but nothing appears in TokenPulse
Check these first:
- your tool is pointed at TokenPulse, not the provider directly
- you used the correct route prefix
- the proxy is actually running on port `4100`
- the dashboard is reading the same local database your proxy is writing to

### If the dashboard loads but looks empty
That usually means either:
- no request has actually gone through TokenPulse yet, or
- the request bypassed the proxy

### If tokens or cost do not appear
That does **not always mean failure**.
Some provider paths and request types expose usage more clearly than others. The first question is:
- did the request appear correctly at all?

If yes, start by treating it as a route/visibility success, then verify the provider-specific usage behavior after that.

### If the installer path feels rough
That is expected today.
The bootstrap installer is useful, but it is not yet the same thing as a polished general-user installer.

---

## What to test next after the first success

Once one request appears correctly, the next best tests are:
1. one real request from the AI tool you care about most
2. one second provider route if you use a hybrid setup
3. the Ollama route if local tracking matters to you most
4. the LM Studio route after that if you want to verify the lighter-confidence local path

Only widen scope after the first clean success.

---

## Current honesty notes

TokenPulse is already useful, but still early.

Current strongest reality:
- local-first proxy works
- browser dashboard is the main experience
- multiple real provider routes are already tracking successfully
- Ollama is the strongest verified local-model path right now

Current rough edges:
- onboarding is still being tightened
- installer experience is narrower than a polished public release
- some provider/request-type coverage is stronger than others
- LM Studio support is real, but still carries lighter verification confidence than Ollama today

---

## Recommended first tester mindset

Treat TokenPulse today as:
- a promising, already-useful local tool
- best for technical early adopters
- strongest when tested one route at a time

If you can get one clean request to appear in the dashboard, you are using the real product, not a mockup.
