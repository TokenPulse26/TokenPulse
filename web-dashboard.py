#!/usr/bin/env python3
"""TokenPulse Web Dashboard v0.2.0 — full-featured analytics dashboard."""
import sqlite3
import os
import json
import math
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from string import Template

DB_PATH = os.environ.get(
    "TOKENPULSE_DB",
    os.path.expanduser(
        "~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db"
    ),
)
VERSION = "0.3.0"

# ─── Cost Optimization constants ──────────────────────────────────────────────
MODEL_COSTS = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "tier": "premium"},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "tier": "mid"},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.0, "tier": "budget"},
    "gpt-4o": {"input": 2.50, "output": 10.0, "tier": "mid"},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "tier": "budget"},
    "gpt-4.1": {"input": 2.0, "output": 8.0, "tier": "mid"},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "tier": "budget"},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40, "tier": "budget"},
}
DOWNGRADE_MAP = {
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4-6": "claude-haiku-3-5",
    "gpt-4o": "gpt-4o-mini",
    "gpt-4.1": "gpt-4.1-mini",
    "gpt-4.1-mini": "gpt-4.1-nano",
}

# Project tag colors for the "By Project" breakdown
PROJECT_COLORS = [
    "#22c55e", "#58a6ff", "#a78bfa", "#f59e0b", "#f87171",
    "#34d399", "#818cf8", "#fb923c", "#e879f9", "#38bdf8",
]

PROVIDER_COLORS = {
    "openai": "#10a37f",
    "anthropic": "#d4a574",
    "cliproxy": "#d4a574",
    "google": "#4285f4",
    "mistral": "#ff7000",
    "groq": "#f55036",
    "ollama": "#ffffff",
    "lmstudio": "#8b5cf6",
}

RANGE_LABELS = {
    "today": "Today",
    "7d": "7 Days",
    "30d": "30 Days",
    "all": "All Time",
}

# ---------------------------------------------------------------------------
# Page Template — uses string.Template for the outer skeleton only.
# JS is injected via $page_scripts to avoid $ escaping issues.
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenPulse &middot; $range_label</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#c9d1d9;font-family:'Inter',system-ui,-apple-system,sans-serif;line-height:1.5;min-height:100vh}
a{color:inherit;text-decoration:none}

/* Sticky nav */
.sticky-nav{
  position:fixed;top:0;left:0;right:0;z-index:100;
  background:rgba(15,17,23,0.92);backdrop-filter:blur(10px);
  border-bottom:1px solid #2a2d3a;
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 28px;
  transform:translateY(-100%);transition:transform .25s ease;
}
.sticky-nav.visible{transform:translateY(0)}
.sticky-nav .wordmark{font-size:16px;font-weight:800;color:#f0f6fc;letter-spacing:-0.5px}
.sticky-nav .range-bar{display:flex;gap:5px}
@media(max-width:600px){.sticky-nav{display:none}}

/* Layout */
.shell{max-width:1320px;margin:0 auto;padding:24px 28px 40px}

/* Header */
.header{position:relative;overflow:hidden;border-radius:14px;background:#1a1d27;border:1px solid #2a2d3a;margin-bottom:20px;padding:22px 24px 0}
.header-top{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:12px}
.header-left{display:flex;align-items:center;gap:14px}
.wordmark{font-size:24px;font-weight:800;color:#f0f6fc;letter-spacing:-0.5px}
.live-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(34,197,94,0.1);color:#22c55e;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600}
.pulse-dot{width:7px;height:7px;border-radius:50%;background:#22c55e;animation:pulse 2s ease-in-out infinite}
.pulse-dot.fast{animation:pulse .6s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.85)}}

/* Token flow strip */
.token-flow{height:80px;position:relative;overflow:hidden;margin:0 -24px}
.flow-dot{position:absolute;border-radius:50%;pointer-events:none;opacity:0;animation:flow-anim linear infinite}
@keyframes flow-anim{
  0%{left:-20px;opacity:0}
  5%{opacity:.9}
  90%{opacity:.7}
  100%{left:calc(100% + 20px);opacity:0}
}

/* Range buttons */
.range-bar{display:flex;gap:6px;flex-wrap:wrap}
.range-btn{padding:6px 18px;border-radius:8px;font-size:13px;font-weight:500;background:#1a1d27;border:1px solid #2a2d3a;color:#8b949e;cursor:pointer;transition:all .15s ease}
.range-btn:hover{border-color:#3d4250;color:#e6edf3}
.range-btn.active{background:#22c55e;border-color:#22c55e;color:#0f1117;font-weight:600}

/* Activity feed */
.activity-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:18px 24px;margin-bottom:20px}
.activity-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:10px}
.activity-timeline{position:relative;height:28px;background:#161922;border-radius:8px;overflow:hidden;margin-bottom:8px}
.activity-dot{position:absolute;top:50%;transform:translateY(-50%);width:10px;height:10px;border-radius:50%;opacity:.85;transition:box-shadow .3s}
.activity-dot.new-dot{animation:dot-pulse .8s ease-out}
@keyframes dot-pulse{0%{box-shadow:0 0 0 0 rgba(255,255,255,.6);transform:translateY(-50%) scale(1.4)}100%{box-shadow:0 0 0 8px rgba(255,255,255,0);transform:translateY(-50%) scale(1)}}
.activity-count{font-size:12px;color:#8b949e}
.activity-waiting{display:flex;align-items:center;justify-content:center;height:28px;gap:8px;color:#6e7681;font-size:13px}
.breathing{animation:breathe 3s ease-in-out infinite}
@keyframes breathe{0%,100%{opacity:.3}50%{opacity:1}}

/* Stat cards */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px}
.stat-card{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:20px 22px;transition:border-color .2s}
.stat-card:hover{border-color:#3d4250}
.stat-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:8px}
.stat-value{font-size:28px;font-weight:800;color:#f0f6fc;line-height:1}
.stat-sub{font-size:11px;color:#6e7681;margin-top:6px}
.stat-trend{font-size:11px;margin-top:5px;font-weight:600}
.stat-trend.up{color:#22c55e}
.stat-trend.down{color:#f85149}
.stat-trend.flat{color:#8b949e}
.stat-sparkline{margin-top:10px;display:block}
.clr-green{color:#22c55e}
.clr-blue{color:#58a6ff}
.clr-purple{color:#a78bfa}

/* Charts row */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.chart-panel{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;min-height:320px;display:flex;flex-direction:column}
.chart-title{font-size:14px;font-weight:700;color:#f0f6fc;margin-bottom:18px}

/* SVG spend chart */
.spend-svg-wrap{flex:1;position:relative;min-height:240px}
.spend-svg-wrap svg{width:100%;height:100%;display:block}
.svg-tooltip{
  position:absolute;pointer-events:none;background:rgba(15,17,23,.95);
  border:1px solid #3d4250;border-radius:8px;padding:10px 14px;
  font-size:12px;color:#c9d1d9;white-space:nowrap;z-index:50;
  opacity:0;transition:opacity .15s;box-shadow:0 4px 12px rgba(0,0,0,.4);
}
.svg-tooltip.visible{opacity:1}
.chart-empty{flex:1;display:flex;align-items:center;justify-content:center;color:#6e7681;font-size:13px}

/* Model breakdown */
.model-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.model-item{background:#161922;border:1px solid #2a2d3a;border-radius:10px;padding:14px 16px;transition:border-color .2s}
.model-item:hover{border-color:#3d4250}
.model-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.model-name{font-size:13px;font-weight:600;color:#f0f6fc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
.model-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.model-meta span{font-size:11px;color:#8b949e}
.model-cost{font-size:15px;font-weight:700;white-space:nowrap}
.usage-bar-bg{height:3px;background:#2a2d3a;border-radius:2px;margin-top:10px}
.usage-bar-fill{height:3px;border-radius:2px;transition:width .3s ease}
.prov-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;white-space:nowrap}

/* Heatmap */
.heatmap-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:0}
.heatmap-scroll{overflow-x:auto}
.heatmap-grid-wrap{display:flex;gap:0}
.heatmap-hour-labels{display:flex;flex-direction:column;justify-content:space-between;padding:26px 8px 0 0;min-width:30px}
.heatmap-hour-labels span{font-size:10px;color:#6e7681;line-height:1}
.heatmap-inner{flex:1}
.heatmap-day-labels{display:flex;gap:3px;margin-bottom:4px;padding-left:0}
.heatmap-day-label{flex:0 0 14px;font-size:9px;color:#6e7681;text-align:center;white-space:nowrap;overflow:hidden}
.heatmap-rows{display:flex;flex-direction:column;gap:3px}
.heatmap-row{display:flex;gap:3px}
.heatmap-cell{width:14px;height:14px;border-radius:2px;flex-shrink:0;cursor:default}

/* Insights */
.insights-section{margin-bottom:0;background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px}
.insights-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.insight-card{background:#1a1d27;border:1px solid #2a2d3a;border-radius:12px;padding:18px 20px;transition:border-color .2s}
.insight-card:hover{border-color:#3d4250}
.insight-emoji{font-size:22px;margin-bottom:10px}
.insight-title{font-size:13px;font-weight:700;color:#f0f6fc;margin-bottom:6px}
.insight-desc{font-size:12px;color:#8b949e;line-height:1.5}

/* Requests table */
.table-section{margin-bottom:28px}
.section-title{font-size:14px;font-weight:700;color:#f0f6fc;margin-bottom:14px}
.table-wrap{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;overflow:hidden;overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:720px}
th{background:#161922;color:#6e7681;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;padding:12px 16px;text-align:left;white-space:nowrap;border-bottom:1px solid #2a2d3a}
td{padding:11px 16px;font-size:12px;border-top:1px solid rgba(42,45,58,.5);white-space:nowrap}
.req-row{cursor:pointer;transition:background .15s}
.req-row:nth-child(even) td{background:rgba(22,25,34,.35)}
.req-row:hover td{background:rgba(22,25,34,.7) !important}
.req-row td:first-child{border-left:3px solid transparent}
.td-time{color:#6e7681}
.td-model{max-width:200px;overflow:hidden;text-overflow:ellipsis;color:#c9d1d9}
.cost-api{color:#22c55e;font-weight:600}
.cost-sub{color:#8b949e;font-style:italic}
.cost-local{color:#a78bfa;font-style:italic}
.stream-badge{display:inline-block;padding:1px 6px;border-radius:3px;background:rgba(88,166,255,.1);color:#58a6ff;font-size:9px;font-weight:600;margin-left:4px}
.latency{color:#6e7681}
.expand-chevron{display:inline-block;transition:transform .2s;color:#6e7681;font-size:11px;margin-left:6px}
.req-row.expanded .expand-chevron{transform:rotate(180deg)}

/* Detail row */
.detail-row td{padding:0 !important;border:none !important}
.detail-inner{
  max-height:0;overflow:hidden;transition:max-height .3s ease;
  background:#161922;border-top:1px solid #2a2d3a;
}
.detail-row.expanded .detail-inner{max-height:200px}
.detail-content{padding:14px 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px 20px}
.detail-field{display:flex;flex-direction:column;gap:2px}
.detail-key{font-size:10px;color:#6e7681;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.detail-val{font-size:12px;color:#c9d1d9}
.load-more{display:block;text-align:center;padding:14px;font-size:12px;color:#58a6ff;border-top:1px solid #2a2d3a}
.load-more:hover{background:rgba(88,166,255,.05)}

/* Footer */
.footer{text-align:center;color:#30363d;font-size:11px;padding:16px 0;border-top:1px solid #1a1d27}

/* Empty / error */
.empty-state{text-align:center;padding:60px 20px;color:#6e7681}
.empty-state h2{color:#f0f6fc;font-size:20px;margin-bottom:12px}
.empty-state p{max-width:480px;margin:0 auto 8px;font-size:13px;line-height:1.7}
.empty-state code{background:#1a1d27;padding:2px 6px;border-radius:4px;font-size:12px;color:#c9d1d9}
.error-state{text-align:center;padding:60px 20px}
.error-state h2{color:#f85149;font-size:20px;margin-bottom:12px}
.error-state p{color:#6e7681;font-size:13px}
.error-state code{display:block;margin-top:16px;background:#1a1d27;padding:12px;border-radius:8px;color:#c9d1d9;font-size:12px;text-align:left;max-width:600px;margin-left:auto;margin-right:auto;word-break:break-all}

/* Responsive */
@media(max-width:900px){
  .charts-row{grid-template-columns:1fr}
  .stats{grid-template-columns:repeat(2,1fr)}
  .insights-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:600px){
  .shell{padding:16px 14px 32px}
  .stats{grid-template-columns:1fr 1fr;gap:10px}
  .stat-value{font-size:22px}
  .stat-card{padding:16px}
  .wordmark{font-size:20px}
  td,th{padding:8px 10px;font-size:11px}
  .model-name{max-width:140px}
  .insights-grid{grid-template-columns:1fr}
}
@media(max-width:400px){.stats{grid-template-columns:1fr}}

/* ── Budget Alerts ─────────────────────────────────── */
.budget-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:20px}
.budget-empty{color:#6e7681;font-size:13px;padding:12px 0}
.budget-item{margin-bottom:16px}
.budget-item:last-child{margin-bottom:0}
.budget-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.budget-name{font-size:14px;font-weight:600;color:#f0f6fc}
.budget-meta{display:flex;align-items:center;gap:10px;font-size:12px;color:#8b949e}
.budget-amount{font-size:13px;font-weight:600}
.budget-bar-bg{height:8px;background:#2a2d3a;border-radius:4px;overflow:hidden}
.budget-bar-fill{height:8px;border-radius:4px;transition:width .4s ease}
.budget-bar-green{background:#22c55e}
.budget-bar-yellow{background:#eab308}
.budget-bar-orange{background:#f97316}
.budget-bar-red{background:#ef4444}
.budget-bar-over{background:#ef4444;animation:budget-pulse 1s ease-in-out infinite}
@keyframes budget-pulse{0%,100%{opacity:1}50%{opacity:.5}}
.over-badge{display:inline-flex;align-items:center;gap:4px;background:rgba(239,68,68,.15);color:#ef4444;border:1px solid rgba(239,68,68,.3);padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;animation:budget-pulse 1s ease-in-out infinite}
.budget-period-badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600;background:rgba(88,166,255,.1);color:#58a6ff}
.budget-manage-link{display:inline-block;margin-top:14px;font-size:12px;color:#58a6ff;cursor:pointer}
.budget-manage-link:hover{text-decoration:underline}

/* Budget management panel */
.budget-manage-panel{display:none;margin-top:16px;padding-top:16px;border-top:1px solid #2a2d3a}
.budget-manage-panel.open{display:block}
.budget-form{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-bottom:16px}
.budget-form input,.budget-form select{background:#161922;border:1px solid #2a2d3a;color:#c9d1d9;border-radius:7px;padding:7px 12px;font-size:13px;outline:none;transition:border-color .15s}
.budget-form input:focus,.budget-form select:focus{border-color:#58a6ff}
.budget-form input[type=text]{min-width:140px}
.budget-form input[type=number]{width:100px}
.budget-form-group{display:flex;flex-direction:column;gap:4px}
.budget-form-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#6e7681}
.btn-add-budget{background:#22c55e;color:#0f1117;border:none;border-radius:7px;padding:8px 16px;font-size:13px;font-weight:700;cursor:pointer;transition:background .15s}
.btn-add-budget:hover{background:#16a34a}
.budget-list-manage{display:flex;flex-direction:column;gap:8px}
.budget-manage-row{display:flex;align-items:center;justify-content:space-between;background:#161922;border:1px solid #2a2d3a;border-radius:8px;padding:10px 14px}
.budget-manage-info{font-size:13px;color:#c9d1d9}
.budget-manage-sub{font-size:11px;color:#6e7681;margin-top:2px}
.btn-delete-budget{background:rgba(239,68,68,.1);color:#ef4444;border:1px solid rgba(239,68,68,.2);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;transition:background .15s}
.btn-delete-budget:hover{background:rgba(239,68,68,.25)}

/* ── Cost Optimizer ────────────────────────────────── */
.optimizer-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:20px}
.optimizer-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-top:14px}
.optimizer-card{background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:16px 18px;transition:border-color .2s}
.optimizer-card:hover{border-color:#3d4250}
.optimizer-card-header{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.optimizer-icon{font-size:20px}
.optimizer-title{font-size:13px;font-weight:700;color:#f0f6fc}
.optimizer-savings{font-size:12px;font-weight:700;color:#22c55e;margin-left:auto;white-space:nowrap}
.optimizer-desc{font-size:12px;color:#8b949e;line-height:1.55}
.optimizer-empty{color:#6e7681;font-size:13px;padding:12px 0}

/* ── Project Breakdown ─────────────────────────────── */
.project-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:20px}
.project-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:14px}
.project-card{background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:14px 16px;transition:border-color .2s;border-left:3px solid transparent}
.project-card:hover{border-color:#3d4250}
.project-name{font-size:14px;font-weight:700;color:#f0f6fc;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.project-stats{display:flex;flex-direction:column;gap:3px}
.project-stat{display:flex;justify-content:space-between;align-items:center;font-size:12px}
.project-stat-label{color:#8b949e}
.project-stat-value{color:#c9d1d9;font-weight:600}
.project-cost{font-size:18px;font-weight:800;margin-bottom:8px}
.project-empty{color:#6e7681;font-size:13px;padding:12px 0}
</style>
</head>
<body>

<!-- Sticky Nav -->
<nav class="sticky-nav" id="stickyNav">
  <span class="wordmark">TokenPulse</span>
  <div class="range-bar">$range_buttons</div>
  <span class="live-badge"><span class="pulse-dot" id="stickyPulseDot"></span> Live</span>
</nav>

<div class="shell">

  <!-- Header with token flow -->
  <div class="header">
    <div class="header-top">
      <div class="header-left">
        <span class="wordmark">TokenPulse</span>
        <span class="live-badge"><span class="pulse-dot" id="mainPulseDot"></span> Live</span>
      </div>
      <div class="range-bar">$range_buttons</div>
    </div>
    <div class="token-flow" id="tokenFlow"></div>
  </div>

  $body_content

  <div class="footer">
    TokenPulse v$version &nbsp;&middot;&nbsp; Proxy: localhost:4100 &nbsp;&middot;&nbsp; Last updated: $updated_at
  </div>
</div>

$page_scripts
</body>
</html>""")

EMPTY_TEMPLATE = Template(r"""
<div class="empty-state">
  <h2>Welcome to TokenPulse</h2>
  <p>No request data found yet. Make sure the TokenPulse proxy is running on <code>localhost:4100</code> and route your API calls through it.</p>
  <p style="margin-top:16px;color:#8b949e;font-size:12px">Database path: <code>$db_path</code></p>
</div>
""")

ERROR_TEMPLATE = Template(r"""
<div class="error-state">
  <h2>Database Error</h2>
  <p>Could not connect to the TokenPulse database.</p>
  <code>$error_message</code>
  <p style="margin-top:16px">Expected path: <code>$db_path</code></p>
</div>
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_color(provider):
    return PROVIDER_COLORS.get((provider or "").lower(), "#8b949e")


def _provider_bg(provider):
    c = _provider_color(provider)
    if c.startswith("#") and len(c) == 7:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return f"rgba({r},{g},{b},0.12)"
    return "rgba(255,255,255,0.08)"


def provider_badge_html(provider):
    p = (provider or "unknown").lower()
    color = _provider_color(p)
    bg = _provider_bg(p)
    label = "LM Studio" if p == "lmstudio" else p
    return f'<span class="prov-badge" style="background:{bg};color:{color}">{label}</span>'


def fmt_tokens(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_cost(cost):
    try:
        c = float(cost or 0)
    except (TypeError, ValueError):
        return "$0.00"
    if c == 0:
        return "$0.00"
    if c < 0.01:
        return f"${c:.4f}"
    return f"${c:.2f}"


def fmt_latency(ms):
    if not ms:
        return "—"
    try:
        ms = float(ms)
    except (TypeError, ValueError):
        return "—"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{int(ms)}ms"


def relative_time(ts_str):
    if not ts_str:
        return "—"
    try:
        ts = datetime.fromisoformat(
            ts_str.replace("T", " ").replace("Z", "").split(".")[0]
        )
        diff = (datetime.now() - ts).total_seconds()
        if diff < 0:
            return ts_str[:16]
        if diff < 60:
            return f"{int(diff)}s ago"
        if diff < 3600:
            return f"{int(diff / 60)}m ago"
        if diff < 86400:
            return f"{int(diff / 3600)}h ago"
        if diff < 172800:
            return "yesterday"
        return ts.strftime("%b %d, %H:%M")
    except Exception:
        return ts_str[:16] if ts_str else "—"


def _time_filter_sql(time_range, prefix="WHERE"):
    if time_range == "today":
        return f" {prefix} timestamp >= datetime('now', 'start of day')"
    elif time_range == "7d":
        return f" {prefix} timestamp >= datetime('now', '-7 days')"
    elif time_range == "30d":
        return f" {prefix} timestamp >= datetime('now', '-30 days')"
    return ""


def _prev_period_sql(time_range):
    """Return (start_expr, end_expr) for the previous comparable period."""
    if time_range == "today":
        return ("datetime('now', '-1 day', 'start of day')",
                "datetime('now', 'start of day')")
    elif time_range == "7d":
        return ("datetime('now', '-14 days')", "datetime('now', '-7 days')")
    elif time_range == "30d":
        return ("datetime('now', '-60 days')", "datetime('now', '-30 days')")
    return (None, None)


def _chart_days(time_range):
    if time_range in ("today", "7d"):
        return 7
    return 30


def _escape_html(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Sparkline SVG generation
# ---------------------------------------------------------------------------

def _sparkline_svg(values, color):
    """Generate a 120x40 SVG sparkline polyline + area fill."""
    if not values or len(values) == 0:
        return ""
    vals = [float(v) for v in values]
    max_v = max(vals) if max(vals) > 0 else 1.0
    n = len(vals)
    step = 120.0 / max(n - 1, 1)

    pts = []
    for i, v in enumerate(vals):
        x = i * step
        y = 40.0 - (v / max_v) * 38.0
        pts.append((x, y))

    poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    # Area polygon: polyline pts + bottom-right + bottom-left
    area_pts = poly_pts
    if pts:
        area_pts += f" {pts[-1][0]:.1f},40 {pts[0][0]:.1f},40"

    # Parse color for fill
    c = color
    if c.startswith("#") and len(c) == 7:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        fill_color = f"rgba({r},{g},{b},0.15)"
    else:
        fill_color = "rgba(255,255,255,0.1)"

    return (
        f'<svg class="stat-sparkline" viewBox="0 0 120 40" width="120" height="40"'
        f' xmlns="http://www.w3.org/2000/svg" style="overflow:visible">'
        f'<polygon points="{area_pts}" fill="{fill_color}"/>'
        f'<polyline points="{poly_pts}" fill="none"'
        f' stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_data(time_range):
    """Fetch all dashboard data from SQLite. Returns a dict or raises."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    where = _time_filter_sql(time_range, "WHERE")
    and_clause = _time_filter_sql(time_range, "AND")

    # Summary stats
    c.execute(
        f"SELECT COUNT(*) as cnt, "
        f"COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens "
        f"FROM requests{where}"
    )
    row = c.fetchone()
    total_requests = row["cnt"]
    total_tokens = row["total_tokens"]

    api_cost = 0
    sub_tokens = 0
    local_tokens = 0
    try:
        c.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0) as v FROM requests "
            f"WHERE COALESCE(provider_type, 'api') = 'api'{and_clause}"
        )
        api_cost = c.fetchone()["v"] or 0

        c.execute(
            f"SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as v "
            f"FROM requests WHERE provider_type = 'subscription'{and_clause}"
        )
        sub_tokens = c.fetchone()["v"] or 0

        c.execute(
            f"SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as v "
            f"FROM requests WHERE provider_type = 'local'{and_clause}"
        )
        local_tokens = c.fetchone()["v"] or 0
    except Exception:
        c.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0) as v FROM requests{where}"
        )
        api_cost = c.fetchone()["v"] or 0

    # Daily chart data
    days = _chart_days(time_range)
    c.execute(
        f"SELECT date(timestamp) as day, "
        f"LOWER(provider) as prov, "
        f"COALESCE(SUM(cost_usd), 0) as cost "
        f"FROM requests "
        f"WHERE timestamp >= datetime('now', '-{days} days') "
        f"GROUP BY day, prov ORDER BY day"
    )
    daily_raw = [dict(r) for r in c.fetchall()]

    # Model breakdown
    try:
        c.execute(
            f"SELECT model, provider, COUNT(*) as cnt, "
            f"COALESCE(SUM(input_tokens), 0) as inp, "
            f"COALESCE(SUM(output_tokens), 0) as outp, "
            f"COALESCE(SUM(cost_usd), 0) as cost, "
            f"COALESCE(provider_type, 'api') as ptype "
            f"FROM requests{where} "
            f"GROUP BY model, provider "
            f"ORDER BY (inp + outp) DESC LIMIT 15"
        )
        models = [dict(r) for r in c.fetchall()]
    except Exception:
        c.execute(
            f"SELECT model, provider, COUNT(*) as cnt, "
            f"COALESCE(SUM(input_tokens), 0) as inp, "
            f"COALESCE(SUM(output_tokens), 0) as outp, "
            f"COALESCE(SUM(cost_usd), 0) as cost, "
            f"'api' as ptype "
            f"FROM requests{where} "
            f"GROUP BY model, provider "
            f"ORDER BY (inp + outp) DESC LIMIT 15"
        )
        models = [dict(r) for r in c.fetchall()]

    # Recent requests with extended columns
    base_cols = (
        "timestamp, provider, model, input_tokens, output_tokens, "
        "cost_usd, latency_ms, is_streaming"
    )
    try:
        c.execute(
            f"SELECT {base_cols}, "
            f"COALESCE(provider_type, 'api') as ptype, "
            f"COALESCE(cached_tokens, 0) as cached_tokens, "
            f"COALESCE(reasoning_tokens, 0) as reasoning_tokens, "
            f"COALESCE(tokens_per_second, 0) as tokens_per_second, "
            f"COALESCE(time_to_first_token_ms, 0) as time_to_first_token_ms, "
            f"COALESCE(error_message, '') as error_message, "
            f"COALESCE(source_tag, '') as source_tag "
            f"FROM requests{where} ORDER BY timestamp DESC LIMIT 50"
        )
        requests_rows = [dict(r) for r in c.fetchall()]
    except Exception:
        # Fall back to base columns only
        try:
            c.execute(
                f"SELECT {base_cols}, "
                f"COALESCE(provider_type, 'api') as ptype, "
                f"0 as cached_tokens, 0 as reasoning_tokens, "
                f"0 as tokens_per_second, 0 as time_to_first_token_ms, "
                f"'' as error_message, '' as source_tag "
                f"FROM requests{where} ORDER BY timestamp DESC LIMIT 50"
            )
            requests_rows = [dict(r) for r in c.fetchall()]
        except Exception:
            c.execute(
                f"SELECT {base_cols}, 'api' as ptype "
                f"FROM requests{where} ORDER BY timestamp DESC LIMIT 50"
            )
            rows_base = [dict(r) for r in c.fetchall()]
            for rb in rows_base:
                rb.update({
                    "cached_tokens": 0, "reasoning_tokens": 0,
                    "tokens_per_second": 0, "time_to_first_token_ms": 0,
                    "error_message": "", "source_tag": "",
                })
            requests_rows = rows_base

    # Activity feed — try last 5 minutes first, fall back to last 20 requests
    activity_60s = []
    activity_window = "5 minutes"
    try:
        c.execute(
            "SELECT timestamp, provider, COALESCE(provider_type,'api') as ptype "
            "FROM requests WHERE timestamp >= datetime('now', '-5 minutes') "
            "ORDER BY timestamp ASC"
        )
        activity_60s = [dict(r) for r in c.fetchall()]
        # If no activity in 5 min, grab the last 20 requests regardless of time
        if not activity_60s:
            c.execute(
                "SELECT timestamp, provider, COALESCE(provider_type,'api') as ptype "
                "FROM requests ORDER BY timestamp DESC LIMIT 20"
            )
            activity_60s = list(reversed([dict(r) for r in c.fetchall()]))
            activity_window = "recent"
    except Exception:
        try:
            c.execute(
                "SELECT timestamp, provider, 'api' as ptype "
                "FROM requests ORDER BY timestamp DESC LIMIT 20"
            )
            activity_60s = list(reversed([dict(r) for r in c.fetchall()]))
            activity_window = "recent"
        except Exception:
            pass

    # Trend data (previous period)
    trend = {"api_cost_prev": None, "sub_tokens_prev": None,
             "local_tokens_prev": None, "total_requests_prev": None}
    if time_range != "all":
        prev_start, prev_end = _prev_period_sql(time_range)
        if prev_start and prev_end:
            try:
                c.execute(
                    f"SELECT COALESCE(SUM(cost_usd),0) as v FROM requests "
                    f"WHERE timestamp >= {prev_start} AND timestamp < {prev_end} "
                    f"AND COALESCE(provider_type,'api')='api'"
                )
                trend["api_cost_prev"] = c.fetchone()["v"] or 0
                c.execute(
                    f"SELECT COALESCE(SUM(input_tokens+output_tokens),0) as v "
                    f"FROM requests "
                    f"WHERE timestamp >= {prev_start} AND timestamp < {prev_end} "
                    f"AND provider_type='subscription'"
                )
                trend["sub_tokens_prev"] = c.fetchone()["v"] or 0
                c.execute(
                    f"SELECT COALESCE(SUM(input_tokens+output_tokens),0) as v "
                    f"FROM requests "
                    f"WHERE timestamp >= {prev_start} AND timestamp < {prev_end} "
                    f"AND provider_type='local'"
                )
                trend["local_tokens_prev"] = c.fetchone()["v"] or 0
                c.execute(
                    f"SELECT COUNT(*) as cnt FROM requests "
                    f"WHERE timestamp >= {prev_start} AND timestamp < {prev_end}"
                )
                trend["total_requests_prev"] = c.fetchone()["cnt"] or 0
            except Exception:
                pass

    # Sparklines (last 7 daily data points)
    today = datetime.now().date()
    sparkline_days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

    def _sparkline_query(metric_expr, filter_extra=""):
        results = {}
        try:
            c.execute(
                f"SELECT date(timestamp) as day, {metric_expr} as val "
                f"FROM requests "
                f"WHERE timestamp >= datetime('now', '-7 days'){filter_extra} "
                f"GROUP BY day ORDER BY day"
            )
            for row2 in c.fetchall():
                results[row2["day"]] = row2["val"] or 0
        except Exception:
            pass
        return [(d, results.get(d, 0)) for d in sparkline_days]

    sparklines = {
        "spend_days": _sparkline_query("COALESCE(SUM(cost_usd),0)",
                                       " AND COALESCE(provider_type,'api')='api'"),
        "sub_days": _sparkline_query("COALESCE(SUM(input_tokens+output_tokens),0)",
                                     " AND provider_type='subscription'"),
        "local_days": _sparkline_query("COALESCE(SUM(input_tokens+output_tokens),0)",
                                       " AND provider_type='local'"),
        "req_days": _sparkline_query("COUNT(*)"),
    }

    # Heatmap (30 days x 24 hours)
    heatmap = []
    try:
        c.execute(
            "SELECT strftime('%Y-%m-%d', timestamp) as day, "
            "CAST(strftime('%H', timestamp) AS INTEGER) as hour, "
            "COUNT(*) as cnt "
            "FROM requests WHERE timestamp >= datetime('now', '-30 days') "
            "GROUP BY day, hour"
        )
        heatmap = [dict(r) for r in c.fetchall()]
    except Exception:
        pass

    # Insights
    insights_raw = {
        "busiest_hour": None, "top_model": None, "top_model_pct": 0.0,
        "avg_latency_ms": None, "distinct_models": 0, "stream_pct": 0.0,
        "sub_token_pct": 0.0, "cost_per_1k": None,
    }
    try:
        # Busiest hour
        c.execute(
            f"SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hr, COUNT(*) as cnt "
            f"FROM requests{where} GROUP BY hr ORDER BY cnt DESC LIMIT 1"
        )
        hr_row = c.fetchone()
        if hr_row and hr_row["cnt"] > 0:
            h = hr_row["hr"]
            ampm = "am" if h < 12 else "pm"
            h12 = h % 12 or 12
            insights_raw["busiest_hour"] = f"{h12}{ampm}"

        # Top model
        c.execute(
            f"SELECT model, COUNT(*) as cnt FROM requests{where} "
            f"GROUP BY model ORDER BY cnt DESC LIMIT 1"
        )
        tm_row = c.fetchone()
        if tm_row and tm_row["cnt"] > 0 and total_requests > 0:
            insights_raw["top_model"] = tm_row["model"] or "unknown"
            insights_raw["top_model_pct"] = round(tm_row["cnt"] / total_requests * 100, 1)

        # Avg latency
        c.execute(
            f"SELECT AVG(latency_ms) as v FROM requests{where} WHERE latency_ms IS NOT NULL"
        )
        lat_row = c.fetchone()
        if lat_row and lat_row["v"]:
            insights_raw["avg_latency_ms"] = round(float(lat_row["v"]), 0)

        # Distinct models
        c.execute(f"SELECT COUNT(DISTINCT model) as cnt FROM requests{where}")
        insights_raw["distinct_models"] = c.fetchone()["cnt"] or 0

        # Streaming pct
        c.execute(
            f"SELECT COUNT(*) as cnt FROM requests{where} WHERE is_streaming=1"
        )
        stream_cnt = c.fetchone()["cnt"] or 0
        if total_requests > 0:
            insights_raw["stream_pct"] = round(stream_cnt / total_requests * 100, 1)

        # Sub token pct
        total_tok_all = total_tokens or 0
        if total_tok_all > 0 and sub_tokens > 0:
            insights_raw["sub_token_pct"] = round(sub_tokens / total_tok_all * 100, 1)

        # Cost per 1k tokens
        api_tok = total_tok_all - sub_tokens - local_tokens
        if api_tok > 0 and api_cost > 0:
            insights_raw["cost_per_1k"] = round(api_cost / api_tok * 1000, 4)

    except Exception:
        pass

    conn.close()

    return {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "api_cost": api_cost,
        "sub_tokens": sub_tokens,
        "local_tokens": local_tokens,
        "daily_raw": daily_raw,
        "models": models,
        "requests": requests_rows,
        "chart_days": days,
        "activity_60s": activity_60s,
        "trend": trend,
        "sparklines": sparklines,
        "heatmap": heatmap,
        "insights_raw": insights_raw,
    }


# ---------------------------------------------------------------------------
# HTML Builders
# ---------------------------------------------------------------------------

def _build_range_buttons(active):
    parts = []
    for key, label in RANGE_LABELS.items():
        cls = "range-btn active" if key == active else "range-btn"
        parts.append(f'<a href="?range={key}" class="{cls}">{label}</a>')
    return "\n      ".join(parts)


def _trend_html(current, prev):
    """Return trend arrow HTML string."""
    if prev is None or prev == 0:
        return ""
    try:
        pct = (float(current) - float(prev)) / float(prev) * 100
    except (TypeError, ZeroDivisionError):
        return ""
    if abs(pct) < 0.5:
        return '<span class="stat-trend flat">&#8212; no change</span>'
    if pct > 0:
        return f'<span class="stat-trend up">&#8593; {abs(pct):.0f}% vs prev</span>'
    return f'<span class="stat-trend down">&#8595; {abs(pct):.0f}% vs prev</span>'


def _fetch_budgets_with_status():
    """Fetch all budgets with their current spend status."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Ensure table exists
        try:
            c.execute("SELECT COUNT(*) FROM budgets")
        except Exception:
            conn.close()
            return []

        c.execute(
            "SELECT id, name, period, threshold_usd, provider_filter, enabled "
            "FROM budgets WHERE enabled=1 ORDER BY created_at ASC"
        )
        budgets = [dict(r) for r in c.fetchall()]

        results = []
        for b in budgets:
            period = b["period"]
            if period == "daily":
                time_expr = "datetime('now', 'start of day')"
            elif period == "weekly":
                time_expr = "datetime('now', '-7 days')"
            else:
                time_expr = "datetime('now', '-30 days')"

            pf = b["provider_filter"]
            try:
                if pf:
                    c.execute(
                        f"SELECT COALESCE(SUM(cost_usd),0) FROM requests "
                        f"WHERE timestamp >= {time_expr} "
                        f"AND COALESCE(provider_type,'api')='api' AND provider=?",
                        (pf,)
                    )
                else:
                    c.execute(
                        f"SELECT COALESCE(SUM(cost_usd),0) FROM requests "
                        f"WHERE timestamp >= {time_expr} "
                        f"AND COALESCE(provider_type,'api')='api'"
                    )
                current_spend = c.fetchone()[0] or 0.0
            except Exception:
                current_spend = 0.0

            threshold = b["threshold_usd"] or 0.001
            pct = (current_spend / threshold) * 100.0 if threshold > 0 else 0.0
            results.append({
                "id": b["id"],
                "name": b["name"],
                "period": period,
                "threshold_usd": b["threshold_usd"],
                "provider_filter": pf,
                "current_spend": current_spend,
                "percentage": pct,
                "is_over": current_spend >= b["threshold_usd"],
            })

        conn.close()
        return results
    except Exception:
        return []


def _fetch_all_budgets():
    """Fetch all budgets (including disabled) for management panel."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        try:
            c.execute(
                "SELECT id, name, period, threshold_usd, provider_filter, enabled "
                "FROM budgets ORDER BY created_at ASC"
            )
            rows = [dict(r) for r in c.fetchall()]
        except Exception:
            rows = []
        conn.close()
        return rows
    except Exception:
        return []


def _fetch_project_breakdown():
    """Fetch per-project cost/request/token breakdown."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        try:
            c.execute(
                "SELECT COALESCE(source_tag,'unknown') as tag, "
                "COUNT(*) as cnt, "
                "COALESCE(SUM(cost_usd),0) as cost, "
                "COALESCE(SUM(input_tokens+output_tokens),0) as tokens "
                "FROM requests "
                "GROUP BY tag ORDER BY cost DESC"
            )
            rows = [dict(r) for r in c.fetchall()]
        except Exception:
            rows = []
        conn.close()
        return rows
    except Exception:
        return []


def _fetch_optimizer_data():
    """Fetch raw data needed for optimization recommendations."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Per-model avg token counts and costs (API only)
        try:
            c.execute(
                "SELECT model, "
                "AVG(input_tokens+output_tokens) as avg_tokens, "
                "AVG(input_tokens) as avg_input, "
                "AVG(output_tokens) as avg_output, "
                "COUNT(*) as cnt, "
                "SUM(cost_usd) as total_cost, "
                "SUM(input_tokens) as sum_input, "
                "SUM(output_tokens) as sum_output "
                "FROM requests "
                "WHERE COALESCE(provider_type,'api')='api' "
                "GROUP BY model"
            )
            model_stats = [dict(r) for r in c.fetchall()]
        except Exception:
            model_stats = []

        # Failed requests cost last 7 days
        try:
            c.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd),0) as cost "
                "FROM requests "
                "WHERE error_message IS NOT NULL AND error_message != '' "
                "AND timestamp >= datetime('now','-7 days')"
            )
            row = c.fetchone()
            failed_cnt = row["cnt"] or 0
            failed_cost = row["cost"] or 0.0
        except Exception:
            failed_cnt = 0
            failed_cost = 0.0

        # Over-prompting: high input, low output
        try:
            c.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd),0) as cost "
                "FROM requests "
                "WHERE input_tokens > 2000 AND output_tokens < 50 "
                "AND COALESCE(provider_type,'api')='api' "
                "AND timestamp >= datetime('now','-7 days')"
            )
            row = c.fetchone()
            overprompt_cnt = row["cnt"] or 0
            overprompt_cost = row["cost"] or 0.0
        except Exception:
            overprompt_cnt = 0
            overprompt_cost = 0.0

        # Provider cost per 1K tokens
        try:
            c.execute(
                "SELECT provider, "
                "SUM(cost_usd) as total_cost, "
                "SUM(input_tokens+output_tokens) as total_tokens "
                "FROM requests "
                "WHERE COALESCE(provider_type,'api')='api' "
                "GROUP BY provider"
            )
            provider_eff = [dict(r) for r in c.fetchall()]
        except Exception:
            provider_eff = []

        # Peak hour analysis (last 30 days)
        try:
            c.execute(
                "SELECT CAST(strftime('%H',timestamp) AS INTEGER) as hr, COUNT(*) as cnt "
                "FROM requests "
                "WHERE timestamp >= datetime('now','-30 days') "
                "GROUP BY hr ORDER BY cnt DESC"
            )
            hour_rows = [dict(r) for r in c.fetchall()]
        except Exception:
            hour_rows = []

        # Local model usage check
        try:
            c.execute(
                "SELECT COUNT(*) as cnt FROM requests "
                "WHERE COALESCE(provider_type,'api')='local' "
                "AND timestamp >= datetime('now','-30 days')"
            )
            local_cnt = c.fetchone()["cnt"] or 0

            c.execute(
                "SELECT COUNT(*) as cnt FROM requests "
                "WHERE (input_tokens+output_tokens) < 500 "
                "AND COALESCE(provider_type,'api')='api' "
                "AND timestamp >= datetime('now','-30 days')"
            )
            small_api_cnt = c.fetchone()["cnt"] or 0
        except Exception:
            local_cnt = 0
            small_api_cnt = 0

        conn.close()
        return {
            "model_stats": model_stats,
            "failed_cnt": failed_cnt,
            "failed_cost": failed_cost,
            "overprompt_cnt": overprompt_cnt,
            "overprompt_cost": overprompt_cost,
            "provider_eff": provider_eff,
            "hour_rows": hour_rows,
            "local_cnt": local_cnt,
            "small_api_cnt": small_api_cnt,
        }
    except Exception:
        return {}


def _build_budget_section(budgets, all_budgets):
    """Build the budget status section with progress bars."""
    # Budget status cards
    if not budgets:
        status_html = '<div class="budget-empty">No budgets configured — set one up to control your spending.</div>'
    else:
        items = []
        for b in budgets:
            name = _escape_html(b["name"])
            period = b["period"]
            current = b["current_spend"]
            threshold = b["threshold_usd"]
            pct = min(b["percentage"], 100.0)  # cap bar at 100%
            pct_raw = b["percentage"]
            is_over = b["is_over"]

            # Bar color
            if is_over:
                bar_class = "budget-bar-fill budget-bar-over"
            elif pct_raw >= 95:
                bar_class = "budget-bar-fill budget-bar-red"
            elif pct_raw >= 80:
                bar_class = "budget-bar-fill budget-bar-orange"
            elif pct_raw >= 60:
                bar_class = "budget-bar-fill budget-bar-yellow"
            else:
                bar_class = "budget-bar-fill budget-bar-green"

            pf = b.get("provider_filter")
            pf_html = f' &middot; <span style="color:#8b949e">{_escape_html(pf)}</span>' if pf else ""

            over_badge = ""
            if is_over:
                over_badge = '<span class="over-badge">&#9888; OVER BUDGET</span>'

            items.append(
                f'<div class="budget-item">'
                f'<div class="budget-header">'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<span class="budget-name">{name}</span>'
                f'<span class="budget-period-badge">{period}</span>'
                f'{pf_html}'
                f'</div>'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'{over_badge}'
                f'<span class="budget-amount" style="color:{"#ef4444" if is_over else "#f0f6fc"}">'
                f'{fmt_cost(current)} / {fmt_cost(threshold)}</span>'
                f'<span style="font-size:12px;color:#8b949e">{pct_raw:.0f}%</span>'
                f'</div>'
                f'</div>'
                f'<div class="budget-bar-bg">'
                f'<div class="{bar_class}" style="width:{pct:.1f}%"></div>'
                f'</div>'
                f'</div>'
            )
        status_html = "\n".join(items)

    # Management panel
    # Build existing budget rows
    manage_rows = ""
    for b in all_budgets:
        bid = b["id"]
        bname = _escape_html(b["name"])
        period = b["period"]
        threshold = b["threshold_usd"]
        pf = b.get("provider_filter") or "all providers"
        manage_rows += (
            f'<div class="budget-manage-row" id="bmrow-{bid}">'
            f'<div>'
            f'<div class="budget-manage-info">{bname} &mdash; {fmt_cost(threshold)} / {period}</div>'
            f'<div class="budget-manage-sub">{_escape_html(pf)}</div>'
            f'</div>'
            f'<button class="btn-delete-budget" onclick="deleteBudget({bid})">Delete</button>'
            f'</div>'
        )
    if not manage_rows:
        manage_rows = '<div style="color:#6e7681;font-size:13px">No budgets yet.</div>'

    return f"""<div class="budget-section">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <div class="section-title" style="margin-bottom:0">Budget Alerts</div>
  </div>
  {status_html}
  <a class="budget-manage-link" onclick="toggleBudgetPanel()">&#9881; Manage Budgets</a>
  <div class="budget-manage-panel" id="budgetManagePanel">
    <div style="font-size:13px;font-weight:600;color:#f0f6fc;margin-bottom:10px">Add Budget</div>
    <div class="budget-form" id="budgetForm">
      <div class="budget-form-group">
        <label class="budget-form-label">Name</label>
        <input type="text" id="bName" placeholder="e.g. Monthly API Budget">
      </div>
      <div class="budget-form-group">
        <label class="budget-form-label">Period</label>
        <select id="bPeriod">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly" selected>Monthly</option>
        </select>
      </div>
      <div class="budget-form-group">
        <label class="budget-form-label">Threshold ($)</label>
        <input type="number" id="bThreshold" placeholder="10.00" min="0.01" step="0.01">
      </div>
      <div class="budget-form-group">
        <label class="budget-form-label">Provider (optional)</label>
        <input type="text" id="bProvider" placeholder="all providers">
      </div>
      <button class="btn-add-budget" onclick="addBudget()">+ Add</button>
    </div>
    <div style="font-size:13px;font-weight:600;color:#f0f6fc;margin-bottom:8px">Existing Budgets</div>
    <div class="budget-list-manage" id="budgetListManage">
      {manage_rows}
    </div>
  </div>
</div>"""


def _build_optimizer_section(opt_data):
    """Build cost optimization recommendation cards."""
    if not opt_data:
        return ""

    recommendations = []

    # 1. Model downgrade opportunities
    for ms in opt_data.get("model_stats", []):
        model = (ms.get("model") or "").lower()
        avg_tokens = ms.get("avg_tokens") or 0
        cnt = ms.get("cnt") or 0
        sum_input = ms.get("sum_input") or 0
        sum_output = ms.get("sum_output") or 0
        total_cost = ms.get("total_cost") or 0

        if cnt < 3:
            continue

        # Check if model is expensive
        model_info = None
        for key in MODEL_COSTS:
            if key in model:
                model_info = MODEL_COSTS[key]
                break

        if not model_info or model_info["tier"] == "budget":
            continue

        # Find downgrade candidate
        downgrade = None
        for key, cheaper in DOWNGRADE_MAP.items():
            if key in model:
                downgrade = cheaper
                break

        if not downgrade or avg_tokens >= 1000:
            continue

        # Estimate savings
        cheaper_info = None
        for key in MODEL_COSTS:
            if key in downgrade:
                cheaper_info = MODEL_COSTS[key]
                break

        savings = 0.0
        if cheaper_info and sum_input > 0:
            current_estimated = (sum_input / 1_000_000 * model_info["input"] +
                                  sum_output / 1_000_000 * model_info["output"])
            cheaper_estimated = (sum_input / 1_000_000 * cheaper_info["input"] +
                                  sum_output / 1_000_000 * cheaper_info["output"])
            savings = max(0.0, current_estimated - cheaper_estimated)

        pct_under = 100
        desc = (f"{cnt} requests to {model} averaged {int(avg_tokens):,} tokens — "
                f"under the 1K threshold. {downgrade} handles simple tasks at a fraction of the cost.")
        savings_str = f"~{fmt_cost(savings)}" if savings > 0.001 else None
        recommendations.append({
            "icon": "💰",
            "title": f"Downgrade {model} → {downgrade}",
            "desc": desc,
            "savings": savings,
            "savings_str": savings_str,
        })

    # 2. Provider efficiency
    prov_eff = opt_data.get("provider_eff", [])
    if len(prov_eff) >= 2:
        prov_costs = []
        for p in prov_eff:
            toks = p.get("total_tokens") or 0
            cost = p.get("total_cost") or 0
            if toks > 1000 and cost > 0:
                per_1k = (cost / toks) * 1000
                prov_costs.append((p["provider"], per_1k))
        if len(prov_costs) >= 2:
            prov_costs.sort(key=lambda x: x[1])
            cheapest = prov_costs[0]
            most_exp = prov_costs[-1]
            if most_exp[1] > cheapest[1] * 1.5:
                desc = (f"Cost per 1K tokens: {cheapest[0]} ${cheapest[1]:.4f} vs "
                        f"{most_exp[0]} ${most_exp[1]:.4f}. "
                        f"Consider {cheapest[0]} for cost-sensitive workloads.")
                recommendations.append({
                    "icon": "💰",
                    "title": "Provider Efficiency Gap",
                    "desc": desc,
                    "savings": 0,
                    "savings_str": None,
                })

    # 3. Waste detection — failed requests
    failed_cnt = opt_data.get("failed_cnt", 0)
    failed_cost = opt_data.get("failed_cost", 0.0)
    if failed_cnt > 0 and failed_cost > 0.001:
        desc = (f"{failed_cnt} failed request{'s' if failed_cnt != 1 else ''} cost "
                f"{fmt_cost(failed_cost)} in wasted tokens this week. "
                f"Review error patterns to reduce waste.")
        recommendations.append({
            "icon": "⚠️",
            "title": "Wasted Spend on Errors",
            "desc": desc,
            "savings": failed_cost,
            "savings_str": fmt_cost(failed_cost),
        })

    # 4. Over-prompting
    overprompt_cnt = opt_data.get("overprompt_cnt", 0)
    overprompt_cost = opt_data.get("overprompt_cost", 0.0)
    if overprompt_cnt >= 3:
        desc = (f"{overprompt_cnt} requests sent large prompts (&gt;2K input tokens) "
                f"but got tiny responses (&lt;50 output tokens). "
                f"Consider trimming context windows.")
        recommendations.append({
            "icon": "⚠️",
            "title": "Possible Over-Prompting",
            "desc": desc,
            "savings": overprompt_cost,
            "savings_str": fmt_cost(overprompt_cost) if overprompt_cost > 0.001 else None,
        })

    # 5. Peak hour pattern
    hour_rows = opt_data.get("hour_rows", [])
    if hour_rows:
        total_hr = sum(r.get("cnt", 0) for r in hour_rows)
        if total_hr > 10:
            # Find top 3-hour window
            top3 = hour_rows[:3]
            top3_cnt = sum(r.get("cnt", 0) for r in top3)
            top3_pct = (top3_cnt / total_hr) * 100 if total_hr > 0 else 0
            if top3_pct >= 50 and top3:
                hrs = [r["hr"] for r in top3]
                h_start = min(hrs)
                h_end = max(hrs)
                def fmth(h):
                    ampm = "am" if h < 12 else "pm"
                    return f"{h % 12 or 12}{ampm}"
                desc = (f"{top3_pct:.0f}% of your usage occurs between "
                        f"{fmth(h_start)}–{fmth(h_end)}. "
                        f"Spreading non-urgent requests could reduce rate limit hits.")
                recommendations.append({
                    "icon": "💡",
                    "title": "Request Concentration",
                    "desc": desc,
                    "savings": 0,
                    "savings_str": None,
                })

    # 6. Local model suggestion
    local_cnt = opt_data.get("local_cnt", 0)
    small_api_cnt = opt_data.get("small_api_cnt", 0)
    if local_cnt == 0 and small_api_cnt >= 50:
        desc = (f"You made {small_api_cnt:,} API requests under 500 tokens this month. "
                f"A local 7B model (Ollama, LM Studio) could handle many of these for free.")
        recommendations.append({
            "icon": "💡",
            "title": "Local Model Opportunity",
            "desc": desc,
            "savings": 0,
            "savings_str": None,
        })

    if not recommendations:
        return f"""<div class="optimizer-section">
  <div class="section-title">Cost Optimizer</div>
  <div class="optimizer-empty">&#10003; No optimization opportunities found — your usage looks efficient!</div>
</div>"""

    # Sort by savings desc
    recommendations.sort(key=lambda x: x["savings"], reverse=True)

    cards = []
    for rec in recommendations:
        savings_html = ""
        if rec.get("savings_str"):
            savings_html = f'<span class="optimizer-savings">Save {rec["savings_str"]}</span>'
        cards.append(
            f'<div class="optimizer-card">'
            f'<div class="optimizer-card-header">'
            f'<span class="optimizer-icon">{rec["icon"]}</span>'
            f'<span class="optimizer-title">{_escape_html(rec["title"])}</span>'
            f'{savings_html}'
            f'</div>'
            f'<div class="optimizer-desc">{rec["desc"]}</div>'
            f'</div>'
        )

    cards_html = "\n".join(cards)
    return f"""<div class="optimizer-section">
  <div class="section-title">Cost Optimizer</div>
  <div class="optimizer-grid">
    {cards_html}
  </div>
</div>"""


def _build_project_section(projects):
    """Build the By Project breakdown section."""
    if not projects:
        return f"""<div class="project-section">
  <div class="section-title">By Project</div>
  <div class="project-empty">No tagged requests yet. Source tags are auto-detected from User-Agent, or set <code>X-TokenPulse-Project</code> header.</div>
</div>"""

    cards = []
    for i, p in enumerate(projects):
        tag = p.get("tag") or "unknown"
        cnt = p.get("cnt") or 0
        cost = p.get("cost") or 0.0
        tokens = p.get("tokens") or 0
        color = PROJECT_COLORS[i % len(PROJECT_COLORS)]

        cards.append(
            f'<div class="project-card" style="border-left-color:{color}">'
            f'<div class="project-name" title="{_escape_html(tag)}">{_escape_html(tag)}</div>'
            f'<div class="project-cost" style="color:{color}">{fmt_cost(cost)}</div>'
            f'<div class="project-stats">'
            f'<div class="project-stat"><span class="project-stat-label">Requests</span>'
            f'<span class="project-stat-value">{cnt:,}</span></div>'
            f'<div class="project-stat"><span class="project-stat-label">Tokens</span>'
            f'<span class="project-stat-value">{fmt_tokens(tokens)}</span></div>'
            f'</div>'
            f'</div>'
        )

    cards_html = "\n".join(cards)
    return f"""<div class="project-section">
  <div class="section-title">By Project</div>
  <div class="project-grid">
    {cards_html}
  </div>
</div>"""


def _build_stats_cards(data):
    trend = data.get("trend", {})
    sparklines = data.get("sparklines", {})

    def spark_vals(key):
        return [v for _, v in sparklines.get(key, [])]

    spend_spark = _sparkline_svg(spark_vals("spend_days"), "#22c55e")
    sub_spark = _sparkline_svg(spark_vals("sub_days"), "#58a6ff")
    local_spark = _sparkline_svg(spark_vals("local_days"), "#a78bfa")
    req_spark = _sparkline_svg(spark_vals("req_days"), "#c9d1d9")

    api_trend = _trend_html(data["api_cost"], trend.get("api_cost_prev"))
    sub_trend = _trend_html(data["sub_tokens"], trend.get("sub_tokens_prev"))
    local_trend = _trend_html(data["local_tokens"], trend.get("local_tokens_prev"))
    req_trend = _trend_html(data["total_requests"], trend.get("total_requests_prev"))

    return f"""<div class="stats">
  <div class="stat-card">
    <div class="stat-label">API Spend</div>
    <div class="stat-value clr-green">{fmt_cost(data['api_cost'])}</div>
    <div class="stat-sub">paid API calls</div>
    {api_trend}
    {spend_spark}
  </div>
  <div class="stat-card">
    <div class="stat-label">Subscription Usage</div>
    <div class="stat-value clr-blue">{fmt_tokens(data['sub_tokens'])}</div>
    <div class="stat-sub">tokens &middot; included in plan</div>
    {sub_trend}
    {sub_spark}
  </div>
  <div class="stat-card">
    <div class="stat-label">Local Usage</div>
    <div class="stat-value clr-purple">{fmt_tokens(data['local_tokens'])}</div>
    <div class="stat-sub">tokens &middot; free</div>
    {local_trend}
    {local_spark}
  </div>
  <div class="stat-card">
    <div class="stat-label">Total Requests</div>
    <div class="stat-value">{data['total_requests']:,}</div>
    <div class="stat-sub">{fmt_tokens(data['total_tokens'])} total tokens</div>
    {req_trend}
    {req_spark}
  </div>
</div>"""


def _build_svg_spend_chart(data):
    """Build a stacked area SVG spend chart."""
    daily_raw = data["daily_raw"]
    days = data["chart_days"]

    if not daily_raw:
        return '<div class="chart-empty">No spend data for this period</div>'

    # Organize by day
    day_data = {}
    for r in daily_raw:
        d = r["day"]
        prov = r["prov"] or "unknown"
        if d not in day_data:
            day_data[d] = {}
        day_data[d][prov] = day_data[d].get(prov, 0) + (r["cost"] or 0)

    today = datetime.now().date()
    date_range = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

    # Collect all providers with any spend
    all_provs = set()
    for d in date_range:
        all_provs.update(day_data.get(d, {}).keys())
    all_provs = sorted(all_provs)

    if not all_provs:
        return '<div class="chart-empty">No spend data for this period</div>'

    # Compute daily totals per provider
    day_stacks = {}
    max_total = 0
    for d in date_range:
        dd = day_data.get(d, {})
        day_stacks[d] = {p: dd.get(p, 0) for p in all_provs}
        tot = sum(day_stacks[d].values())
        if tot > max_total:
            max_total = tot

    if max_total == 0:
        return '<div class="chart-empty">No spend data for this period</div>'

    # SVG dimensions
    W, H = 520, 220
    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 32
    cw = W - pad_l - pad_r
    ch = H - pad_t - pad_b
    n = len(date_range)
    x_step = cw / max(n - 1, 1)

    def x_of(i):
        return pad_l + i * x_step

    def y_of(v):
        return pad_t + ch - (v / max_total) * ch

    svg_parts = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"'
        f' style="width:100%;height:100%;overflow:visible">'
    ]

    # Defs: gradients
    svg_parts.append("<defs>")
    for prov in all_provs:
        color = _provider_color(prov)
        if color.startswith("#") and len(color) == 7:
            r2, g2, b2 = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            top_c = f"rgba({r2},{g2},{b2},0.4)"
            bot_c = f"rgba({r2},{g2},{b2},0.05)"
        else:
            top_c, bot_c = "rgba(255,255,255,0.4)", "rgba(255,255,255,0.05)"
        svg_parts.append(
            f'<linearGradient id="grad_{prov}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{top_c}"/>'
            f'<stop offset="100%" stop-color="{bot_c}"/>'
            f'</linearGradient>'
        )
    svg_parts.append("</defs>")

    # Y-axis gridlines
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        yg = y_of(frac * max_total)
        val_label = f"${frac * max_total:.3f}" if max_total < 0.1 else f"${frac * max_total:.2f}"
        svg_parts.append(
            f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{W - pad_r}" y2="{yg:.1f}"'
            f' stroke="#2a2d3a" stroke-width="1"/>'
        )
        if frac > 0:
            svg_parts.append(
                f'<text x="{pad_l - 4}" y="{yg + 4:.1f}" text-anchor="end"'
                f' font-size="9" fill="#6e7681">{_escape_html(val_label)}</text>'
            )

    # Stacked area paths per provider
    # Build cumulative stacks
    cum_bottom = {d: 0.0 for d in date_range}

    for prov in all_provs:
        color = _provider_color(prov)
        # Points for this provider's band
        top_pts = []
        bot_pts = []
        for i, d in enumerate(date_range):
            xp = x_of(i)
            b = cum_bottom[d]
            t = b + day_stacks[d][prov]
            top_pts.append((xp, y_of(t)))
            bot_pts.append((xp, y_of(b)))
            cum_bottom[d] = t

        # Build smooth path using linear segments (bezier would be ideal but
        # linear is cleaner for financial data)
        if len(top_pts) < 2:
            continue

        def pts_to_d(pts):
            d_str = f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"
            for px, py in pts[1:]:
                d_str += f" L {px:.1f},{py:.1f}"
            return d_str

        top_d = pts_to_d(top_pts)
        # Area: top path forward, then bottom path reversed
        rev_bot = list(reversed(bot_pts))
        area_d = top_d
        for px, py in rev_bot:
            area_d += f" L {px:.1f},{py:.1f}"
        area_d += " Z"

        # Stroke path (top line only)
        stroke_d = pts_to_d(top_pts)

        svg_parts.append(
            f'<path d="{area_d}" fill="url(#grad_{prov})" opacity="0.85"/>'
        )
        svg_parts.append(
            f'<path d="{stroke_d}" fill="none" stroke="{color}" stroke-width="1.8"'
            f' stroke-linejoin="round"'
            f' style="stroke-dasharray:1000;stroke-dashoffset:1000;'
            f'animation:draw-path 2.8s ease forwards"/>'
        )

    # X-axis date labels
    label_every = max(1, n // 7)
    for i, d in enumerate(date_range):
        if i % label_every == 0 or i == n - 1:
            xp = x_of(i)
            svg_parts.append(
                f'<text x="{xp:.1f}" y="{H - 4}" text-anchor="middle"'
                f' font-size="9" fill="#6e7681">{d[5:]}</text>'
            )

    # Invisible overlay rects for hover (one per day column)
    col_w = x_step if n > 1 else cw
    for i, d in enumerate(date_range):
        xp = x_of(i) - col_w / 2
        svg_parts.append(
            f'<rect class="chart-hover-col" x="{xp:.1f}" y="{pad_t}"'
            f' width="{col_w:.1f}" height="{ch}"'
            f' fill="transparent" data-day="{d}"'
            f' data-costs="{_escape_html(json.dumps(day_stacks[d]))}"'
            f' data-total="{sum(day_stacks[d].values()):.5f}"/>'
        )

    # Vertical hover line
    svg_parts.append(
        f'<line id="hoverLine" x1="0" y1="{pad_t}" x2="0" y2="{pad_t + ch}"'
        f' stroke="#3d4250" stroke-width="1" opacity="0" stroke-dasharray="3,3"/>'
    )

    svg_parts.append("</svg>")

    svg_parts.append(
        '<style>'
        '@keyframes draw-path{to{stroke-dashoffset:0}}'
        '</style>'
    )

    tooltip_html = '<div class="svg-tooltip" id="spendTooltip"></div>'

    return (
        f'<div class="spend-svg-wrap" id="spendChartWrap">'
        + "".join(svg_parts)
        + tooltip_html
        + "</div>"
    )


def _build_model_breakdown(data):
    models = data["models"]
    if not models:
        return '<div class="chart-empty">No model data yet</div>'

    max_tok = max((m["inp"] + m["outp"] for m in models), default=1)
    if max_tok == 0:
        max_tok = 1

    items = []
    for m in models:
        model_name = m["model"] or "unknown"
        prov = m["provider"] or "unknown"
        ptype = m.get("ptype", "api")
        tok = m["inp"] + m["outp"]
        bar_w = int((tok / max_tok) * 100)

        if ptype == "subscription":
            cost_html = '<span class="model-cost" style="color:#58a6ff">included</span>'
            bar_color = "#58a6ff"
        elif ptype == "local":
            cost_html = '<span class="model-cost" style="color:#a78bfa">free</span>'
            bar_color = "#a78bfa"
        else:
            cost_html = f'<span class="model-cost clr-green">{fmt_cost(m["cost"])}</span>'
            bar_color = "#22c55e"

        items.append(
            f'<div class="model-item">'
            f'<div class="model-row">'
            f'<div>'
            f'<div class="model-name" title="{_escape_html(model_name)}">{_escape_html(model_name)}</div>'
            f'<div class="model-meta">'
            f"{provider_badge_html(prov)} "
            f"<span>{m['cnt']} reqs</span> "
            f"<span>{fmt_tokens(tok)} tokens</span>"
            f"</div>"
            f"</div>"
            f"{cost_html}"
            f"</div>"
            f'<div class="usage-bar-bg">'
            f'<div class="usage-bar-fill" style="width:{bar_w}%;background:{bar_color}"></div>'
            f"</div>"
            f"</div>"
        )

    return '<div class="model-list">' + "\n".join(items) + "</div>"


def _build_heatmap(data):
    """Build a 30-day x 24-hour activity heatmap."""
    heatmap_data = data.get("heatmap", [])

    # Build lookup dict
    counts = {}
    for row in heatmap_data:
        counts[(row["day"], int(row["hour"]))] = int(row["cnt"])

    today = datetime.now().date()
    date_range = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]

    max_cnt = max(counts.values()) if counts else 1
    if max_cnt == 0:
        max_cnt = 1

    def cell_color(cnt):
        if cnt == 0:
            return "#1a2332"
        frac = cnt / max_cnt
        if frac < 0.15:
            return "rgba(14,68,41,.6)"
        if frac < 0.4:
            return "rgba(0,109,50,.8)"
        if frac < 0.75:
            return "rgba(38,166,65,.9)"
        return "rgba(57,211,83,1.0)"

    # Day labels (show MM-DD every 5 days)
    day_labels_html = ""
    for i, d in enumerate(date_range):
        label = d[5:] if i % 5 == 0 else ""
        day_labels_html += f'<div class="heatmap-day-label">{label}</div>'

    # Rows: 24 hours
    rows_html = ""
    for h in range(24):
        row_cells = ""
        for d in date_range:
            cnt = counts.get((d, h), 0)
            color = cell_color(cnt)
            # Format tooltip: e.g. "March 24, 14:00 — 42 requests"
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                label_day = dt.strftime("%B %-d")
            except Exception:
                label_day = d
            tooltip = f"{label_day}, {h:02d}:00 — {cnt} requests"
            row_cells += (
                f'<div class="heatmap-cell" style="background:{color}" title="{_escape_html(tooltip)}"></div>'
            )
        rows_html += f'<div class="heatmap-row">{row_cells}</div>'

    # Hour labels: show 0, 6, 12, 18, 24 positions
    hour_labels_html = ""
    for h in [0, 6, 12, 18, 23]:
        label = str(h) if h < 24 else "24"
        hour_labels_html += f"<span>{label}</span>"

    return f"""<div class="heatmap-section">
  <div class="section-title">Activity Heatmap — Last 30 Days</div>
  <div class="heatmap-scroll">
    <div class="heatmap-grid-wrap">
      <div class="heatmap-hour-labels">{hour_labels_html}</div>
      <div class="heatmap-inner">
        <div class="heatmap-day-labels">{day_labels_html}</div>
        <div class="heatmap-rows">{rows_html}</div>
      </div>
    </div>
  </div>
</div>"""


def _build_insights(data):
    """Build auto-generated insights panel."""
    ir = data.get("insights_raw", {})
    time_range = data.get("time_range", "today")

    cards = []

    if ir.get("busiest_hour"):
        cards.append(
            ('<span class="insight-emoji">&#9200;</span>',
             "Peak Hour",
             f"Most active at {ir['busiest_hour']}")
        )

    if ir.get("top_model") and ir.get("top_model_pct", 0) > 0:
        model_short = (ir["top_model"] or "")[:30]
        cards.append(
            ('<span class="insight-emoji">&#129302;</span>',
             "Top Model",
             f"{_escape_html(model_short)} — {ir['top_model_pct']}% of requests")
        )

    if ir.get("avg_latency_ms") is not None and ir["avg_latency_ms"] > 0:
        cards.append(
            ('<span class="insight-emoji">&#9889;</span>',
             "Avg Latency",
             fmt_latency(ir["avg_latency_ms"]) + " average response time")
        )

    if ir.get("distinct_models", 0) > 0:
        cards.append(
            ('<span class="insight-emoji">&#128230;</span>',
             "Model Variety",
             f"{ir['distinct_models']} distinct models used")
        )

    if ir.get("stream_pct", 0) > 0:
        cards.append(
            ('<span class="insight-emoji">&#128225;</span>',
             "Streaming",
             f"{ir['stream_pct']}% of requests are streaming")
        )

    if ir.get("sub_token_pct", 0) > 0:
        cards.append(
            ('<span class="insight-emoji">&#9729;</span>',
             "Subscription",
             f"{ir['sub_token_pct']}% of tokens via subscription (free tier)")
        )

    if ir.get("cost_per_1k") is not None and ir["cost_per_1k"] > 0:
        cards.append(
            ('<span class="insight-emoji">&#128176;</span>',
             "API Efficiency",
             f"${ir['cost_per_1k']:.4f} per 1K tokens")
        )

    if not cards:
        return ""

    card_html = ""
    for emoji, title, desc in cards:
        card_html += (
            f'<div class="insight-card">'
            f'<div class="insight-emoji">{emoji}</div>'
            f'<div class="insight-title">{title}</div>'
            f'<div class="insight-desc">{desc}</div>'
            f'</div>'
        )

    return f"""<div class="insights-section">
  <div class="section-title">Insights</div>
  <div class="insights-grid">{card_html}</div>
</div>"""


def _build_requests_table(data, time_range="today", page=1):
    """Build the recent requests table with expandable rows."""
    requests = data["requests"]
    if not requests:
        return (
            '<div class="table-wrap">'
            '<div class="chart-empty" style="padding:40px">'
            "No requests in this time range"
            "</div></div>"
        )

    rows_html = []
    for idx, r in enumerate(requests):
        ts = relative_time(r["timestamp"])
        prov = r["provider"] or "unknown"
        ptype = r.get("ptype", "api")
        model_name = _escape_html(r["model"] or "unknown")
        inp = fmt_tokens(r["input_tokens"])
        out = fmt_tokens(r["output_tokens"])
        lat = fmt_latency(r["latency_ms"])
        prov_color = _provider_color(prov)

        if ptype == "subscription":
            cost_td = '<span class="cost-sub">included</span>'
        elif ptype == "local":
            cost_td = '<span class="cost-local">free</span>'
        else:
            cost_td = f'<span class="cost-api">{fmt_cost(r["cost_usd"])}</span>'

        stream_html = ""
        if r.get("is_streaming"):
            stream_html = '<span class="stream-badge">STREAM</span>'

        # Detail data for JS
        detail = {
            "cached_tokens": r.get("cached_tokens", 0),
            "reasoning_tokens": r.get("reasoning_tokens", 0),
            "tokens_per_second": r.get("tokens_per_second", 0),
            "time_to_first_token_ms": r.get("time_to_first_token_ms", 0),
            "streaming": bool(r.get("is_streaming")),
            "error_message": r.get("error_message", "") or "",
            "source_tag": r.get("source_tag", "") or "",
        }
        detail_json = _escape_html(json.dumps(detail))
        row_id = f"row{idx}"
        detail_id = f"detail{idx}"

        rows_html.append(
            f'<tr class="req-row" id="{row_id}" data-detail="{detail_json}" data-detail-id="{detail_id}">'
            f'<td class="td-time" style="border-left:3px solid {prov_color}">{ts}</td>'
            f"<td>{provider_badge_html(prov)}</td>"
            f'<td class="td-model" title="{model_name}">{model_name}</td>'
            f"<td>{inp}</td>"
            f"<td>{out}</td>"
            f"<td>{cost_td}</td>"
            f'<td class="latency">{lat}</td>'
            f"<td>{stream_html}<span class='expand-chevron'>&#9660;</span></td>"
            f"</tr>"
            f'<tr class="detail-row" id="{detail_id}">'
            f'<td colspan="8"><div class="detail-inner"><div class="detail-content"></div></div></td>'
            f"</tr>"
        )

    load_more_html = ""
    if len(requests) >= 50:
        next_page = page + 1
        load_more_html = (
            f'<a class="load-more" href="?range={time_range}&page={next_page}">'
            f"Load more &rarr;</a>"
        )

    return (
        '<div class="table-wrap"><table>'
        "<tr>"
        "<th>Time</th><th>Provider</th><th>Model</th>"
        "<th>Input</th><th>Output</th><th>Cost</th>"
        "<th>Latency</th><th>Type</th>"
        "</tr>"
        + "\n".join(rows_html)
        + "</table>"
        + load_more_html
        + "</div>"
    )


# ---------------------------------------------------------------------------
# JavaScript (built as f-string, passed as $page_scripts template variable)
# ---------------------------------------------------------------------------

def _build_page_scripts(data):
    """Build the inline <script> block as a Python f-string."""
    activity_60s = data.get("activity_60s", [])
    recent_count = len(activity_60s)

    # Build JS activity dots array
    now_ts = datetime.now()

    def ts_to_pct(ts_str):
        try:
            ts = datetime.fromisoformat(
                ts_str.replace("T", " ").replace("Z", "").split(".")[0]
            )
            diff = (now_ts - ts).total_seconds()
            # Use 300s (5 min) window, or spread evenly if showing recent history
            window = 300.0
            if len(activity_60s) > 0:
                # Calculate actual time span of the data
                first_ts = datetime.fromisoformat(
                    activity_60s[0].get("timestamp", "").replace("T", " ").replace("Z", "").split(".")[0]
                )
                span = max((now_ts - first_ts).total_seconds(), 60.0)
                window = min(span, 300.0)
            pct = max(0.0, min(100.0, (1.0 - diff / window) * 100.0))
            return round(pct, 1)
        except Exception:
            return 50.0

    dots_list = []
    for act in activity_60s:
        prov = (act.get("provider") or "unknown").lower()
        color = PROVIDER_COLORS.get(prov, "#8b949e")
        pct = ts_to_pct(act.get("timestamp", ""))
        dots_list.append({
            "ts": act.get("timestamp", ""),
            "prov": prov,
            "color": color,
            "pct": pct,
        })

    activity_dots_json = json.dumps(dots_list)
    provider_colors_json = json.dumps(PROVIDER_COLORS)

    # Build daily chart data for JS
    daily_raw = data.get("daily_raw", [])
    chart_days = data.get("chart_days", 7)
    today = datetime.now().date()
    date_range = [(today - timedelta(days=i)).isoformat() for i in range(chart_days - 1, -1, -1)]

    day_map = {}
    for r in daily_raw:
        d = r["day"]
        prov = r["prov"] or "unknown"
        if d not in day_map:
            day_map[d] = {}
        day_map[d][prov] = day_map[d].get(prov, 0) + (r["cost"] or 0)

    chart_data_list = []
    for d in date_range:
        chart_data_list.append({"day": d, "costs": day_map.get(d, {})})

    daily_chart_data_json = json.dumps(chart_data_list)
    recent_count_js = recent_count

    # Dominant provider for flow color
    prov_counts = {}
    for act in activity_60s:
        p = (act.get("provider") or "unknown").lower()
        prov_counts[p] = prov_counts.get(p, 0) + 1
    dominant_prov = max(prov_counts, key=lambda k: prov_counts[k]) if prov_counts else "openai"
    dominant_color = PROVIDER_COLORS.get(dominant_prov, "#10a37f")

    script = f"""<script>
// Injected data
var activityDots = {activity_dots_json};
var providerColors = {provider_colors_json};
var dailyChartData = {daily_chart_data_json};
var recentCount = {recent_count_js};
var dominantColor = "{dominant_color}";

// ── Sticky nav ──────────────────────────────────────────
function initStickyNav() {{
  var nav = document.getElementById('stickyNav');
  if (!nav) return;
  var shown = false;
  window.addEventListener('scroll', function() {{
    var y = window.scrollY || window.pageYOffset;
    if (y > 120 && !shown) {{
      nav.classList.add('visible');
      shown = true;
    }} else if (y <= 120 && shown) {{
      nav.classList.remove('visible');
      shown = false;
    }}
  }});
}}

// ── Token flow animation ─────────────────────────────────
function initTokenFlow(activityLevel) {{
  var container = document.getElementById('tokenFlow');
  if (!container) return;
  var baseDuration = 4.0;
  var minDuration = 0.8;
  var speedFactor = Math.max(minDuration, baseDuration - activityLevel * 0.3);
  var numDots = Math.min(20, 4 + activityLevel * 2);

  for (var i = 0; i < numDots; i++) {{
    var dot = document.createElement('div');
    dot.className = 'flow-dot';
    var size = 4 + Math.random() * 6;
    var top = 10 + Math.random() * 60;
    var delay = Math.random() * speedFactor;
    var dur = speedFactor * (0.8 + Math.random() * 0.4);
    dot.style.cssText = (
      'width:' + size + 'px;height:' + size + 'px;' +
      'top:' + top + 'px;' +
      'background:' + dominantColor + ';' +
      'box-shadow:0 0 ' + (size * 1.5) + 'px ' + dominantColor + ';' +
      'animation-duration:' + dur + 's;' +
      'animation-delay:' + delay + 's;'
    );
    container.appendChild(dot);
  }}
}}

// ── Activity feed ────────────────────────────────────────
function initActivityFeed(dots, count) {{
  var timeline = document.getElementById('activityTimeline');
  var counter = document.getElementById('activityCount');
  if (!timeline) return;

  if (count === 0) {{
    timeline.innerHTML = '<div class="activity-waiting"><span class="breathing">&#9679;</span> Waiting for requests...</div>';
    if (counter) counter.textContent = 'No recent activity — showing last known requests';
    return;
  }}

  timeline.innerHTML = '';
  dots.forEach(function(d, i) {{
    var dot = document.createElement('div');
    dot.className = 'activity-dot' + (i >= dots.length - 3 ? ' new-dot' : '');
    dot.style.cssText = (
      'left:' + d.pct + '%;' +
      'background:' + d.color + ';' +
      'box-shadow:0 0 6px ' + d.color + ';'
    );
    dot.title = d.prov + ' — ' + d.ts;
    timeline.appendChild(dot);
  }});

  if (counter) {{
    counter.textContent = count + ' request' + (count === 1 ? '' : 's') + ' in the last 5 minutes';
  }}
}}

// ── SVG Spend chart hover ────────────────────────────────
function initSpendChart() {{
  var wrap = document.getElementById('spendChartWrap');
  if (!wrap) return;
  var tooltip = document.getElementById('spendTooltip');
  var hoverLine = document.getElementById('hoverLine');
  var cols = wrap.querySelectorAll('.chart-hover-col');
  var provColors = providerColors;

  cols.forEach(function(col) {{
    col.addEventListener('mouseenter', function(e) {{
      if (!tooltip) return;
      var day = col.getAttribute('data-day');
      var total = parseFloat(col.getAttribute('data-total') || '0');
      var costsStr = col.getAttribute('data-costs') || '{{}}';
      var costs;
      try {{ costs = JSON.parse(costsStr); }} catch(ex) {{ costs = {{}}; }}

      var lines = '<strong>' + day + '</strong><br>';
      lines += 'Total: $' + total.toFixed(4) + '<br>';
      var provs = Object.keys(costs).sort();
      provs.forEach(function(p) {{
        if (costs[p] > 0) {{
          var clr = provColors[p] || '#8b949e';
          lines += '<span style="color:' + clr + '">' + p + '</span>: $' + costs[p].toFixed(4) + '<br>';
        }}
      }});
      tooltip.innerHTML = lines;
      tooltip.classList.add('visible');

      // Move hover line
      var svgEl = wrap.querySelector('svg');
      if (svgEl && hoverLine) {{
        var rect = col.getBoundingClientRect();
        var svgRect = svgEl.getBoundingClientRect();
        var cx = rect.left + rect.width / 2 - svgRect.left;
        var vb = svgEl.viewBox.baseVal;
        var scaleX = vb.width / svgRect.width;
        var svgX = cx * scaleX;
        hoverLine.setAttribute('x1', svgX);
        hoverLine.setAttribute('x2', svgX);
        hoverLine.setAttribute('opacity', '1');
      }}
    }});

    col.addEventListener('mousemove', function(e) {{
      if (!tooltip) return;
      var wrapRect = wrap.getBoundingClientRect();
      var tx = e.clientX - wrapRect.left + 12;
      var ty = e.clientY - wrapRect.top - 10;
      if (tx + 180 > wrapRect.width) tx = e.clientX - wrapRect.left - 180;
      tooltip.style.left = tx + 'px';
      tooltip.style.top = ty + 'px';
    }});

    col.addEventListener('mouseleave', function() {{
      if (tooltip) tooltip.classList.remove('visible');
      if (hoverLine) hoverLine.setAttribute('opacity', '0');
    }});
  }});
}}

// ── Expandable rows ──────────────────────────────────────
function initExpandableRows() {{
  var rows = document.querySelectorAll('.req-row');
  rows.forEach(function(row) {{
    row.addEventListener('click', function() {{
      var detailId = row.getAttribute('data-detail-id');
      var detailRow = document.getElementById(detailId);
      if (!detailRow) return;

      var isExpanded = row.classList.contains('expanded');
      var inner = detailRow.querySelector('.detail-inner');
      var content = detailRow.querySelector('.detail-content');

      if (isExpanded) {{
        row.classList.remove('expanded');
        detailRow.classList.remove('expanded');
      }} else {{
        // Populate detail content
        var detailStr = row.getAttribute('data-detail') || '{{}}';
        var detail;
        try {{ detail = JSON.parse(detailStr); }} catch(ex) {{ detail = {{}}; }}

        var fields = [
          ['Cached Tokens', detail.cached_tokens || 0],
          ['Reasoning Tokens', detail.reasoning_tokens || 0],
          ['Tokens/sec', detail.tokens_per_second > 0 ? detail.tokens_per_second.toFixed(1) : '—'],
          ['Time to First Token', detail.time_to_first_token_ms > 0 ? detail.time_to_first_token_ms + 'ms' : '—'],
          ['Streaming', detail.streaming ? 'Yes' : 'No'],
          ['Error', detail.error_message || 'None'],
          ['Source Tag', detail.source_tag || '—'],
        ];

        var html = '';
        fields.forEach(function(f) {{
          html += '<div class="detail-field"><span class="detail-key">' + f[0] + '</span><span class="detail-val">' + f[1] + '</span></div>';
        }});
        content.innerHTML = html;

        row.classList.add('expanded');
        detailRow.classList.add('expanded');
      }}
    }});
  }});
}}

// ── Pulse speed ──────────────────────────────────────────
function updatePulseDots(count) {{
  var dots = document.querySelectorAll('.pulse-dot');
  dots.forEach(function(d) {{
    if (count > 5) {{
      d.classList.add('fast');
    }} else {{
      d.classList.remove('fast');
    }}
  }});
}}

// ── Auto refresh ─────────────────────────────────────────
function startAutoRefresh(seconds) {{
  setTimeout(function() {{ location.reload(); }}, seconds * 1000);
}}

// ── Budget management ─────────────────────────────────────
function toggleBudgetPanel() {{
  var panel = document.getElementById('budgetManagePanel');
  if (panel) panel.classList.toggle('open');
}}

function addBudget() {{
  var nameEl = document.getElementById('bName');
  var periodEl = document.getElementById('bPeriod');
  var threshEl = document.getElementById('bThreshold');
  var provEl = document.getElementById('bProvider');
  var name = nameEl ? nameEl.value : '';
  var period = periodEl ? periodEl.value : 'monthly';
  var threshold = parseFloat(threshEl ? threshEl.value : '0');
  var provider = provEl ? provEl.value.trim() : '';

  if (!name.trim()) {{ alert('Please enter a budget name.'); return; }}
  if (!threshold || threshold <= 0) {{ alert('Please enter a valid threshold.'); return; }}

  var body = 'name=' + encodeURIComponent(name.trim()) +
    '&period=' + encodeURIComponent(period) +
    '&threshold=' + encodeURIComponent(threshold);
  if (provider) body += '&provider_filter=' + encodeURIComponent(provider);

  fetch('/api/budgets', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
    body: body
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    if (data.ok) {{ location.reload(); }}
    else {{ alert('Error: ' + (data.error || 'unknown')); }}
  }})
  .catch(function(e) {{ alert('Request failed: ' + e); }});
}}

function deleteBudget(id) {{
  if (!confirm('Delete this budget?')) return;
  fetch('/api/budgets/' + id, {{ method: 'DELETE' }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    if (data.ok) {{ location.reload(); }}
    else {{ alert('Error: ' + (data.error || 'unknown')); }}
  }})
  .catch(function(e) {{ alert('Request failed: ' + e); }});
}}

// ── Init ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {{
  initStickyNav();
  var actLevel = Math.min(10, Math.round(recentCount / 2));
  initTokenFlow(actLevel);
  initActivityFeed(activityDots, recentCount);
  initSpendChart();
  initExpandableRows();
  updatePulseDots(recentCount);
  startAutoRefresh(30);
}});
</script>"""

    return script


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def build_page(time_range, page=1):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    range_label = RANGE_LABELS.get(time_range, "Today")
    range_buttons = _build_range_buttons(time_range)

    try:
        data = _fetch_data(time_range)
    except Exception as e:
        error_body = ERROR_TEMPLATE.substitute(
            error_message=_escape_html(str(e)),
            db_path=_escape_html(DB_PATH),
        )
        empty_scripts = "<script>setTimeout(function(){location.reload()},3000);</script>"
        return PAGE_TEMPLATE.substitute(
            range_label=range_label,
            range_buttons=range_buttons,
            body_content=error_body,
            version=VERSION,
            updated_at=now_str,
            page_scripts=empty_scripts,
        )

    if data["total_requests"] == 0:
        empty_body = EMPTY_TEMPLATE.substitute(
            db_path=_escape_html(DB_PATH),
        )
        empty_scripts = "<script>setTimeout(function(){location.reload()},3000);</script>"
        return PAGE_TEMPLATE.substitute(
            range_label=range_label,
            range_buttons=range_buttons,
            body_content=empty_body,
            version=VERSION,
            updated_at=now_str,
            page_scripts=empty_scripts,
        )

    data["time_range"] = time_range

    # Activity feed section
    activity_60s = data.get("activity_60s", [])
    recent_count = len(activity_60s)
    activity_section = f"""<div class="activity-section">
  <div class="activity-label">Live Activity</div>
  <div class="activity-timeline" id="activityTimeline"></div>
  <div class="activity-count" id="activityCount"></div>
</div>"""

    stats_html = _build_stats_cards(data)
    spend_chart = _build_svg_spend_chart(data)
    model_breakdown = _build_model_breakdown(data)
    heatmap_html = _build_heatmap(data)
    insights_html = _build_insights(data)
    requests_table = _build_requests_table(data, time_range=time_range, page=page)

    # Paid feature sections
    budgets_status = _fetch_budgets_with_status()
    all_budgets = _fetch_all_budgets()
    budget_html = _build_budget_section(budgets_status, all_budgets)

    opt_data = _fetch_optimizer_data()
    optimizer_html = _build_optimizer_section(opt_data)

    projects = _fetch_project_breakdown()
    project_html = _build_project_section(projects)

    body = f"""{activity_section}

{stats_html}

  {budget_html}

  {optimizer_html}

  {project_html}

  <!-- Charts -->
  <div class="charts-row">
    <div class="chart-panel">
      <div class="chart-title">Daily Spend</div>
      {spend_chart}
    </div>
    <div class="chart-panel">
      <div class="chart-title">Model Breakdown</div>
      {model_breakdown}
    </div>
  </div>

  <!-- Heatmap + Insights side by side -->
  <div class="charts-row">
    <div style="flex:1;min-width:0">
      {heatmap_html}
    </div>
    <div style="flex:1;min-width:0">
      {insights_html}
    </div>
  </div>

  <!-- Recent Requests -->
  <div class="table-section">
    <div class="section-title">Recent Requests</div>
    {requests_table}
  </div>"""

    page_scripts = _build_page_scripts(data)

    return PAGE_TEMPLATE.substitute(
        range_label=range_label,
        range_buttons=range_buttons,
        body_content=body,
        version=VERSION,
        updated_at=now_str,
        page_scripts=page_scripts,
    )


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

def _json_response(handler, status, data):
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _api_get_budgets():
    """Return all budgets with current status as JSON."""
    budgets = _fetch_budgets_with_status()
    return {"ok": True, "budgets": budgets}


def _api_create_budget(form_data):
    """Create a new budget from POST form data."""
    name = (form_data.get("name") or [""])[0].strip()
    period = (form_data.get("period") or ["monthly"])[0].strip()
    try:
        threshold = float((form_data.get("threshold") or ["0"])[0])
    except (ValueError, TypeError):
        return {"ok": False, "error": "Invalid threshold value"}
    provider_filter = (form_data.get("provider_filter") or [""])[0].strip() or None

    if not name:
        return {"ok": False, "error": "Name is required"}
    if period not in ("daily", "weekly", "monthly"):
        return {"ok": False, "error": "Period must be daily, weekly, or monthly"}
    if threshold <= 0:
        return {"ok": False, "error": "Threshold must be positive"}

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO budgets (name, period, threshold_usd, provider_filter, enabled, created_at) "
            "VALUES (?, ?, ?, ?, 1, datetime('now'))",
            (name, period, threshold, provider_filter)
        )
        bid = c.lastrowid
        conn.commit()
        conn.close()
        return {"ok": True, "id": bid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_delete_budget(budget_id):
    """Delete a budget by ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM budget_alerts WHERE budget_id=?", (budget_id,))
        c.execute("DELETE FROM budgets WHERE id=?", (budget_id,))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API endpoint: GET /api/budgets
        if path == "/api/budgets":
            _json_response(self, 200, _api_get_budgets())
            return

        params = parse_qs(parsed.query)
        time_range = params.get("range", ["today"])[0]
        if time_range not in RANGE_LABELS:
            time_range = "today"
        try:
            page = int(params.get("page", ["1"])[0])
        except (ValueError, IndexError):
            page = 1

        html = build_page(time_range, page=page).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API endpoint: POST /api/budgets
        if path == "/api/budgets":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else ""
            form_data = parse_qs(raw_body)
            result = _api_create_budget(form_data)
            _json_response(self, 200 if result.get("ok") else 400, result)
            return

        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API endpoint: DELETE /api/budgets/{id}
        if path.startswith("/api/budgets/"):
            try:
                bid = int(path.split("/")[-1])
            except (ValueError, IndexError):
                _json_response(self, 400, {"ok": False, "error": "Invalid budget ID"})
                return
            result = _api_delete_budget(bid)
            _json_response(self, 200 if result.get("ok") else 500, result)
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("0.0.0.0", 4200), DashboardHandler)
    print(f"TokenPulse Web Dashboard v{VERSION}")
    print(f"  -> http://0.0.0.0:4200")
    print(f"  -> Database: {DB_PATH}")
    server.serve_forever()
