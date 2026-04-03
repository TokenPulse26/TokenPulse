# TokenPulse Deep Audit

Date: 2026-04-02

Scope reviewed:
- Rust proxy / Tauri app: `src-tauri/src/proxy.rs`, `src-tauri/src/db.rs`, `src-tauri/src/lib.rs`, `src-tauri/src/pricing.rs`
- Bundled pricing data: `src-tauri/pricing.json`
- Python dashboard: `web-dashboard.py`
- Repo docs for expected behavior: `README.md`, `GETTING_STARTED.md`

Validation run:
- `cargo check` in `src-tauri`: passed
- `cargo clippy --all-targets -- -W clippy::unwrap_used -W clippy::expect_used`: passed with many warnings
- `python3 -m py_compile web-dashboard.py`: passed

## Executive Summary

The project is functional, but it has three major design problems:

- The Python dashboard is exposed on all interfaces with wildcard CORS and unauthenticated write endpoints. That is the most serious issue.
- The data layer is bottlenecked by a single global `Arc<Mutex<rusqlite::Connection>>`, while analytics and tray tasks run frequent heavy queries against that same lock.
- Business logic is duplicated between Rust and Python for budgets, reliability, notifications, and forecasting. That duplication is already causing correctness bugs and drift.

The codebase also has a large monolithic proxy handler, stale bundled model pricing, and several user-visible dashboard defects that are masked by broad `except Exception` blocks.

## Findings

### Critical

- `web-dashboard.py:4346-4359`, `web-dashboard.py:3985-3991`, `web-dashboard.py:4259-4328`
  The dashboard binds to `("::", 4200)`, which exposes it on all network interfaces, not just localhost. Its JSON responses set `Access-Control-Allow-Origin: *`, and it exposes unauthenticated mutating endpoints for budgets (`POST /api/budgets`, `PUT /api/budgets/*`, `DELETE /api/budgets/*`). On any machine where port `4200` is reachable from another host, any website or LAN peer can drive those endpoints. This is the top security issue.

- `web-dashboard.py:4208-4210`
  `/api/notifications` is broken. It reads `query.get(...)`, but `query` is never defined in `do_GET`. This should raise `NameError` on first request and makes the endpoint nonfunctional.

### High

- `src-tauri/src/proxy.rs:25-30`, `src-tauri/src/lib.rs:14`, `src-tauri/src/lib.rs:381-457`, `src-tauri/src/lib.rs:485-489`, `src-tauri/src/lib.rs:619-645`
  The entire app shares one SQLite connection behind a global `Mutex`. Every Tauri command, every proxy write, every pricing refresh, and every 30-second tray polling loop serializes through the same lock. This is the main architectural bottleneck and will hurt throughput once request volume rises or the dashboard issues heavier analytics queries.

- `src-tauri/src/proxy.rs:377-1104`
  `proxy_handler` is too large and mixes routing, origin policy, provider detection, request rewriting, streaming parsing, error logging, metrics extraction, and response shaping in one function. That structure is already producing repeated response-builder boilerplate, repeated DB insert paths, and brittle provider-specific conditionals. It is not cleanly decomposed for adding more providers or non-chat endpoints.

- `web-dashboard.py:1108-1114`, `web-dashboard.py:1337-1386`, `web-dashboard.py:1517-1650`, `web-dashboard.py:4055-4129`
  The dashboard duplicates backend logic instead of consuming one authoritative API. Budget status, forecasts, notifications, reliability anomaly logic, and budget mutations all exist in Python even though equivalent Rust/SQLite logic already exists in `src-tauri/src/db.rs`. This duplication is an architectural drift risk and has already led to correctness bugs and inconsistent fallback behavior.

- `src-tauri/src/db.rs:203-206`, `src-tauri/src/db.rs:647-663`, `src-tauri/src/db.rs:804-842`, `src-tauri/src/db.rs:950-957`, `src-tauri/src/db.rs:1180-1186`, `src-tauri/src/db.rs:1432-1513`
  The schema is under-indexed for the actual query mix. There are only single-column indexes on `requests(timestamp)`, `requests(provider)`, `requests(model)`, and `requests(source_tag)`. The hot analytics queries filter by combinations like timestamp + provider type, timestamp + provider + model, budget alert lookups by `budget_id/resolved_at`, and notification polling by `delivered_at/resolved_at`. Large datasets will degrade into repeated scans.

- `web-dashboard.py:1025-1043`
  Two insight queries are invalid when a time range is active: `FROM requests{where} WHERE latency_ms IS NOT NULL` and `FROM requests{where} WHERE is_streaming=1`. When `where` already contains `WHERE ...`, SQLite throws a syntax error. The surrounding broad `try/except` suppresses the failure, so `avg_latency_ms` and `stream_pct` silently disappear or stay zero.

- `web-dashboard.py:4185-4372`
  The dashboard runs on `HTTPServer`, not a threaded or async server. A slow page render, CSV export, or slow SQLite read blocks every other request. That is a poor fit for a “live” dashboard with periodic browser fetches and write endpoints.

- `src-tauri/src/pricing.rs:30-45`
  Cost matching uses fallback substring matching if exact lookup misses. That is convenient for local aliases like `llama3.2:latest`, but it is also unsafe for model families with overlapping names or provider aliases. Mispricing becomes more likely as the number of supported models grows.

- `src-tauri/src/proxy.rs:141-229`
  Usage extraction is narrowly tailored to chat-style response bodies. There is no explicit handling for embeddings, image/audio endpoints, rerank/classification APIs, or provider-specific batch responses. A user would reasonably expect a token/cost tracker to cover more than chat completions, especially in hybrid local + cloud setups.

### Medium

- `src-tauri/src/proxy.rs:52-62`, `src-tauri/src/proxy.rs:76-80`
  Local/self-hosted provider support is hardcoded to fixed ports and one-off routes: Ollama at `11434`, LM Studio at `1234`, CLIProxy at `8317`. There is no configurable provider registry, no custom OpenAI-compatible upstream list, and no per-project routing policy. For hybrid AI workflows, users will expect configurable cloud and self-hosted targets.

- `src-tauri/src/proxy.rs:720-728`
  The proxy injects `stream_options: { include_usage: true }` into all streaming OpenAI-compatible requests except Anthropic/Google/Ollama. That assumes downstream compatibility and may break providers that emulate OpenAI partially but reject unknown request fields.

- `src-tauri/src/proxy.rs:704-707`, `src-tauri/src/proxy.rs:1040-1103`
  Non-streaming requests and responses are fully buffered in memory. Request bodies are capped at 10 MB, but responses are not capped before buffering. For image/audio/multimodal endpoints or unusually large JSON payloads, this becomes a memory and latency issue.

- `src-tauri/src/proxy.rs:873-1025`
  Streaming accounting is best-effort only. It relies on parsing SSE `data:` lines and a final usage-bearing chunk. If the provider streams in a different shape, compresses frames differently, or omits usage on the terminal event, TokenPulse records partial or zero usage. This is especially fragile for expanding provider support.

- `src-tauri/src/db.rs:161-162`
  WAL mode is enabled, but there is no `busy_timeout`, no explicit foreign key enablement, and no DB-side tuning beyond that. With one shared connection this is partly masked, but as soon as the architecture improves, the DB initialization is still incomplete.

- `src-tauri/src/db.rs:220-228`, `src-tauri/src/db.rs:230-247`
  Budget alert and notification tables lack supporting indexes for their most common access paths. Examples: active alert lookup uses `budget_id` and `resolved_at`; undelivered notification polling uses `delivered_at IS NULL AND resolved_at IS NULL`; dedupe resolution scans `dedupe_key LIKE ...`. Those paths should be indexed explicitly.

- `src-tauri/src/db.rs:1388-1605`
  Reliability anomaly detection ignores the selected dashboard range for its recent/baseline windows; it always evaluates “last 24h vs previous 7 days”. That is defensible analytically, but the `/api/reliability?range=...` surface suggests the range should affect anomalies too. Current behavior is surprising.

- `web-dashboard.py:1389-1410`, `web-dashboard.py:3914-3915`
  Project breakdown ignores the selected time range entirely. The rest of the dashboard is range-aware, but the project cards always read all-time data.

- `web-dashboard.py:1413-1481`, `web-dashboard.py:1741-1857`, `web-dashboard.py:3911-3912`
  Forecasting and optimizer sections also ignore the active time range and use fixed windows. That makes the UI internally inconsistent and harder to trust.

- `web-dashboard.py:763-1058`, `web-dashboard.py:1322-1857`
  The dashboard uses many broad `except Exception:` blocks to hide query or schema issues. This keeps the page alive, but it also masks real correctness defects and makes regressions hard to notice.

- `src-tauri/src/lib.rs:325-367`
  Pricing refresh performs one `upsert_pricing` call per entry while holding the shared DB mutex. For a larger LiteLLM file this becomes a long serialized write window. A transaction or bulk insert path would be better.

- `src-tauri/src/lib.rs:473-481`, `src-tauri/src/lib.rs:554`, `src-tauri/src/lib.rs:587`, `src-tauri/src/proxy.rs:1112-1115`
  Production code still uses `expect()`/`unwrap()` on startup paths and response builders. Most of these are unlikely to fail during normal operation, but they are still process-kill points in desktop code. Clippy confirms this.

- `src-tauri/src/proxy.rs:412-418`
  The health endpoint returns hardcoded metadata (`version: "0.2.0"`, `dashboard_url: "http://localhost:4200"`). That can drift from the actual app version and runtime configuration.

### Low

- `src-tauri/src/db.rs:1634-1972`
  There are tests for `db.rs`, but there are no corresponding tests for the proxy handler or the Python dashboard. The highest-risk surfaces currently have the weakest test coverage.

- `src-tauri/src/lib.rs:401-423`, `src-tauri/src/db.rs:898-924`
  `update_budget` and related command surfaces are too argument-heavy. They should use a request struct to make API evolution safer and clearer.

- `src-tauri/src/proxy.rs:536-693`
  Several internal API endpoints always respond with HTTP 200 even when the JSON payload says `"status": "error"`. That makes monitoring, scripting, and browser-side failure handling worse than necessary.

## Code Quality Notes

### `unwrap()` / `expect()` inventory

Production-path panic points found:

- `src-tauri/src/proxy.rs:322`
- `src-tauri/src/proxy.rs:423-424`
- `src-tauri/src/proxy.rs:539-540`
- `src-tauri/src/proxy.rs:584-585`
- `src-tauri/src/proxy.rs:619-620`
- `src-tauri/src/proxy.rs:650-651`
- `src-tauri/src/proxy.rs:671-672`
- `src-tauri/src/proxy.rs:692-693`
- `src-tauri/src/proxy.rs:861`
- `src-tauri/src/proxy.rs:1038`
- `src-tauri/src/proxy.rs:1103`
- `src-tauri/src/proxy.rs:1112-1115`
- `src-tauri/src/lib.rs:473-481`
- `src-tauri/src/lib.rs:554`
- `src-tauri/src/lib.rs:587`

Most remaining `unwrap()`s reported by clippy are in `db.rs` test code (`src-tauri/src/db.rs:1644-1966`).

### Dead code / drift

- `web-dashboard.py:23-32`
  `_fetch_proxy_json()` is used, but its existence is a symptom of the bigger issue: the dashboard is half API client and half direct-SQL app. The codebase would be cleaner if it committed to one model.

- `web-dashboard.py:1218-1318`, `src-tauri/src/db.rs:1005-1054`, `src-tauri/src/db.rs:1212-1256`
  Budget alert synchronization exists in both Python and Rust. That is not dead code yet, but it is duplicated code that will drift.

## Architecture Assessment

### Proxy structure

`src-tauri/src/proxy.rs` works, but it is not cleanly structured enough for continued provider growth.

Main issues:
- Provider detection is heuristic and scattered (`src-tauri/src/proxy.rs:38-139`).
- Routing, metrics extraction, and persistence all happen in `proxy_handler` (`src-tauri/src/proxy.rs:377-1104`).
- Streaming and non-streaming logging paths are largely duplicated (`src-tauri/src/proxy.rs:820-1103`).
- Internal API endpoints are embedded into the same fallback handler as the forward proxy (`src-tauri/src/proxy.rs:401-694`).

Recommended direction:
- Split internal analytics routes from the forwarding proxy router.
- Introduce provider adapters with traits or per-provider modules for path rewriting, request mutation, and usage extraction.
- Move persistence into a small service layer instead of hand-constructing `RequestRecord` in many branches.

### DB schema

Good:
- Basic normalization is acceptable for a local analytics tool.
- `pricing` uses a composite primary key on `(model, provider)`.
- WAL mode is enabled.

Weak points:
- Too few composite indexes for the actual query shape.
- `timestamp` is stored as `TEXT`, then repeatedly wrapped in `date(...)`/`datetime(...)` expressions, which limits index usefulness for grouped analytics.
- Notification and budget-alert lookup paths are under-indexed.
- Foreign key behavior is not explicitly enabled.

## Security Assessment

### API key handling

Good:
- The proxy forwards original auth headers without persisting them.
- Logging only reports whether auth headers are present, not their values (`src-tauri/src/proxy.rs:756-760`).

Risks:
- The local dashboard is network-exposed and cross-origin writable, which is a much larger problem than key storage.
- The app checks for updates and pricing over the network at startup (`src-tauri/src/lib.rs:325-367`, `src-tauri/src/lib.rs:258-295`). That is expected, but there is no explicit integrity verification beyond HTTPS.

### Injection risks

Good:
- Most SQL writes are parameterized.
- Dynamic SQL fragments are mostly built from closed enums or sanitized values (`time_range`, `scope_kind`, bounded limits).

Residual concern:
- The dashboard’s heavy use of formatted SQL strings makes future mistakes likely, and the double-`WHERE` bugs show the pattern is already brittle.

### CORS / local exposure

Proxy:
- Reasonable for `/api/*`: it only accepts local dashboard origin `localhost:4200` / `127.0.0.1:4200` over HTTP/HTTPS (`src-tauri/src/proxy.rs:271-333`).

Dashboard:
- Not acceptable: wildcard CORS on a server bound to all interfaces, with write endpoints and no auth.

## Missing Features Users Will Expect

### Hybrid local + cloud workflows

Likely user expectations not currently met:

- Configurable upstream registry for arbitrary OpenAI-compatible hosts, not just hardcoded Ollama/LM Studio/CLIProxy ports (`src-tauri/src/proxy.rs:52-80`).
- Cloud/local fallback routing rules and failover suggestions that can actually route traffic, not just dashboard recommendations.
- Per-project routing policies such as “prefer local for short prompts, cloud for long prompts”.
- Provider/model alias normalization so `llama3.2:latest`, quantized local models, and cloud snapshots roll up cleanly.
- Cost accounting for cached-token discounts, prompt-cache hit rates, and provider-specific reasoning-token pricing beyond a few exposed fields.
- Coverage for embeddings, image generation, audio transcription/speech, and batch APIs.
- Better local-model metadata: model size, quantization, hardware used, VRAM pressure, and throughput by machine.

## Provider Support Review

### What `pricing.json` currently covers

`src-tauri/pricing.json:1-60` contains 58 bundled entries across:

- OpenAI: GPT-4o, GPT-4.1 family, GPT-4 Turbo, GPT-3.5 Turbo, `o1`, `o1-mini`, `o3-mini`, `o4-mini`
- Anthropic: Claude 3, 3.5, 4.5, 4.6 variants
- Google: Gemini 1.5, 2.0, 2.5
- Mistral: Large/Medium/Small/Nemo/Codestral variants
- Groq: Llama 3.1/3.3, Mixtral 8x7B, Gemma 2 9B
- Meta: Llama 3.1/3.2/3.3
- DeepSeek: `deepseek-chat`, `deepseek-reasoner`
- Ollama: a few generic local aliases
- LM Studio: one generic `local` entry

### Major gaps / stale areas

Based on the bundled file and current mainstream provider families as of 2026-04-02:

- OpenAI missing newer flagship families such as GPT-5-era entries and open-weight `gpt-oss` variants. The file is still centered on GPT-4.1 / `o1` / `o3-mini` / `o4-mini`.
- Anthropic lacks modern API snapshot names for Claude 4 family models. The file uses friendly aliases like `claude-opus-4-6` rather than current API IDs, which makes exact matching brittle.
- Google Gemma open-model families are effectively absent from bundled pricing. There is only Groq `gemma2-9b-it` and Ollama `gemma2`; no bundled Gemma 3 / Gemma 3n family coverage.
- DeepSeek coverage is too thin: only two models. No newer DeepSeek V3.x / R1-era naming variants, and no distinction for cache-hit pricing tiers.
- Groq coverage is stale and narrow. It lacks more recent Groq-hosted families such as GPT-OSS, newer Qwen/Kimi/Llama variants, and other current hosted open models.
- Mistral coverage is missing newer family names and aliases that users are likely to see in current APIs.
- LM Studio support is effectively nonexistent from a pricing perspective; everything collapses to a single `local` placeholder.
- Ollama coverage is generic and insufficient for real-world local setups. Modern local model families such as Gemma 3, Qwen 3, Llama 4, DeepSeek local variants, and tool-specific tags are not bundled.

### Pricing correctness concerns

- `src-tauri/pricing.json:50-51`
  DeepSeek pricing looks stale. The bundled values are unlikely to match current published pricing structure, especially if cache-hit or newer model tiers matter.

- `src-tauri/pricing.json:4-6`
  OpenAI context windows are stored as `1047576`, which is likely a typo for `1048576`.

- `src-tauri/pricing.json:52-59`
  Local model pricing is all zero with minimal model coverage. That is acceptable as a placeholder, but users should not confuse it with complete local-model support.

## Dashboard Assessment

### Structure

`web-dashboard.py` is productive but overgrown:

- One file, ~4.3k lines
- HTML template, CSS, JS, SQL, API handlers, budget mutations, and analytics all mixed together
- No tests
- Broad exception swallowing

The UI generation is surprisingly polished, but the implementation is difficult to maintain. A small module split would already help:

- data access
- API handlers
- page composition
- HTML/CSS/JS templates

### UI / UX gaps

- The page looks rich, but not all sections honor the active range filter (`web-dashboard.py:3898-3915`).
- There is no drill-down for provider snapshots, request search, model search, or filtering beyond broad time windows.
- No explicit indication when a section is using fallback SQL instead of the proxy API.
- No explanation of whether a cost is exact, estimated, stale, or missing due to missing pricing coverage.
- No surface for provider config, upstream health, or local-model endpoint configuration.
- No per-project or per-provider comparison view tailored to hybrid local+cloud routing decisions.

## Performance Assessment

Top issues:

- Single shared SQLite mutex is the main bottleneck.
- Dashboard server is single-threaded.
- Analytics queries repeatedly scan `requests` with few composite indexes.
- Tray background loop runs expensive analytics every 30 seconds while holding the same DB lock (`src-tauri/src/lib.rs:619-645`).
- Pricing refresh upserts one row at a time while holding the DB lock (`src-tauri/src/lib.rs:349-365`).
- Proxy buffers non-streaming bodies and responses entirely in memory (`src-tauri/src/proxy.rs:704-707`, `src-tauri/src/proxy.rs:1040-1103`).

## Recommended Remediation Order

1. Lock down the dashboard server.
   - Bind it to localhost only.
   - Remove wildcard CORS.
   - Reject cross-origin writes or add a local CSRF token.

2. Fix the known dashboard correctness bugs.
   - `/api/notifications` undefined variable.
   - Double-`WHERE` insight queries.
   - Time-range consistency for projects/forecast/optimizer.

3. Replace the single global SQLite connection.
   - Use a small connection pool or at least separate read/write connections.
   - Add `busy_timeout`, enable foreign keys, and add composite indexes.

4. Split `proxy_handler`.
   - Separate internal API routes from forwarding routes.
   - Move provider-specific logic behind a provider adapter abstraction.

5. Eliminate duplicated Python business logic.
   - Make the dashboard an API client over the Rust backend, or fully move dashboard data logic into Rust endpoints.

6. Refresh bundled pricing and improve normalization.
   - Add current model families.
   - Normalize aliases and snapshot IDs.
   - Distinguish exact pricing from heuristic matches.

## Bottom Line

TokenPulse has a solid product idea and a workable local-first foundation, but it is at the point where the current “single file / single handler / single DB mutex” approach is limiting correctness, security, and scale.

If only one thing is fixed immediately, it should be the dashboard exposure problem in `web-dashboard.py`. If two more things are fixed next, they should be the global SQLite lock architecture and the Rust/Python logic duplication.
