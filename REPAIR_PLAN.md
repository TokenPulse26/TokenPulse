# TokenPulse Repair Plan — 2026-03-28

## Current State Assessment

### What's Working ✅
- **Proxy (port 4100):** Running via launchd (`com.tokenpulse.proxy`), successfully forwarding requests
- **CLIProxy routing:** `POST /cliproxy/v1/chat/completions` → `http://127.0.0.1:8317/v1/chat/completions` works perfectly
- **Auth header forwarding:** Fixed — forwarding 14 headers including Authorization
- **HTTPS outbound:** Fixed — `native-tls` feature enabled in reqwest
- **Streaming SSE:** Working — Anthropic streaming token extraction confirmed
- **Database:** 2,637 requests tracked (2,621 cliproxy, 14 anthropic, 2 openai)
- **Logging:** Error logging working (eprintln to tokenpulse-error.log)
- **Cargo check:** Clean compile, no warnings
- **Release binary:** Built and current (Mar 27)

### What's Broken/Not Ideal ❌
1. **Dashboard not running** — `com.tokenpulse.dashboard` launchd service crashed with "Address already in use" (EADDRINUSE) and never recovered
2. **OpenClaw not routing through TokenPulse** — Config points directly at CLIProxy (8317), bypassing TokenPulse (4100). This means current usage isn't being tracked.
3. **Dashboard DB path mismatch** — Dashboard Python code defaults to `com.tokenpulse.desktop` but Tauri creates `com.tokenpulse.app`. The actual DB is at `com.tokenpulse.desktop`. Need to verify this is stable.
4. **Only tracking cliproxy** — Because OpenClaw config bypasses TokenPulse, only manual tests go through the proxy. Ryan was right that it only showed Opus 4.6.
5. **Proxy responds 421 to bare GET /** — OpenAI returns "Misdirected Request" when proxy forwards a bare GET to api.openai.com. Should return a friendly health check page instead.
6. **Tauri desktop app running as tray-only** — But the proxy portion works standalone (the release binary). The Tauri window/tray is unnecessary for headless operation.

## Fix Plan

### Phase 1: Get Dashboard Running Again (Quick Fix)
1. Fix the `SO_REUSEADDR` issue in web-dashboard.py — it already sets `allow_reuse_address` but the HTTPServer class doesn't use it. Need to set it before `server_bind`.
2. Restart the dashboard launchd service
3. Verify it loads at http://localhost:4200

### Phase 2: Route OpenClaw Through TokenPulse (Critical)
1. Update `~/.openclaw/openclaw.json` to point at TokenPulse proxy (4100) instead of directly at CLIProxy (8317)
2. Provider `cliproxy` baseUrl: `http://127.0.0.1:8317/v1` → `http://127.0.0.1:4100/cliproxy/v1`
3. Test that OpenClaw requests still work end-to-end
4. Verify requests appear in the dashboard

### Phase 3: Add Health Check Endpoint
1. Add a `GET /` handler that returns a simple JSON or HTML health page instead of forwarding to OpenAI
2. Shows proxy status, uptime, request count

### Phase 4: Verify & Polish
1. Confirm streaming works correctly through the proxy
2. Check that fallback routes also work through TokenPulse
3. Review dashboard for any display issues with the existing data
4. Ensure the proxy gracefully handles connection failures without crashing

### Phase 5: Suggestions for Improvement
- After fixes verified, propose UI/UX improvements
- Consider adding a `/health` API endpoint for monitoring
- Evaluate whether Ollama traffic should also route through TokenPulse
