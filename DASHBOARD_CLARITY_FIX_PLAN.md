# TokenPulse Dashboard Clarity & Trust Pass — Implementation Plan

Date: 2026-04-04
Author: Shaka

## Goal
Fix the places where the dashboard currently feels vague, misleading, or hard to trust. The target is not just prettier UI — it is clearer decision support.

This pass addresses:
- unclear Attention Center items
- vague error rate / spend-at-risk language
- generic fallback recommendations
- weak Live Activity value
- missing budget approach notifications
- broken / misleading Spending Forecast for subscription-heavy traffic
- generic Cost Optimizer wording
- unknown GPT-5.4 / unknown model display issues
- confusing By Project section
- unclear Error Monitor terminology

---

## Core Principles
1. Prefer plain language over dashboard jargon.
2. Don’t show “unknown” as if it were a real model/project if it’s actually missing metadata or failed traffic.
3. Don’t present subscription traffic as if it were costed API traffic.
4. Recommendations should reflect the actual setup when possible.
5. If a widget isn’t helping, simplify or replace it.

---

## Issue 1 — Attention Center clarity

### Problem
The Attention Center can show “1 thing needs attention” without making the specific issue obvious.

### Fix
- Make every attention card title concrete and self-explanatory.
- Replace abstract titles with issue-first language.

Examples:
- "727 failed OpenAI requests (HTTP 404)"
- "Budget threshold approaching: Monthly API spend at 82%"
- "Latency spike on claude-opus-4-6"

### UI changes
- Add a short “Why this matters” line to each card.
- Add a “What to do next” line in plain language.
- In the summary row, replace vague metrics with clearer labels.

### Implementation notes
- Rework `_build_attention_section()` card text generation.
- Ensure card titles are derived from the actual triggered issue, not a generic severity bucket.

---

## Issue 2 — Error rate / Spend at risk explanation

### Problem
The user doesn’t know what “error rate” or “spend at risk” means.

### Fix
- Change labels to:
  - `Failed Requests` instead of `Error Rate`
  - `Spend tied to failures / instability` instead of `Spend at risk`
- Add explanatory subtitles:
  - Failed Requests: `X of Y requests failed in this range`
  - Spend tied to failures / instability: `Paid traffic already burned on failed requests and unstable providers`

### Implementation notes
- Update labels in Attention Center and Reliability summary areas.
- Prefer counts first, percentages second.

---

## Issue 3 — Opus fallback recommendation is too generic

### Problem
The UI says Opus needs a fallback plan even though the user already has one.

### Fix
- Detect whether multiple viable models/providers already exist in recent traffic.
- If fallbacks are already visible in recent data, soften or replace recommendation.

New examples:
- If fallback exists: `Fallback traffic is visible, but Opus still dominates. Consider confirming failover actually triggers on errors.`
- If no fallback exists: keep stronger warning.

### Implementation notes
- Use provider/model mix from recent data to infer if a fallback lane exists.
- Update `_reliability_recommendation()` in both Rust and Python fallback logic as needed.

---

## Issue 4 — Live Activity is weak / decorative

### Problem
The visualizer doesn’t convey enough information and feels useless.

### Fix options
Preferred:
- Replace dot timeline with a compact mini chart of requests over the last 60 minutes.
- Show:
  - requests last 60 min
  - busiest 5-minute window
  - last request timestamp

Fallback option:
- If a mini-chart is too much for this pass, simplify to a compact summary strip with recent volume metrics and remove the decorative visualizer.

### Implementation notes
- Reuse existing recent activity data if possible.
- If current `activity_60s` data is too thin, query counts per 5-minute bucket over the last hour.

---

## Issue 5 — Budget approach notifications

### Problem
Budgets don’t clearly notify the user before they hit the limit.

### Fix
- Add warning thresholds at 75% and 90%.
- Surface these in the budget cards, notifications, and attention center.
- Add explicit states:
  - Healthy
  - Approaching
  - Critical
  - Over budget

### Implementation notes
- Extend budget status logic in Python and/or Rust snapshot logic.
- If budget alerts table already exists, use it for warning entries too.
- Avoid spamming repeated notifications; dedupe by budget + threshold band.

---

## Issue 6 — Spending Forecast broken for subscription-heavy traffic

### Problem
Forecast only uses `provider_type='api'`, but the main workload is `subscription` traffic via CLIProxy. Result: “waiting for more data” even with lots of real usage.

### Fix
Split forecast into two modes:

### API spend forecast
- only for true paid API traffic with real `cost_usd`

### Usage forecast
- for subscription/local traffic where dollar cost is not meaningful
- show projected:
  - total requests this month
  - total tokens this month
  - busiest day / average day

### UI behavior
- If costable API data exists, show spend forecast.
- If mostly subscription traffic, show usage forecast instead of pretending spend forecast is missing.
- If both exist, show both in a two-part forecast section.

### Implementation notes
- Update `_fetch_forecast_data()` to compute both cost forecast and usage forecast.
- Update `_build_forecast_section()` labels and empty states.

---

## Issue 7 — Cost Optimizer too generic

### Problem
Recommendations feel like placeholders even when based on real data.

### Fix
- Make optimizer recommendations reference actual models/providers/request counts.
- Use stronger evidence from real counts and estimated impact.
- Avoid generic phrasing like “consider a cheaper model” unless it names one.

Example:
- `123 small requests hit claude-opus-4-6. Test routing these to claude-sonnet-4-6 or a local lane first.`

### Implementation notes
- Improve `_build_optimizer_section()` text construction.
- Use top model/provider from the actual optimizer data where possible.

---

## Issue 8 — GPT-5.4 showing as unknown / unknown model clutter

### Problem
"Unknown" is being shown as if it were a real model. The data inspection suggests most of this is failed OpenAI traffic (HTTP 404) where model extraction never succeeded.

### Fix
Two layers:
1. **Presentation fix now**
   - Do not show failed requests with missing model names as top “models” in model breakdown.
   - Label them as `Unidentified failed OpenAI requests` or similar in error-focused areas.

2. **Data capture fix**
   - Improve request model extraction in proxy before forwarding for OpenAI-compatible traffic.
   - If model field is missing but request path/source strongly suggests Codex/GPT-5.4 lane, attempt safer normalization.

### Implementation notes
- Audit `src-tauri/src/proxy.rs` model extraction paths.
- In dashboard sections, filter `model='unknown'` out of normal model ranking unless it has meaningful successful traffic.

---

## Issue 9 — By Project confusion

### Problem
The section calls things “projects” but the data is mostly `source_tag`, which is often empty/unknown.

### Fix
- Rename section to **By Source / Project** or **By Source**.
- Add helper copy: `Uses explicit source tags when available. Falls back to routing source when tags are missing.`
- Fallback grouping rules:
  - `source_tag` if present and non-empty
  - else inferred source label from provider/provider_type/model family
  - examples: `OpenClaw / CLIProxy`, `OpenAI API`, `Anthropic API`

### Implementation notes
- Update `_fetch_project_breakdown()` to normalize unknown/blank source_tag values into readable buckets.
- Update section title and explanatory text.

---

## Issue 10 — Error Monitor clarity

### Problem
Raw `HTTP 404:` is not meaningful to a normal user.

### Fix
Translate error classes into plain English summaries:
- 404 → `Endpoint not found or wrong API path`
- 401 → `Authentication failed / missing API key`
- 421 → `Wrong server or endpoint mismatch`
- unknown other → `Provider returned an error`

### UI improvements
- For each top error, show:
  - plain-language label
  - raw provider/error code in smaller text
  - affected request count
  - likely cause
  - suggested next step

### Implementation notes
- Add a small helper to classify error messages.
- Update `_build_error_section()` rendering.

---

## Issue 11 — Context Audit is good, but can improve slightly

### Goal
Preserve the current feature while improving trust a bit more.

### Fix
- Add one short explainer line under Audit Score:
  - `Higher is cleaner. Lower means more likely waste or routing inefficiency.`
- Surface top affected lane more clearly in summary.
- Keep heuristic wording honest.

---

## Implementation Order

### Phase A — data / truth fixes first
1. Unknown model handling
2. Forecast mode split (API spend vs subscription usage)
3. Source/project normalization
4. Error classification helper
5. Smarter fallback recommendation logic

### Phase B — UI clarity pass
6. Attention Center text rewrite
7. Error/spend labels rewrite
8. Budget approach states and warnings
9. Cost optimizer wording improvements
10. Live Activity simplification/replacement
11. Context Audit small trust polish

### Phase C — validation
- cargo check
- python3 -m py_compile web-dashboard.py
- inspect dashboard endpoints
- spot-check rendered HTML strings for the new copy

---

## Success Criteria
This pass is successful if:
- the dashboard stops making the user ask “what does this mean?”
- unknown models/source buckets are reduced or explained clearly
- forecast becomes useful for subscription-heavy workflows
- errors are understandable in normal language
- attention items clearly state what is wrong and what to do next
