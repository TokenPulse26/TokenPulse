# Release Tester Runbook (Post-PR #5)

Use this runbook for a small first-tester release validation on **macOS Apple Silicon**.

## Preconditions
- You are testing from a clean machine/user profile when noted.
- You can access the TokenPulse GitHub repo and Releases page.
- You have at least one provider key available for route checks.

## Required Validation Order

1. **Confirm `VERSION` / `Cargo.toml` / `tauri.conf.json` all match**
   - Check `VERSION`:
     ```bash
     cat VERSION
     ```
   - Check Rust package version:
     ```bash
     rg '^version\s*=\s*"' src-tauri/Cargo.toml
     ```
   - Check Tauri version fields:
     ```bash
     rg '"version"\s*:' src-tauri/tauri.conf.json
     ```

2. **Confirm `install.sh` one-command install**
   - Run:
     ```bash
     curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
     ```

3. **Confirm latest GitHub Release asset exists**
   - Verify release assets include:
     - `tokenpulse-macos-arm64`
     - `tokenpulse-macos-arm64.sha256`
   - Optional API check:
     ```bash
     curl -fsSL https://api.github.com/repos/TokenPulse26/TokenPulse/releases/latest
     ```

4. **Clean macOS Apple Silicon install**
   - On a clean machine/profile, complete install and confirm services come up.
   - Health check:
     ```bash
     curl -sS http://127.0.0.1:4100/health
     ```
   - Dashboard check: open `http://127.0.0.1:4200`.

5. **Run `~/.tokenpulse/agent_verify.py`**
   - Run:
     ```bash
     python3 ~/.tokenpulse/agent_verify.py
     ```

6. **Test OpenAI-compatible route**
   - Base URL: `http://localhost:4100`
   - Send one known test prompt through an OpenAI-compatible client and confirm it appears in dashboard activity.

7. **Test Anthropic route**
   - Base URL: `http://localhost:4100/anthropic`
   - Send one known test prompt through an Anthropic-native client and confirm it appears in dashboard activity.

8. **Test Ollama route if available**
   - Base URL: `http://localhost:4100/ollama`
   - If Ollama is installed/running locally, send one known test prompt and confirm local-model traffic appears in dashboard activity.

9. **Confirm dashboard shows overview/connections/recent requests**
   - Verify the dashboard renders:
     - overview
     - connections
     - recent requests

10. **Run CSV export**
    - Export from dashboard and confirm expected rows/columns are present for the test requests.

11. **Run uninstall**
    - Run:
      ```bash
      ./uninstall.sh
      ```
    - Confirm TokenPulse services/files are removed per script output.

## Go / No-Go
- **Go:** All 11 checks pass in order with no blocker-level issues.
- **No-Go:** Any install failure, missing release asset, route failure, missing dashboard core views, CSV export failure, or uninstall failure.

