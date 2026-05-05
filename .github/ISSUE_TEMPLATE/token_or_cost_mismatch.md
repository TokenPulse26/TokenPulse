---
name: Token or cost mismatch
about: Report mismatches between TokenPulse counts and provider/tool counts.
title: "[Token/Cost Mismatch] "
labels: [analytics, early-access]
assignees: []
---

## Environment
- **TokenPulse version:**
- **macOS version:**
- **Mac chip (Apple Silicon model):**
- **Install method:** (for example: `install.sh`, from source)
- **Provider route used:** (for example: `http://localhost:4100`, `/anthropic`, `/ollama`)
- **AI tool used:**

## Mismatch details
- **Provider:**
- **Model:**
- **Request type:** (streaming or non-streaming)
- **Expected token count:**
- **TokenPulse token count:**
- **Provider dashboard token count (if available):**

## What did you expect?

## What actually happened?

## Reproduction details
Include enough detail to reproduce (prompt shape, endpoint used, tool behavior, retries, etc.).

## Logs (required)
Please paste relevant excerpts from:
- `~/.tokenpulse/logs/proxy.error.log`
- `~/.tokenpulse/logs/dashboard.error.log`

```text
# Paste logs here
```

## Dashboard screenshot (if UI looked wrong)
Attach a screenshot if charts/tables/cards appeared incorrect.

## Additional context
Include any billing/cost context that might help explain the mismatch.
