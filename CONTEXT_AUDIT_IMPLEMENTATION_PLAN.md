# TokenPulse Context Audit v2 — Implementation Plan

Date: 2026-04-04
Author: Shaka

## Goal
Turn the current Context Audit feature from a useful heuristic panel into a more credible decision-support system for identifying likely wasteful token spending, routing inefficiencies, and context hygiene problems.

## Current v1 strengths
- Detects likely waste patterns using real request data
- Surfaces score, estimated savings, findings, and recommendations
- Good product direction: moves TokenPulse beyond passive charts into action-oriented guidance

## Current v1 weaknesses
- Score model is naive fixed-penalty math
- Estimated savings numbers appear more precise than they are
- Findings mix true waste with optimization opportunities
- No confidence levels
- No drill-down path from finding to underlying requests
- Wording is too certain for heuristic logic

## v2 design goals
1. Increase user trust
2. Make findings more actionable
3. Separate "real waste" from "optimization opportunity"
4. Preserve simplicity — still readable at a glance
5. Avoid pretending heuristics are hard truth

---

## Product / UX Changes

### 1. Rename mental model
Keep section title as **Context Audit** for now, but restructure findings into two buckets:

- **Waste Signals** — money likely burned with little/no value
  - failed paid requests
  - repeated huge prompts with tiny outputs
  - obvious cache misses on repeated heavy context

- **Optimization Opportunities** — probably valid work, but could be routed cheaper or prepared better
  - premium model used on small/simple tasks
  - lightweight API work that may fit local/budget models

This distinction is important. Users trust the panel more when not everything is labeled “waste.”

### 2. Add confidence levels
Each finding gets:
- `high`
- `medium`
- `low`

Confidence should be shown visually in the UI and included in API payloads.

### 3. Change wording
Replace hard-sounding wording with honest wording:
- "likely waste"
- "possible downgrade candidate"
- "heuristic estimate"
- "candidate for local/budget routing"

### 4. Add drill-down links / filters
Each finding should expose a clickable filter link that narrows recent requests to matching candidates.

Initial implementation can be simple:
- finding emits a `filter_hint`
- clicking it loads recent requests filtered by relevant model / request pattern / error state

If true drill-down is too much for one pass, at minimum expose:
- matching request count
- top affected model
- top affected provider

### 5. Improve summary cards
Replace current generic summary with:
- **Audit Score**
- **Likely Recoverable Spend** (not “Estimated Savings”)
- **High-confidence findings**

This makes the top of the section more credible.

---

## Backend Changes (Rust / db.rs)

### Data model updates
Extend `ContextAuditFinding` with:
- `category: String` (`waste` | `opportunity`)
- `confidence: String` (`high` | `medium` | `low`)
- `top_model: Option<String>`
- `top_provider: Option<String>`
- `filter_hint: Option<String>`
- `impact_label: String` (e.g. `heuristic`, `direct`, `partial`)

Extend `ContextAuditSnapshot` with:
- `high_confidence_count: i64`
- `waste_findings_count: i64`
- `opportunity_findings_count: i64`

### Score model v2
Replace fixed severity subtraction with weighted scoring.

Start from 100.
For each finding, compute penalty using:
- severity weight
- confidence weight
- normalized cost impact
- normalized affected request count

Suggested weights:
- severity: high=1.0, medium=0.6, low=0.3
- confidence: high=1.0, medium=0.7, low=0.45
- cost factor: cap at 20 points
- volume factor: cap at 10 points

Suggested formula per finding:
penalty = min(25, (severity_weight * confidence_weight * (cost_factor + volume_factor)))

Where:
- `cost_factor = min(20, estimated_cost_impact_usd * 4)`
- `volume_factor = min(10, requests / 4)`

Clamp total score to 0–100.

### Confidence rules

#### Failed requests
- confidence: **high**
- category: `waste`
- impact label: `direct`

#### Overprompting
Criteria currently: input > 2000 and output < 100
Improve with:
- high confidence if input > 4000 and output < 80 and count >= 5
- medium if input > 2500 and output < 120
- low otherwise
Category: `waste`
Impact label: `partial`

#### Cache underuse
Current rule: input >= 4000 and cached_tokens == 0
Confidence:
- high if repeated pattern count >= 8 and same model/provider dominate
- medium if count >= 4
- low otherwise
Category: `waste`
Impact label: `partial`

#### Premium small tasks
Current rule: premium models with <=1200 total tokens
Confidence:
- medium at best, never high in v2
- low if request count is small
Category: `opportunity`
Impact label: `heuristic`

#### Local model opportunity
Current rule: API requests <500 tokens and count >=10
Confidence:
- low by default
- medium only if models are repeatedly budgetable and no high-error rate / low-latency need inferred
Category: `opportunity`
Impact label: `heuristic`

### Top model/provider extraction
For each finding query, also fetch the top affected model and provider by count.
Include those in the response.

### Recoverable spend wording
Rename API field internally or at least surface label in UI as:
- `likely_recoverable_spend_usd`
If you keep JSON field as `estimated_savings_usd` for compatibility, update the UI label only.

---

## Frontend Changes (web-dashboard.py)

### Section structure
Context Audit should render:
1. Summary cards
2. Verdict banner
3. **Waste Signals** group
4. **Optimization Opportunities** group

### Finding card layout
Each finding card should show:
- title
- category badge
- severity badge
- confidence badge
- affected request count
- likely impact
- top model / provider
- short summary
- recommendation
- optional drill-down/filter hint

### Badge styles
Add new visual badges:
- category badge: red/orange for waste, blue/purple for opportunity
- confidence badge: solid for high, muted for medium, faint for low
- impact label badge: direct / partial / heuristic

### Summary wording changes
Replace:
- “Estimated Savings” → “Likely Recoverable Spend”
- “Findings” → “Audit Findings”

Add:
- “High-confidence findings” count

### Empty state
If no findings:
- keep current clean-state message
- add note that audit uses heuristic patterns and improves with more tracked traffic

### Optional small enhancement
If top model/provider exists, render a tiny meta row:
- `Most affected: claude-opus-4-6 via cliproxy`

---

## Implementation Order

### Phase A — backend credibility
1. Extend Rust structs
2. Upgrade heuristic queries to compute confidence/category/top model/top provider
3. Replace score formula
4. Return new fields through API

### Phase B — UI credibility
1. Split findings into waste vs opportunity groups
2. Add confidence/category badges
3. Rename labels for honesty
4. Add top model/provider metadata
5. Add filter hint text or light drill-down affordance

### Phase C — sanity check
1. Compile Rust/Tauri code
2. Compile dashboard Python
3. Verify `/api/context-audit?range=today`
4. Load dashboard and confirm section renders with both empty and populated states

---

## Constraints
- Do not rewrite the whole dashboard
- Preserve current design language
- Keep the feature explainable to non-technical users
- Prefer honest heuristics over fake precision
- Avoid introducing expensive queries that will noticeably slow the dashboard

---

## Success Criteria
This v2 is successful if:
- findings feel more credible
- the score feels less arbitrary
- users can distinguish actual waste from cheaper-routing opportunities
- UI language sounds confident but honest
- the panel helps a user decide what to trim, reroute, or stabilize next
