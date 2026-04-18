# TokenPulse Verification Flow v1

This is the **smallest credible verification flow** for TokenPulse v1.

The goal is not to build a whole secondary verification product yet.
The goal is to give a user one clear way to prove:
- TokenPulse is running
- their request went through TokenPulse
- the dashboard is reflecting that request in a believable way

---

## What this flow is trying to prove

A successful verification run should answer four questions:

1. **Did my request go through TokenPulse?**
2. **Did TokenPulse identify the right provider and model?**
3. **Did the dashboard show the request clearly enough to trust the route?**
4. **If usage fields were available, did they show up?**

That is enough for v1.

It is **not** trying to prove every advanced thing yet, like:
- full route tracing
- bypass detection across every tool
- historical verification state
- formal provider support tiers UI
- exact confidence labeling for every token field

Those can come later.

---

## Verification prerequisites

Before a user runs the verification flow:

1. the proxy must be running on `http://localhost:4100`
2. the dashboard must be available on `http://127.0.0.1:4200`
3. the user must point **one tool** or test request at the correct TokenPulse route

Do not ask a first tester to verify five providers at once.

---

## Minimal v1 verification flow

### Step 1: Start TokenPulse

Start the proxy and dashboard.

Expected result:
- proxy is reachable on port `4100`
- dashboard is reachable on port `4200`

### Step 2: Pick one route

Choose one path only:
- OpenAI-compatible via `http://localhost:4100`
- Anthropic via `http://localhost:4100/anthropic`
- Ollama via `http://localhost:4100/ollama`
- LM Studio via `http://localhost:4100/lmstudio` (implemented, but currently a lighter-confidence route than Ollama)

Recommended first test:
- OpenAI-compatible route, because it is the simplest mental model for most technical users
- If you specifically want a local-model verification, start with **Ollama first**

### Step 3: Send one recognizable request

Use one short test prompt with a recognizable string.

Example:

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Verification request from TokenPulse"}],"max_tokens":10}'
```

### Step 4: Open the dashboard

Open or refresh:

```text
http://127.0.0.1:4200
```

### Step 5: Confirm the verification points

A verification run counts as **pass** when all of these are true:

- a new request appears in recent activity
- the provider is correct
- the model is correct or close enough to the expected identifier
- the timestamp is fresh and matches the test
- the request does not look like stale historical traffic

A verification run counts as **strong pass** when these are also true:
- token fields appear where expected
- cost appears where expected
- latency / request shape look plausible

---

## Pass / partial / fail definition

### Pass
- request appears
- provider/model are correct
- route confidence is high

### Partial pass
- request appears
- provider/model are mostly correct
- but usage fields are missing or incomplete

Interpretation:
- TokenPulse likely saw the route correctly
- usage extraction may still depend on provider/request-type specifics

### Fail
- request does not appear
- or appears with the wrong provider/path meaning
- or the dashboard state makes the route impossible to trust

Interpretation:
- first troubleshoot routing/bypass before talking about analytics quality

---

## What the UI/docs should say

The product does not need a giant verification subsystem yet.

For v1, the verification language should simply teach the user:
- send one request
- look for it in the dashboard
- confirm provider/model/timestamp
- treat usage fields as the second layer of confidence, not the first

That framing is honest and easy to understand.

---

## Recommended v1 product wording

Suggested wording:

> To verify TokenPulse, point one AI tool at the correct TokenPulse route, send one test request, and confirm that the request appears in the dashboard with the expected provider and model details. If usage data is available for that provider and request type, TokenPulse should show token and cost fields as well.

---

## What should stay out of scope for now

Do not block launch on:
- route trace IDs everywhere
- full provider-health framework
- historical verification log UI
- broad bypass detection automation
- exact support-tier UI

Those are good future improvements, but the v1 product only needs a clean proof-of-life flow.

---

## Bottom line

The minimal credible TokenPulse verification flow is:

1. start TokenPulse
2. route one request through it
3. open the dashboard
4. confirm the request appears with the expected provider/model/timestamp
5. treat usage fields as an additional confidence signal when available

That is enough to support early testers without pretending the product has a full verification platform already.
