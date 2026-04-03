# TokenPulse Roadmap & Vision Doc
**Date:** 2026-04-02
**Author:** Shaka (synthesized from Codex audit + market research)

---

## Vision

TokenPulse is the **unified command center for hybrid AI setups** — the single dashboard where you see every token, every dollar, every model, cloud and local, in one place. No other tool does this well.

The hybrid AI wave is accelerating. Google just released Gemma 4 under Apache 2.0 (2B/8B/27B). Matthew Berman and others are calling hybrid local+cloud the future of AI. People are running Ollama, llama.cpp, LM Studio alongside Claude, GPT, Gemini APIs — and they have zero visibility into what's actually happening across all of them.

**TokenPulse's unfair advantage:** Real-time proxy interception gives actual per-request token data. Competitors like CostGoat poll billing APIs (delayed, no granularity). Helicone is enterprise/cloud-focused. LiteLLM is a routing layer, not a monitoring product. Nobody owns the "hybrid local + cloud tracking" space yet.

---

## Current State (Honest Assessment)

### What Works
- Proxy on port 4100 intercepting and tracking requests
- 27K+ requests tracked, 4 models, 3 providers
- Streaming support, cost calculation, budget alerts
- Dashboard with heatmaps, CSV export, forecasting
- Fully local SQLite — privacy-first architecture

### What's Broken or Missing (from Codex Audit)

**Critical:**
- Dashboard exposed on all network interfaces with wildcard CORS and no auth
- `/api/notifications` endpoint is broken (undefined variable)

**Architectural:**
- Single global SQLite mutex bottlenecks everything
- 4,300-line monolithic Python dashboard
- Business logic duplicated between Rust and Python (budgets, alerts, forecasting)
- Proxy handler is one giant function (~700 lines)

**Feature Gaps:**
- Only tracks CLIProxy traffic (96% of requests) — Ollama/Codex/direct API not routed through
- Hardcoded provider ports (Ollama:11434, LM Studio:1234, CLIProxy:8317)
- No configurable provider registry for arbitrary endpoints
- Pricing data stale — missing Gemma 4, newer DeepSeek, GPT-5 era models
- No embeddings/image/audio endpoint tracking
- No local model metadata (VRAM, quantization, throughput)

---

## Competitive Landscape

| Product | Type | Local Models | Real-time | Self-hosted | Price |
|---------|------|-------------|-----------|-------------|-------|
| **TokenPulse** | Proxy + Dashboard | ✅ (planned) | ✅ | ✅ | Free/OSS |
| **Helicone** | AI Gateway | ❌ | ✅ | ✅ (OSS) | Free to $500/mo |
| **LiteLLM** | Routing Proxy | Partial | ✅ | ✅ (OSS) | Free/OSS |
| **CostGoat** | Billing Monitor | ❌ | ❌ (polls) | Desktop app | $9/mo |
| **Crossnode** | Agency Tooling | ❌ | Partial | ❌ | TBD |

**Key insight:** Nobody owns hybrid local+cloud tracking. That's the lane.

---

## Roadmap

### Phase 1: Foundation Fix (Priority: NOW)
**Goal:** Make what exists actually solid before adding features.

1. **Dashboard Security** — Bind to localhost, kill wildcard CORS, add local auth token
2. **Fix Dashboard Bugs** — `/api/notifications` crash, double-WHERE SQL bugs, time-range inconsistency across sections
3. **SQLite Architecture** — Replace single mutex with connection pool, add composite indexes, enable busy_timeout
4. **Split Proxy Handler** — Separate internal API routes from forwarding, introduce provider adapter pattern

**Estimated effort:** 1-2 Codex sessions

### Phase 2: True Hybrid Support (Priority: HIGH)
**Goal:** Track ALL model traffic — cloud and local — through one pane of glass.

1. **Configurable Provider Registry** — UI to add any OpenAI-compatible endpoint (not just hardcoded ports)
2. **Route Ollama Traffic** — Configure Ollama to proxy through TokenPulse
3. **Route Codex/Edison Traffic** — Same for OpenAI Codex OAuth traffic
4. **Model Alias Normalization** — `llama3.2:latest`, `qwen3.5:9b`, quantized variants all roll up cleanly
5. **Local vs Cloud Dashboard View** — Side-by-side comparison showing cloud costs vs local "savings"
6. **Local Model Metadata** — Track model size, quantization level, tokens/sec for local models

**Estimated effort:** 2-3 Codex sessions

### Phase 3: Pricing & Provider Refresh (Priority: HIGH)
**Goal:** Accurate, up-to-date cost tracking for the current model landscape.

1. **Refresh pricing.json** — Add Gemma 4, DeepSeek V3/R1, GPT-5 era, Qwen 3, Llama 4, Mistral updates
2. **Auto-update Pricing** — Fetch from LiteLLM's community pricing file or similar source
3. **Pricing Confidence Indicator** — Show users when a cost is exact vs estimated vs unknown
4. **Cache-hit Pricing** — Support Anthropic/DeepSeek cached token discount tiers

**Estimated effort:** 1 Codex session

### Phase 4: Dashboard Overhaul (Priority: MEDIUM)
**Goal:** From "works" to "looks good and is maintainable."

1. **Split Python Monolith** — Separate data access, API handlers, templates into modules
2. **Eliminate Rust/Python Duplication** — Dashboard becomes pure API client over Rust backend
3. **Drill-down Views** — Click into any provider/model for detailed request history
4. **Request Search** — Find specific requests by model, timestamp, token count
5. **Provider Health Dashboard** — Uptime, error rates, latency per provider
6. **Design Pass** — Modern UI, dark mode, responsive layout

**Estimated effort:** 2-3 Codex sessions

### Phase 5: Advanced Features (Priority: FUTURE)
**Goal:** Features that make TokenPulse a must-have for power users.

1. **Smart Routing Suggestions** — "You could save $X/mo by routing short prompts to local Gemma 4 instead of Claude"
2. **Embeddings/Image/Audio Tracking** — Beyond chat completions
3. **Multi-machine Support** — Aggregate data from multiple TokenPulse instances
4. **API for External Tools** — Let OpenClaw, scripts, etc. query TokenPulse data
5. **Export to Obsidian** — Weekly/monthly usage reports as vault notes

---

## Revenue Angle

### Open Source Core + Premium Features
- **Free:** Local proxy, basic dashboard, unlimited tracking
- **Premium ($9-19/mo or $99-199 lifetime):**
  - Cloud sync between machines
  - Team/org dashboards
  - Advanced analytics and forecasting
  - Priority pricing updates
  - Slack/Discord alerts

### Gumroad Quick Win
- Package current state as "TokenPulse Early Access" — $19-29
- Target: AI power users, OpenClaw users, local model enthusiasts
- Update cadence: monthly releases through the roadmap phases

---

## Inspiration & Research Sources

- **Helicone** (helicone.ai) — OSS AI gateway, good dashboard UX reference
- **LiteLLM** (litellm.ai) — Provider adapter pattern, pricing database
- **CostGoat** — Validates the market, but polling approach is fundamentally weaker
- **Crossnode** — Agency billing angle worth watching
- **Reddit r/ExperiencedDevs, r/sysadmin** — Real pain points around AI cost tracking and FinOps
- **Matthew Berman** — Hybrid setup advocacy, large audience validation
- **Gemma 4 release** — Perfect timing for local model tracking features

---

## Next Action

Ryan picks a starting point. My recommendation: **Phase 1 first** (security + stability), then jump straight to **Phase 2** (hybrid support) — that's the differentiator. Codex can handle both.
