# TokenPulse Dashboard Cleanup Spec

## Problem
The dashboard (web-dashboard.py, 5511 lines) has grown organically and is now information-dense but not information-clear. Too many sections compete for attention, unknown/ghost entries clutter the data, and it's hard to quickly answer "how much am I spending and where?"

## Design Philosophy
- **Signal over noise.** If a section doesn't help the user make a decision, it should be hidden or collapsed.
- **Hierarchy matters.** The most important info (spending, active models, health) should be immediately visible. Deep dives should be opt-in.
- **Clean, not empty.** Don't remove features — reorganize them. Power users should still find everything, just not all at once.
- **Visual reference:** The TokenPulse marketing site (`../tokenpulse-site/index.html`) is clean, readable, well-spaced. Match that energy in the dashboard.

---

## Current Layout (13+ sections, all visible at once)

1. Activity timeline (live feed)
2. Stat cards (summary numbers)  
3. Attention Center
4. Budget + Spending Forecast (side by side)
5. Cost Optimizer + Reliability (side by side)
6. Context Audit
7. Project/Source Breakdown
8. Daily Spend chart + Model Breakdown chart
9. Error Monitor
10. Activity Heatmap + Insights (side by side)
11. Recent Requests table

## Proposed Layout (tiered)

### Tier 1: Always Visible — "The Glance"
These answer: "How much am I spending, where, and is anything broken?"

1. **Stat Cards** (keep, but clean up)
   - Total Spend, Total Requests, Avg Cost/Request, Active Models
   - REMOVE: any stat card showing $0 or models with 0 requests
   
2. **Provider/Model Summary** (NEW — replaces the cluttered model breakdown)
   - Clean card grid: one card per ACTIVE provider+model combo
   - Show: model name, request count, total tokens, cost, last used
   - Color-coded by provider (Opus=purple, GPT-5.4=green, Grok=blue, Qwen=orange, Ollama=gray)
   - HIDE models with 0 requests in the selected time range
   - HIDE "unidentified model" entries — or collapse them into a single "Unattributed" row at the bottom
   
3. **Daily Spend Chart** (keep, make prominent)

### Tier 2: Collapsible — "The Details"  
These are useful but shouldn't compete with Tier 1. Each should be a collapsible section, closed by default, with a summary line visible.

4. **Budget & Forecast** (collapse into one section)
   - Summary line when collapsed: "Monthly budget: $X used of $Y (Z%)"
   - Expand for full budget cards and forecast chart

5. **Attention Center** (collapse)
   - Summary line: "2 items need attention" or "All clear"
   - Expand for details

6. **Cost Optimizer** (collapse)
   - Summary line: "Potential savings: $X/mo"
   - Expand for recommendations

7. **Context Audit** (collapse)
   - Summary line: "Audit score: X/100" or "Run audit"
   - Include the audit trigger button Ryan asked for right in the summary line

### Tier 3: Bottom Section — "The Logs"
For power users who want to dig into raw data.

8. **Recent Requests** (keep at bottom, paginated)

9. **Activity Heatmap** (keep, move to bottom)

10. **Error Monitor** (keep, but only show if there ARE errors, otherwise hide entirely)

11. **Reliability & Latency** (collapse, only show if there are issues)

12. **Insights** (collapse)

### REMOVE entirely:
- **Activity Timeline** (live feed at top) — it's noisy and duplicates the requests table. If keeping it, make it a collapsed section.
- **By Source breakdown** — the source tags are confusing ("Python SDK", "notstkI", etc.). Replace with the clean Provider/Model Summary in Tier 1.
- **"By Project" breakdown** — source_tag data is mostly junk ("unattributed"). Remove until source tagging actually works properly.

---

## Specific Fixes

### Ghost/Noise Cleanup
1. **Filter out models with 0 requests** in the selected time range from all views
2. **Filter out "unknown" / "unidentified" models** — or group them into a single "Other" row
3. **Filter out providers with 0 requests** from the provider list
4. **Clean up source labels** — the `_normalize_source_label` function generates confusing labels. Simplify to: provider name + model name, nothing else
5. **Remove stale MODEL_COSTS and DOWNGRADE_MAP entries** for models Ryan doesn't use (gpt-4o, gpt-4o-mini, gpt-4.1, etc.)

### Provider Colors Update
Add colors for the new providers:
```python
PROVIDER_COLORS = {
    "openai": "#10a37f",
    "openai-codex": "#10a37f",  # same green, GPT family
    "anthropic": "#d4a574",
    "cliproxy": "#d4a574",      # Opus through CLIProxy
    "openrouter": "#6366f1",    # indigo for OpenRouter
    "google": "#4285f4",
    "ollama": "#94a3b8",        # muted gray for local
    "groq": "#f55036",
    "mistral": "#ff7000",
    "lmstudio": "#8b5cf6",
}
```

### Collapsible Sections
Add a simple JS toggle pattern:
- Each collapsible section has a header with a summary line + chevron
- Click to expand/collapse
- State saved in localStorage so preferences persist
- Default state: collapsed for Tier 2, expanded for Tier 1

### Audit Button
Add a "Run Audit" button in the Context Audit section header. When clicked, triggers the existing `/api/context-audit` endpoint and refreshes the section. This was requested but not implemented.

---

## File Structure
- All changes are in `web-dashboard.py` (single-file dashboard)
- The marketing site at `../tokenpulse-site/index.html` is reference only — don't modify it
- CSS is inline in the `PAGE_TEMPLATE` string
- JS is built in `_build_page_scripts()` 

## Testing
After changes:
1. Restart dashboard: `launchctl unload ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist && launchctl load ~/Library/LaunchAgents/com.tokenpulse.dashboard.plist`
2. Verify at `http://10.0.0.137:4200`
3. Check all time ranges work (today, 7d, 30d, all)
4. Verify collapsible sections save state
5. Verify ghost models/providers are filtered out
