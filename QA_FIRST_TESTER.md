# TokenPulse First-Tester QA Pack

Use this pack to run a consistent sanity check of TokenPulse.

Audience:
- non-coding early testers
- AI agents validating setup for a user

Platform target for v1: macOS Apple Silicon.

---

## What counts as success

A run is considered **successful** when all of the following are true:
1. Install completes without fatal errors.
2. Proxy health endpoint returns `"status": "ok"`.
3. Dashboard returns HTTP `200`.
4. At least one provider test request appears in recent requests.
5. CSV export endpoint returns a CSV file.
6. Uninstall command completes cleanly.

## What counts as a bug

Treat as a **bug** if any of the following happen:
- install fails on supported platform with no actionable error message
- `/health` does not return ok after successful install
- dashboard does not load on `http://127.0.0.1:4200`
- requests succeed but never appear in TokenPulse recent requests
- CSV export fails or returns malformed output
- uninstall leaves launchd services running unexpectedly

---

## Test 1 — Install

Run:

```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
```

Expected output includes lines like:
- `✅ Proxy binary installed:`
- `✅ proxy healthy at http://127.0.0.1:4100/health`
- `✅ dashboard healthy at http://127.0.0.1:4200/`
- `🟢 TokenPulse is running`

If install fails, capture full terminal output.

---

## Test 2 — Proxy health

Run:

```bash
curl -s http://127.0.0.1:4100/health | python3 -m json.tool
```

Expected output includes:
- `"status": "ok"`
- `"port": 4100`
- `"dashboard_url": "http://127.0.0.1:4200"`

---

## Test 3 — Dashboard health

Run:

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4200/
```

Expected output:

```text
200
```

---

## Test 4 — OpenAI-compatible test request

Run (replace `$OPENAI_API_KEY`):

```bash
curl http://localhost:4100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "x-tokenpulse-project: qa-first-tester" \
  -H "x-tokenpulse-tag: openai-check" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```

Expected output:
- JSON response from provider (non-empty)
- no proxy crash

---

## Test 5 — Anthropic test request

Run (replace `$ANTHROPIC_API_KEY`):

```bash
curl http://localhost:4100/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-tokenpulse-project: qa-first-tester" \
  -H "x-tokenpulse-tag: anthropic-check" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":8,"messages":[{"role":"user","content":"ping"}]}'
```

Expected output:
- JSON response from provider (non-empty)
- no proxy crash

---

## Test 6 — Ollama test request (optional local model)

Precondition: Ollama is running.

Run:

```bash
curl http://localhost:4100/ollama/api/chat \
  -H "Content-Type: application/json" \
  -H "x-tokenpulse-project: qa-first-tester" \
  -H "x-tokenpulse-tag: ollama-check" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"ping"}],"stream":false}'
```

Expected output:
- JSON response (if Ollama model available)
- if Ollama not running, clear error is acceptable and should be reported as environment/setup issue

---

## Test 7 — Confirm recent requests

Run:

```bash
curl -s "http://localhost:4100/api/requests?limit=5" | python3 -m json.tool
```

Expected output:
- at least one request object appears after tests above
- rows should include provider/model/timestamp

Also visually check dashboard:
- open `http://127.0.0.1:4200`
- confirm Activity/Recent Requests updates

---

## Test 8 — Export CSV

Run:

```bash
curl -s -D /tmp/tokenpulse_csv_headers.txt "http://127.0.0.1:4200/export/csv?range=today" -o /tmp/tokenpulse_requests.csv
head -n 5 /tmp/tokenpulse_requests.csv
```

Expected output:
- CSV file exists at `/tmp/tokenpulse_requests.csv`
- first line is CSV header row
- file contains request rows when traffic exists

---

## Test 9 — Uninstall

Run:

```bash
curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --yes
```

Expected output:
- uninstall confirmation
- TokenPulse launchd services removed/stopped

---

## Collect logs for bug reports

Run:

```bash
mkdir -p /tmp/tokenpulse-qa-logs
cp ~/.tokenpulse/logs/proxy.log /tmp/tokenpulse-qa-logs/ 2>/dev/null || true
cp ~/.tokenpulse/logs/proxy.error.log /tmp/tokenpulse-qa-logs/ 2>/dev/null || true
cp ~/.tokenpulse/logs/dashboard.log /tmp/tokenpulse-qa-logs/ 2>/dev/null || true
cp ~/.tokenpulse/logs/dashboard.error.log /tmp/tokenpulse-qa-logs/ 2>/dev/null || true
ls -lah /tmp/tokenpulse-qa-logs
```

Include these logs when filing issues.

---

## Short tester feedback template

Copy/paste and fill:

```text
TokenPulse version:
macOS version:
Mac chip:
Install method: install.sh / from-source
Routes tested: OpenAI-compatible / Anthropic / Ollama
Result summary: PASS / PARTIAL / FAIL
What worked:
What failed:
Expected behavior:
Actual behavior:
Logs attached: yes/no
Screenshot attached (if dashboard issue): yes/no
```
