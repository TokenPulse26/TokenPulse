#!/usr/bin/env python3
"""TokenPulse Web Dashboard v0.4.0 — full-featured analytics dashboard."""
import sqlite3
import os
import json
import math
import calendar
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from datetime import datetime, timedelta
from string import Template

DB_PATH = os.environ.get(
    "TOKENPULSE_DB",
    os.path.expanduser(
        "~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db"
    ),
)
VERSION = "0.4.0"
PROXY_API_BASE = os.environ.get("TOKENPULSE_PROXY_API", "http://127.0.0.1:4100")

def _fetch_proxy_json(path, timeout=1.2):
    try:
        req = Request(f"{PROXY_API_BASE}{path}", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("status") == "ok":
            return payload
    except Exception:
        return None
    return None


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
<link rel="icon" href="$favicon_href">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b1018;--panel:#171e2c;--panel-soft:#121925;--border:#2a3347;--border-strong:#3a4761;
  --text:#d6dfeb;--text-muted:#94a0b4;--text-soft:#6e7a8f;--title:#f3f7fd;
  --green:#22c55e;--blue:#58a6ff;--amber:#f59e0b;--red:#f85149;--purple:#a78bfa;
  --space:24px;--radius:18px;
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:radial-gradient(circle at top left, rgba(88,166,255,.14), transparent 26%),radial-gradient(circle at top right, rgba(34,197,94,.10), transparent 20%),linear-gradient(180deg,#0a0f18 0%,#0d1320 42%,#0a0e16 100%);color:var(--text);font-family:'Inter',system-ui,-apple-system,sans-serif;line-height:1.5;min-height:100vh}
body.preload .loading-surface{position:relative;overflow:hidden}
body.preload .loading-surface::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.04) 40%, rgba(255,255,255,0) 80%);transform:translateX(-100%);animation:shimmer 1.5s linear infinite}
body.preload .reveal{opacity:.92;transform:none;animation:none}
a{color:inherit;text-decoration:none}
button{font:inherit}
button,.range-btn,.export-btn,.budget-manage-link,.btn-add-budget,.btn-secondary-budget,.btn-edit-budget,.btn-delete-budget,.load-more,.scroll-top{transition:transform .18s ease, background .18s ease, border-color .18s ease, color .18s ease, box-shadow .18s ease}
button:hover,.range-btn:hover,.export-btn:hover,.budget-manage-link:hover,.btn-add-budget:hover,.btn-secondary-budget:hover,.btn-edit-budget:hover,.btn-delete-budget:hover,.load-more:hover,.scroll-top:hover{transform:scale(1.015)}
@keyframes shimmer{to{transform:translateX(100%)}}
@keyframes fade-up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes load-bar{0%{transform:scaleX(0);transform-origin:left}60%{transform:scaleX(.78);transform-origin:left}100%{transform:scaleX(1);transform-origin:left}}
@keyframes live-flash{0%,100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}50%{box-shadow:0 0 0 10px rgba(34,197,94,.08)}}
.reveal{opacity:0;animation:fade-up .55s ease forwards}
.reveal-delay-1{animation-delay:.04s}
.reveal-delay-2{animation-delay:.08s}
.reveal-delay-3{animation-delay:.12s}
.reveal-delay-4{animation-delay:.16s}
.page-progress{position:fixed;top:0;left:0;right:0;height:2px;z-index:140;background:rgba(34,197,94,.08)}
.page-progress::after{content:"";display:block;height:100%;background:linear-gradient(90deg, rgba(34,197,94,.25), #22c55e 50%, rgba(88,166,255,.7));animation:load-bar 1.2s ease forwards;transform-origin:left}

/* Sticky nav */
.sticky-nav{
  position:fixed;top:0;left:0;right:0;z-index:100;
  background:rgba(10,15,24,.88);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 28px;
  transform:translateY(-100%);transition:transform .25s ease;
}
.sticky-nav.visible{transform:translateY(0)}
.brand-lockup{display:flex;align-items:center;gap:10px}
.brand-mark{width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;color:var(--green);filter:drop-shadow(0 0 12px rgba(34,197,94,.18))}
.sticky-nav .wordmark{font-size:16px;font-weight:800;color:var(--title);letter-spacing:-0.5px}
.version-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 9px;border-radius:999px;background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.15);font-size:11px;font-weight:700;color:#b9d7ff}
.sticky-nav .range-bar{display:flex;gap:5px}
@media(max-width:600px){.sticky-nav{display:none}}

/* Layout */
.shell{max-width:1380px;margin:0 auto;padding:30px 28px 84px}
.dashboard-top{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.95fr);gap:18px;align-items:start;margin-bottom:28px}
.dashboard-main,.dashboard-side{display:flex;flex-direction:column;gap:16px}
.secondary-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(290px,.9fr);gap:18px;margin-bottom:28px}
.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:16px}
.section-head.compact{margin-bottom:12px}
.section-kicker{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--blue);margin-bottom:6px}
.section-title{font-size:18px;font-weight:760;color:var(--title);letter-spacing:-.02em;margin-bottom:0}
.section-copy{font-size:13px;color:var(--text-muted);max-width:680px;margin-top:4px}
.section-meta{font-size:11px;color:var(--text-soft);white-space:nowrap}

/* Header */
.header{position:relative;overflow:hidden;border-radius:20px;background:radial-gradient(circle at top right, rgba(34,197,94,.16), transparent 28%),linear-gradient(135deg,rgba(15,23,42,.96),rgba(23,29,43,.94) 45%,rgba(18,24,38,.98));border:1px solid var(--border-strong);margin-bottom:28px;padding:24px 24px 0;box-shadow:0 18px 60px rgba(0,0,0,.24)}
.header::after{content:"";position:absolute;right:-80px;bottom:-120px;width:280px;height:280px;border-radius:50%;background:radial-gradient(circle, rgba(88,166,255,.16), transparent 62%);pointer-events:none}
.header-top{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:12px}
.header-left{display:flex;align-items:flex-start;gap:14px}
.header-copy{display:flex;flex-direction:column;gap:6px}
.wordmark{font-size:28px;font-weight:800;color:var(--title);letter-spacing:-0.6px}
.header-subtitle{font-size:13px;color:var(--text-muted);max-width:720px}
.live-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(34,197,94,0.1);color:#22c55e;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600}
.live-badge.has-update{animation:live-flash .9s ease 2}
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
.range-bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.range-pill-group{display:inline-flex;gap:6px;align-items:center;padding:4px;border-radius:999px;border:1px solid rgba(255,255,255,.05);background:rgba(9,13,21,.66);position:relative;overflow:hidden}
.range-indicator{position:absolute;top:4px;left:4px;height:calc(100% - 8px);border-radius:999px;background:linear-gradient(135deg, rgba(34,197,94,.92), rgba(88,166,255,.75));box-shadow:0 8px 24px rgba(34,197,94,.2);transition:left .22s ease,width .22s ease,opacity .22s ease;opacity:0}
.range-btn{position:relative;z-index:1;padding:8px 16px;border-radius:999px;font-size:13px;font-weight:600;background:transparent;border:1px solid transparent;color:var(--text-muted);cursor:pointer}
.range-btn:hover{color:#e6edf3;background:rgba(255,255,255,.04)}
.range-btn.active{color:#0f1117;font-weight:800}
.export-btn{padding:7px 14px;border-radius:999px;font-size:11px;font-weight:600;background:transparent;border:1px solid var(--border-strong);color:var(--text-muted);cursor:pointer;transition:all .15s ease;text-decoration:none;display:inline-flex;align-items:center;gap:5px}
.export-btn:hover{border-color:var(--blue);color:var(--text)}

/* Activity feed */
.activity-section,.stats .stat-card,.budget-section,.forecast-section,.optimizer-section,.project-section,.reliability-section,.chart-panel,.error-section,.heatmap-section,.insights-section,.table-wrap{background:linear-gradient(180deg, rgba(23,30,44,.98), rgba(19,25,37,.98));border:1px solid var(--border);border-radius:var(--radius)}
.activity-section,.budget-section,.forecast-section,.optimizer-section,.project-section,.reliability-section,.chart-panel,.error-section,.heatmap-section,.insights-section{padding:var(--space)}
.activity-section{padding:18px 22px}
.activity-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--text-muted);margin-bottom:10px}
.activity-timeline{position:relative;height:32px;background:#101623;border-radius:10px;overflow:hidden;margin-bottom:8px;border:1px solid rgba(255,255,255,.04)}
.activity-dot{position:absolute;top:50%;transform:translateY(-50%);width:10px;height:10px;border-radius:50%;opacity:.85;transition:box-shadow .3s}
.activity-dot.new-dot{animation:dot-pulse .8s ease-out}
@keyframes dot-pulse{0%{box-shadow:0 0 0 0 rgba(255,255,255,.6);transform:translateY(-50%) scale(1.4)}100%{box-shadow:0 0 0 8px rgba(255,255,255,0);transform:translateY(-50%) scale(1)}}
.activity-count{font-size:12px;color:var(--text-muted)}
.activity-waiting{display:flex;align-items:center;justify-content:center;height:32px;gap:8px;color:var(--text-soft);font-size:13px}
.breathing{animation:breathe 3s ease-in-out infinite}
@keyframes breathe{0%,100%{opacity:.3}50%{opacity:1}}

/* Stat cards */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-bottom:28px}
.stat-card{padding:var(--space);transition:border-color .2s,transform .2s,background .2s;position:relative;background:linear-gradient(180deg, rgba(23,30,44,.98), rgba(19,25,37,.98));background-clip:padding-box,border-box}
.stat-card::before{content:"";position:absolute;inset:-1px;border-radius:inherit;background:linear-gradient(135deg, rgba(34,197,94,0), rgba(88,166,255,0), rgba(34,197,94,0));opacity:0;transition:opacity .22s ease;z-index:-1}
.stat-card:hover{transform:translateY(-1px)}
.stat-card:hover::before{opacity:1;background:linear-gradient(135deg, rgba(34,197,94,.35), rgba(88,166,255,.12), rgba(34,197,94,.28))}
.stat-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--text-muted);margin-bottom:8px}
.stat-value{font-size:30px;font-weight:800;color:var(--title);line-height:1;letter-spacing:-.03em}
.stat-sub{font-size:11px;color:var(--text-soft);margin-top:6px}
.stat-trend{font-size:11px;margin-top:5px;font-weight:600}
.stat-trend.up{color:var(--green)}
.stat-trend.down{color:var(--red)}
.stat-trend.flat{color:var(--text-muted)}
.stat-sparkline{margin-top:12px;display:block}
.clr-green{color:var(--green)}
.clr-blue{color:var(--blue)}
.clr-purple{color:var(--purple)}

/* Charts row */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:28px}
.chart-panel{min-height:320px;display:flex;flex-direction:column}
.chart-title{font-size:15px;font-weight:700;color:var(--title);margin-bottom:8px}
.chart-copy{font-size:12px;color:var(--text-muted);margin-bottom:18px}
.chart-legend{display:flex;flex-wrap:wrap;gap:8px 10px;margin-bottom:14px}
.chart-legend-item{display:inline-flex;align-items:center;gap:7px;padding:4px 9px;border-radius:999px;background:rgba(255,255,255,.03);font-size:11px;color:var(--text-muted)}
.chart-legend-swatch{width:8px;height:8px;border-radius:999px;box-shadow:0 0 10px currentColor}

/* SVG spend chart */
.spend-svg-wrap{flex:1;position:relative;min-height:240px}
.spend-svg-wrap svg{width:100%;height:100%;display:block}
.svg-tooltip{
  position:absolute;pointer-events:none;background:rgba(10,15,24,.96);
  border:1px solid var(--border-strong);border-radius:10px;padding:10px 14px;
  font-size:12px;color:var(--text);white-space:nowrap;z-index:50;
  opacity:0;transition:opacity .15s;box-shadow:0 4px 12px rgba(0,0,0,.4);
}
.svg-tooltip::after{content:"";position:absolute;left:16px;bottom:-6px;width:10px;height:10px;transform:rotate(45deg);background:rgba(10,15,24,.96);border-right:1px solid var(--border-strong);border-bottom:1px solid var(--border-strong)}
.svg-tooltip.visible{opacity:1}
.chart-empty{flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-soft);font-size:13px}
.empty-state-card{display:flex;align-items:center;justify-content:center;min-height:220px;border:1px dashed rgba(148,160,180,.24);border-radius:16px;background:linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0))}
.empty-state-inner{max-width:460px;padding:28px 24px;text-align:center}
.empty-state-icon{width:54px;height:54px;margin:0 auto 14px;display:flex;align-items:center;justify-content:center;border-radius:18px;background:rgba(34,197,94,.08);color:var(--green);box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.empty-state-title{font-size:20px;font-weight:800;color:var(--title);letter-spacing:-.03em;margin-bottom:8px}
.empty-state-copy{font-size:13px;color:var(--text-muted);line-height:1.7}
.empty-state-hint{margin-top:12px;font-size:12px;color:var(--text-soft)}
.chart-empty .empty-state-card{min-height:100%;width:100%}

/* Model breakdown */
.model-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.model-item{background:#101724;border:1px solid var(--border);border-radius:14px;padding:16px 18px;transition:border-color .2s,transform .2s}
.model-item:hover{border-color:var(--border-strong)}
.model-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.model-name{font-size:13px;font-weight:600;color:var(--title);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
.model-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.model-meta span{font-size:11px;color:var(--text-muted)}
.model-cost{font-size:15px;font-weight:700;white-space:nowrap}
.usage-bar-bg{height:6px;background:#2a3347;border-radius:999px;margin-top:12px;overflow:hidden}
.usage-bar-fill{height:6px;border-radius:999px;transition:width .3s ease;box-shadow:0 0 16px currentColor}
.prov-badge{display:inline-flex;align-items:center;gap:7px;padding:3px 9px;border-radius:999px;font-size:10px;font-weight:700;white-space:nowrap;text-transform:capitalize}
.prov-dot{width:8px;height:8px;border-radius:999px;display:inline-block;box-shadow:0 0 12px currentColor}

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
.table-section{margin-bottom:32px}
.section-title{font-size:14px;font-weight:700;color:#f0f6fc;margin-bottom:14px}
.table-wrap{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;overflow:hidden;overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:720px}
th{background:#161922;color:#6e7681;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;padding:12px 16px;text-align:left;white-space:nowrap;border-bottom:1px solid #2a2d3a}
td{padding:13px 16px;font-size:12px;border-top:1px solid rgba(42,45,58,.5);white-space:nowrap}
.req-row{cursor:pointer;transition:background .15s}
.req-row:nth-child(even) td{background:rgba(255,255,255,.02)}
.req-row:hover td{background:rgba(88,166,255,.08) !important}
.req-row td:first-child{border-left:3px solid transparent}
.td-time{color:#6e7681}
.td-model{max-width:200px;overflow:hidden;text-overflow:ellipsis;color:#c9d1d9}
.td-num,.td-latency,.td-cost{text-align:right}
.td-provider{text-align:left}
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
.footer{position:fixed;left:0;right:0;bottom:0;z-index:90;background:rgba(10,15,24,.92);backdrop-filter:blur(12px);border-top:1px solid rgba(255,255,255,.05);padding:10px 18px}
.footer-inner{max-width:1380px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--text-soft)}
.footer-group{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.status-chip{display:inline-flex;align-items:center;gap:8px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.04);color:var(--text-muted)}
.status-dot{width:8px;height:8px;border-radius:999px;background:#586274}
.status-dot.online{background:var(--green);box-shadow:0 0 12px rgba(34,197,94,.35)}
.status-dot.offline{background:var(--red);box-shadow:0 0 12px rgba(248,81,73,.2)}

/* Empty / error */
.empty-state,.error-state{padding:24px 0}
.empty-state code,.error-state code{background:#101724;padding:3px 7px;border-radius:6px;font-size:12px;color:#c9d1d9}

/* Responsive */
@media(max-width:900px){
  .charts-row{grid-template-columns:1fr}
  .stats{grid-template-columns:repeat(2,1fr)}
  .insights-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:600px){
  .shell{padding:16px 14px 88px}
  .stats{grid-template-columns:1fr 1fr;gap:10px}
  .stat-value{font-size:22px}
  .stat-card{padding:16px}
  .wordmark{font-size:20px}
  td,th{padding:8px 10px;font-size:11px}
  .model-name{max-width:140px}
  .insights-grid{grid-template-columns:1fr}
  .footer-inner{flex-direction:column;align-items:flex-start}
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
.btn-secondary-budget{background:#212734;color:#c9d1d9;border:1px solid #2a2d3a;border-radius:7px;padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer}
.btn-secondary-budget:hover{border-color:#58a6ff;color:#f0f6fc}
.budget-list-manage{display:flex;flex-direction:column;gap:8px}
.budget-manage-row{display:flex;align-items:center;justify-content:space-between;background:#161922;border:1px solid #2a2d3a;border-radius:8px;padding:10px 14px;gap:12px}
.budget-manage-info{font-size:13px;color:#c9d1d9}
.budget-manage-sub{font-size:11px;color:#6e7681;margin-top:2px}
.budget-manage-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.budget-toggle{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#8b949e}
.btn-edit-budget,.btn-delete-budget{border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;transition:background .15s}
.btn-edit-budget{background:rgba(88,166,255,.1);color:#58a6ff;border:1px solid rgba(88,166,255,.2)}
.btn-edit-budget:hover{background:rgba(88,166,255,.2)}
.btn-delete-budget{background:rgba(239,68,68,.1);color:#ef4444;border:1px solid rgba(239,68,68,.2)}
.btn-delete-budget:hover{background:rgba(239,68,68,.25)}
.budget-alert-state{margin-top:8px;font-size:11px;color:#8b949e}
.budget-alert-state.active{color:#f59e0b}
.budget-alert-state.resolved{color:#22c55e}
.budget-history{margin-top:16px;padding-top:16px;border-top:1px solid #2a2d3a}
.budget-history-list{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.budget-history-item{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;background:#161922;border:1px solid #2a2d3a;border-radius:10px;padding:12px 14px}
.budget-history-main{display:flex;flex-direction:column;gap:4px}
.budget-history-title{font-size:13px;font-weight:600;color:#f0f6fc}
.budget-history-meta{font-size:11px;color:#8b949e;line-height:1.5}
.budget-history-empty{color:#6e7681;font-size:13px;padding:8px 0 2px}
.budget-history-status{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px}
.budget-history-status.active{color:#f59e0b}
.budget-history-status.resolved{color:#22c55e}
.forecast-budget-list{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.forecast-budget-item{padding:12px 14px;border:1px solid #2a2d3a;border-radius:10px;background:#161922}
.forecast-budget-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.forecast-budget-name{font-size:13px;font-weight:600;color:#f0f6fc}
.forecast-budget-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:10px}
.forecast-budget-metric{font-size:11px;color:#8b949e;line-height:1.5}
.forecast-budget-metric strong{display:block;font-size:14px;color:#f0f6fc}
.forecast-budget-note{font-size:11px;line-height:1.5;margin-top:8px}
.forecast-budget-note.over{color:#f85149}
.forecast-budget-note.warn{color:#f59e0b}
.forecast-budget-note.ok{color:#22c55e}
.forecast-budget-note.caution{color:#f97316}

/* ── Spending Forecast ──────────────────────────────── */
.forecast-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:20px}
.forecast-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin-top:14px}
.forecast-card{background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:18px 20px;transition:border-color .2s}
.forecast-card:hover{border-color:#3d4250}
.forecast-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:8px}
.forecast-value{font-size:24px;font-weight:800;line-height:1}
.forecast-sub{font-size:11px;color:#6e7681;margin-top:6px;line-height:1.5}
.forecast-trend{font-size:11px;margin-top:5px;font-weight:600}
.forecast-trend.over{color:#f85149}
.forecast-trend.under{color:#22c55e}
.forecast-trend.neutral{color:#8b949e}
.clr-amber{color:#f59e0b}
.clr-red{color:#f85149}

/* ── Error Monitor ─────────────────────────────────── */
.error-section{background:#1a1d27;border:1px solid rgba(248,81,73,0.15);border-radius:14px;padding:22px 24px;margin-bottom:20px}
.error-summary-bar{display:flex;align-items:center;gap:12px;padding:12px 16px;background:#161922;border-radius:10px;margin-bottom:14px}
.error-indicator{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.error-indicator.green{background:#22c55e}
.error-indicator.yellow{background:#eab308}
.error-indicator.red{background:#f85149}
.error-summary-text{font-size:13px;color:#c9d1d9}
.error-summary-text strong{color:#f0f6fc}
.error-models{display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.error-model-item{display:flex;align-items:center;justify-content:space-between;background:#161922;border:1px solid #2a2d3a;border-radius:10px;padding:12px 16px;transition:border-color .2s}
.error-model-item:hover{border-color:#3d4250}
.error-model-item.high-error{border-color:rgba(248,81,73,0.3)}
.error-model-left{display:flex;align-items:center;gap:10px}
.error-model-name{font-size:13px;font-weight:600;color:#f0f6fc}
.error-model-stats{display:flex;gap:14px;font-size:12px;color:#8b949e}
.error-rate-badge{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700}
.error-rate-badge.green{background:rgba(34,197,94,0.1);color:#22c55e}
.error-rate-badge.yellow{background:rgba(234,179,8,0.1);color:#eab308}
.error-rate-badge.red{background:rgba(248,81,73,0.15);color:#f85149}
.error-timeline-wrap{margin-bottom:14px}
.error-timeline-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:8px}
.error-timeline-chart{display:flex;align-items:flex-end;gap:2px;height:60px;background:#161922;border-radius:8px;padding:8px 6px 4px}
.error-bar{flex:1;background:#f85149;border-radius:2px 2px 0 0;min-width:4px;position:relative;cursor:default;transition:opacity .15s}
.error-bar:hover{opacity:.8}
.error-bar-empty{flex:1;min-height:2px;min-width:4px;background:rgba(248,81,73,0.1);border-radius:2px}
.error-recent-list{display:flex;flex-direction:column;gap:6px}
.error-recent-item{background:#161922;border:1px solid #2a2d3a;border-radius:8px;padding:10px 14px;cursor:pointer;transition:border-color .2s}
.error-recent-item:hover{border-color:#3d4250}
.error-recent-header{display:flex;align-items:center;justify-content:space-between;gap:10px}
.error-recent-time{font-size:11px;color:#6e7681}
.error-recent-model{font-size:12px;font-weight:600;color:#f0f6fc}
.error-recent-cost{font-size:11px;color:#f85149;font-weight:600}
.error-recent-msg{font-size:11px;color:#8b949e;margin-top:4px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.error-recent-full{display:none;font-size:11px;color:#c9d1d9;margin-top:6px;line-height:1.5;word-break:break-all;background:#0f1117;border-radius:6px;padding:8px 10px}
.error-recent-item.expanded .error-recent-msg{white-space:normal}
.error-recent-item.expanded .error-recent-full{display:block}

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
.reliability-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:20px}
.reliability-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:14px}
.reliability-card{background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:16px 18px}
.reliability-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:8px}
.reliability-value{font-size:24px;font-weight:800;line-height:1;color:#f0f6fc}
.reliability-sub{font-size:11px;color:#6e7681;margin-top:6px}
.reliability-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:14px}
.reliability-list,.anomaly-list{display:flex;flex-direction:column;gap:8px}
.reliability-item,.anomaly-item{background:#161922;border:1px solid #2a2d3a;border-radius:10px;padding:12px 14px}
.reliability-item-header,.anomaly-header{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px}
.reliability-item-name,.anomaly-title{font-size:13px;font-weight:600;color:#f0f6fc}
.reliability-item-meta,.anomaly-meta{display:flex;flex-wrap:wrap;gap:10px;font-size:11px;color:#8b949e}
.reliability-item-stats{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#c9d1d9}
.anomaly-recommendation{margin-top:10px;padding:10px 12px;border-radius:8px;background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.16);font-size:11px;color:#c9d1d9;line-height:1.55}
.anomaly-recommendation strong{color:#f0f6fc}
.severity-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.severity-badge.medium{background:rgba(234,179,8,.12);color:#eab308}
.severity-badge.high{background:rgba(248,81,73,.15);color:#f85149}
.reliability-empty{color:#6e7681;font-size:13px;padding:12px 0}
@media(max-width:900px){.reliability-grid{grid-template-columns:1fr}}
.attention-section{background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;padding:22px 24px;margin-bottom:20px}
.attention-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;margin-top:14px}
.attention-card{background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:16px 18px}
.attention-card.high{border-color:rgba(239,68,68,.35)}
.attention-card.medium{border-color:rgba(245,158,11,.35)}
.attention-card.low{border-color:rgba(34,197,94,.28)}
.attention-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.attention-title{font-size:13px;font-weight:700;color:#f0f6fc}
.attention-body{font-size:12px;color:#c9d1d9;line-height:1.6}
.attention-foot{margin-top:10px;font-size:11px;color:#8b949e;line-height:1.5}
.attention-empty{color:#6e7681;font-size:13px;padding:8px 0 2px}
.attention-pill{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:999px;font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase}
.attention-pill.high{background:rgba(239,68,68,.12);color:#f87171;border:1px solid rgba(239,68,68,.22)}
.attention-pill.medium{background:rgba(245,158,11,.12);color:#f59e0b;border:1px solid rgba(245,158,11,.22)}
.attention-pill.low{background:rgba(34,197,94,.12);color:#22c55e;border:1px solid rgba(34,197,94,.22)}
.project-stat-label{color:#8b949e}
.project-stat-value{color:#c9d1d9;font-weight:600}
.project-cost{font-size:18px;font-weight:800;margin-bottom:8px}
.project-empty{color:#6e7681;font-size:13px;padding:12px 0}

/* ── UX refinement overrides ───────────────────────── */
.primary-grid,.secondary-grid{display:grid;gap:16px;margin-bottom:20px}
.primary-grid{grid-template-columns:minmax(0,1.45fr) minmax(340px,.95fr)}
.secondary-grid{grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr)}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}
.section-heading{display:flex;flex-direction:column;gap:4px}
.section-kicker{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:#58a6ff}
.section-subtitle{font-size:13px;color:#8b949e;line-height:1.5;max-width:70ch}
.attention-section{position:relative;background:linear-gradient(180deg,rgba(88,166,255,.12),rgba(26,29,39,.96) 28%);border-color:rgba(88,166,255,.22);box-shadow:0 18px 50px rgba(0,0,0,.22)}
.attention-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}
.attention-stat{background:rgba(15,17,23,.45);border:1px solid rgba(88,166,255,.12);border-radius:12px;padding:12px 14px}
.attention-stat-label{font-size:11px;font-weight:700;letter-spacing:.7px;text-transform:uppercase;color:#8b949e;margin-bottom:6px}
.attention-stat-value{font-size:24px;font-weight:800;color:#f0f6fc;line-height:1}
.attention-stat-sub{margin-top:6px;font-size:12px;color:#8b949e}
.attention-grid{grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.attention-card{background:rgba(15,17,23,.55);border-width:1px 1px 1px 4px;box-shadow:inset 0 1px 0 rgba(255,255,255,.02)}
.attention-empty{background:#161922;border:1px dashed #2f3545;border-radius:12px;padding:18px}
.budget-section,.forecast-section,.optimizer-section,.project-section,.reliability-section,.error-section,.chart-panel,.insights-section,.heatmap-section,.activity-section,.stat-card{box-shadow:0 10px 26px rgba(0,0,0,.18)}
.budget-section{background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(255,255,255,0));}
.budget-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}
.budget-overview-card{background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:14px 16px}
.budget-overview-label{font-size:11px;font-weight:700;letter-spacing:.7px;text-transform:uppercase;color:#8b949e;margin-bottom:8px}
.budget-overview-value{font-size:22px;font-weight:800;color:#f0f6fc;line-height:1}
.budget-overview-sub{margin-top:6px;font-size:12px;color:#8b949e}
.budget-list{display:flex;flex-direction:column;gap:12px}
.budget-item{margin-bottom:0;background:#161922;border:1px solid #2a2d3a;border-radius:12px;padding:16px}
.budget-header{align-items:flex-start;gap:12px;margin-bottom:10px}
.budget-title{display:flex;flex-direction:column;gap:6px;min-width:0}
.budget-name-row,.budget-summary-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.budget-summary-row{justify-content:space-between}
.budget-meta{gap:8px;flex-wrap:wrap}
.budget-amount{font-size:18px}
.budget-percent{font-size:12px;color:#8b949e;font-weight:700}
.budget-bar-bg{height:10px;border-radius:999px;margin-bottom:10px}
.budget-bar-fill{height:10px;border-radius:999px}
.budget-supporting{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12px;color:#8b949e}
.budget-status-copy{color:#c9d1d9}
.budget-manage-link{display:inline-flex;align-items:center;gap:8px;padding:9px 12px;margin-top:0;background:#161922;border:1px solid #2a2d3a;border-radius:10px;color:#c9d1d9;font-weight:600}
.budget-manage-link:hover{text-decoration:none;border-color:#58a6ff;color:#f0f6fc}
.budget-manage-panel{background:#11151d;border:1px solid #2a2d3a;border-radius:12px;padding:18px;margin-top:16px}
.budget-form{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:18px}
.budget-form-group{min-width:0}
.budget-form-group.span-2{grid-column:span 2}
.budget-form-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.budget-manage-row{padding:12px 14px;border-radius:10px}
.budget-history{margin-top:18px}
.forecast-grid{margin-top:0}
@media(max-width:1080px){.primary-grid,.secondary-grid{grid-template-columns:1fr}.attention-summary,.budget-overview{grid-template-columns:repeat(2,minmax(0,1fr))}.budget-form{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.attention-summary,.budget-overview,.budget-form{grid-template-columns:1fr}.budget-summary-row,.budget-supporting,.section-header{align-items:flex-start;flex-direction:column}.budget-form-group.span-2{grid-column:auto}}
.scroll-top{position:fixed;right:22px;bottom:74px;width:42px;height:42px;border:none;border-radius:999px;background:linear-gradient(135deg, rgba(34,197,94,.92), rgba(88,166,255,.78));color:#081016;box-shadow:0 14px 30px rgba(0,0,0,.28);cursor:pointer;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transform:translateY(10px);z-index:120}
.scroll-top.visible{opacity:1;pointer-events:auto;transform:translateY(0)}
</style>
</head>
<body class="preload">
<div class="page-progress" aria-hidden="true"></div>

<!-- Sticky Nav -->
<nav class="sticky-nav" id="stickyNav">
  <div class="brand-lockup">
    <span class="brand-mark">$pulse_mark_small</span>
    <span class="wordmark">TokenPulse</span>
    <span class="version-badge">v$version</span>
  </div>
  <div class="range-bar">$range_buttons</div>
  <span class="live-badge"><span class="pulse-dot" id="stickyPulseDot"></span> Live</span>
</nav>

<div class="shell">

  <!-- Header with token flow -->
  <div class="header loading-surface reveal">
    <div class="header-top">
      <div class="header-left">
        <span class="brand-mark" style="width:28px;height:28px">$pulse_mark_large</span>
        <div class="header-copy">
          <div class="brand-lockup">
            <span class="wordmark">TokenPulse</span>
            <span class="version-badge">v$version</span>
            <span class="live-badge"><span class="pulse-dot" id="mainPulseDot"></span> Live</span>
          </div>
          <div class="header-subtitle">AI token usage tracking with live spend, reliability, and optimization signals for local and hosted workloads.</div>
        </div>
      </div>
      <div class="range-bar">$range_buttons</div>
    </div>
    <div class="token-flow" id="tokenFlow"></div>
  </div>

  $body_content

  <div class="footer">
    <div class="footer-inner">
      <div class="footer-group">
        <span class="status-chip"><span class="status-dot $proxy_status_class"></span> Proxy $proxy_status_label</span>
        <span>Last request: $last_request_at</span>
        <span>Total requests: $total_requests</span>
      </div>
      <div class="footer-group">
        <span>Updated $updated_at</span>
        <span>v$version</span>
      </div>
    </div>
  </div>
</div>

<button class="scroll-top" id="scrollTopBtn" type="button" aria-label="Scroll to top">&#8593;</button>

$page_scripts
</body>
</html>""")

EMPTY_TEMPLATE = Template(r"""
<div class="empty-state">
  <div class="empty-state-card reveal reveal-delay-1">
    <div class="empty-state-inner">
      <div class="empty-state-icon">$icon_svg</div>
      <h2 class="empty-state-title">Welcome to TokenPulse</h2>
      <p class="empty-state-copy">No request data found yet. Start the local proxy on <code>localhost:4100</code> and route requests through it so the dashboard can track spend, tokens, and reliability.</p>
      <p class="empty-state-hint">Setup hint: keep the dashboard and proxy local, then make a test request to populate the first cards. Database path: <code>$db_path</code></p>
    </div>
  </div>
</div>
""")

ERROR_TEMPLATE = Template(r"""
<div class="error-state">
  <div class="empty-state-card reveal reveal-delay-1">
    <div class="empty-state-inner">
      <div class="empty-state-icon" style="background:rgba(248,81,73,.08);color:#f85149">$icon_svg</div>
      <h2 class="empty-state-title" style="color:#f87171">Database Error</h2>
      <p class="empty-state-copy">Could not connect to the TokenPulse database.</p>
      <p class="empty-state-hint"><code>$error_message</code></p>
      <p class="empty-state-hint">Expected path: <code>$db_path</code></p>
    </div>
  </div>
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
    return (
        f'<span class="prov-badge" style="background:{bg};color:{color}">'
        f'<span class="prov-dot" style="background:{color};color:{color}"></span>'
        f'{_escape_html(label)}'
        f'</span>'
    )


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


def _pulse_mark_svg(size=18):
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<path d="M2 13h4.1l2.1-4.6 3.3 9.2 2.8-6h7.7" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M2 13h4.1l2.1-4.6 3.3 9.2 2.8-6h7.7" '
        'stroke="rgba(34,197,94,.45)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


def _favicon_href():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="18" fill="#0b1018"/>'
        '<path d="M10 34h12l6-13 9 26 8-17h9" '
        'stroke="#22c55e" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def fmt_compact_number(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")
    return f"{int(value):,}"


def fmt_timestamp_full(ts_str):
    if not ts_str:
        return "—"
    try:
        ts = datetime.fromisoformat(
            ts_str.replace("T", " ").replace("Z", "").split(".")[0]
        )
        return ts.strftime("%b %d, %Y %I:%M:%S %p")
    except Exception:
        return ts_str


def _render_empty_state(title, description, hint, icon_svg=None, extra_class=""):
    return (
        f'<div class="empty-state-card {extra_class}">'
        f'<div class="empty-state-inner">'
        f'<div class="empty-state-icon">{icon_svg or _pulse_mark_svg(24)}</div>'
        f'<div class="empty-state-title">{_escape_html(title)}</div>'
        f'<div class="empty-state-copy">{description}</div>'
        f'<div class="empty-state-hint">{hint}</div>'
        f'</div>'
        f'</div>'
    )


def _proxy_status_summary():
    status = _fetch_proxy_json("/health", timeout=0.5)
    if status is not None:
        return True, "online"
    return False, "offline"


def _append_sql_condition(where_clause, condition):
    if where_clause.strip():
        return f"{where_clause} AND {condition}"
    return f" WHERE {condition}"


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
            f"SELECT AVG(latency_ms) as v FROM requests{_append_sql_condition(where, 'latency_ms IS NOT NULL')}"
        )
        lat_row = c.fetchone()
        if lat_row and lat_row["v"]:
            insights_raw["avg_latency_ms"] = round(float(lat_row["v"]), 0)

        # Distinct models
        c.execute(f"SELECT COUNT(DISTINCT model) as cnt FROM requests{where}")
        insights_raw["distinct_models"] = c.fetchone()["cnt"] or 0

        # Streaming pct
        c.execute(
            f"SELECT COUNT(*) as cnt FROM requests{_append_sql_condition(where, 'is_streaming=1')}"
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
    pill_group = '<div class="range-pill-group"><span class="range-indicator" aria-hidden="true"></span>' + "".join(parts) + '</div>'
    return pill_group + f'<a href="/export/csv?range={active}" class="export-btn" title="Export CSV">&#128229; CSV</a>'


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
    proxied = _fetch_proxy_json('/api/budgets')
    if proxied:
        return proxied.get('budgets') or []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Ensure table exists
        try:
            c.execute("SELECT COUNT(*) FROM budgets")
        except Exception:
            conn.close()
            return []

        budgets = _select_budget_rows(c, enabled_only=True)

        results = []
        for b in budgets:
            period = b["period"]
            pf = b["provider_filter"]
            scope_kind = _normalize_budget_scope_kind(b.get("scope_kind")) or "global"
            scope_value = (b.get("scope_value") or "").strip() or None
            try:
                current_spend = _budget_current_spend(c, period, pf, scope_kind, scope_value)
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
                "scope_kind": scope_kind,
                "scope_value": scope_value,
                "enabled": bool(b.get("enabled", 1)),
                "current_spend": current_spend,
                "percentage": pct,
                "is_over": current_spend >= b["threshold_usd"],
                "alert_active": False,
                "last_alert_triggered_at": None,
            })

        _sync_budget_alert_states(conn, results)
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
            rows = _select_budget_rows(c, enabled_only=False)
        except Exception:
            rows = []
        conn.close()
        return rows
    except Exception:
        return []


def _normalize_budget_scope_kind(scope_kind):
    scope = (scope_kind or "").strip().lower()
    if not scope or scope == "global":
        return "global"
    if scope in ("source_tag", "project"):
        return "source_tag"
    return None


def _get_budget_table_columns(cursor):
    cursor.execute("PRAGMA table_info(budgets)")
    return {row[1] for row in cursor.fetchall()}


def _select_budget_rows(cursor, enabled_only):
    columns = _get_budget_table_columns(cursor)
    enabled_where = " WHERE enabled=1" if enabled_only else ""
    if "scope_kind" in columns and "scope_value" in columns:
        cursor.execute(
            "SELECT id, name, period, threshold_usd, provider_filter, "
            "COALESCE(scope_kind, 'global') as scope_kind, scope_value, enabled "
            f"FROM budgets{enabled_where} ORDER BY created_at ASC"
        )
    else:
        cursor.execute(
            "SELECT id, name, period, threshold_usd, provider_filter, "
            "'global' as scope_kind, NULL as scope_value, enabled "
            f"FROM budgets{enabled_where} ORDER BY created_at ASC"
        )
    return [dict(r) for r in cursor.fetchall()]


def _ensure_budget_scope_columns(conn):
    c = conn.cursor()
    columns = _get_budget_table_columns(c)
    if "scope_kind" not in columns:
        c.execute("ALTER TABLE budgets ADD COLUMN scope_kind TEXT NOT NULL DEFAULT 'global'")
    if "scope_value" not in columns:
        c.execute("ALTER TABLE budgets ADD COLUMN scope_value TEXT")


def _ensure_budget_alert_columns(conn):
    c = conn.cursor()
    c.execute("PRAGMA table_info(budget_alerts)")
    columns = {row[1] for row in c.fetchall()}
    if "resolved_at" not in columns:
        c.execute("ALTER TABLE budget_alerts ADD COLUMN resolved_at TEXT")


def _budget_time_expr(period):
    if period == "daily":
        return "datetime('now', 'start of day')"
    if period == "weekly":
        return "datetime('now', '-7 days')"
    if period == "trailing_1":
        return "datetime('now', '-1 days')"
    if period == "trailing_7":
        return "datetime('now', '-7 days')"
    return "datetime('now', '-30 days')"


def _budget_current_spend(cursor, period, provider_filter, scope_kind, scope_value):
    where_parts = [
        f"timestamp >= {_budget_time_expr(period)}",
        "COALESCE(provider_type,'api')='api'",
    ]
    params = []
    if provider_filter:
        where_parts.append("provider=?")
        params.append(provider_filter)
    if scope_kind == "source_tag" and scope_value:
        where_parts.append("COALESCE(source_tag,'')=?")
        params.append(scope_value)
    cursor.execute(
        f"SELECT COALESCE(SUM(cost_usd),0) FROM requests WHERE {' AND '.join(where_parts)}",
        tuple(params)
    )
    return cursor.fetchone()[0] or 0.0


def _budget_scope_label(scope_kind, scope_value):
    if _normalize_budget_scope_kind(scope_kind) == "source_tag" and scope_value:
        return f"project: {scope_value}"
    return "all projects"


def _budget_scope_badge(scope_kind, scope_value):
    label = _budget_scope_label(scope_kind, scope_value)
    return f'<span style="color:#8b949e">{_escape_html(label)}</span>'


def _get_active_budget_alert(cursor, budget_id):
    cursor.execute(
        "SELECT triggered_at FROM budget_alerts WHERE budget_id=? AND resolved_at IS NULL ORDER BY triggered_at DESC LIMIT 1",
        (budget_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    if isinstance(row, sqlite3.Row):
        return row[0]
    return row[0]


def _resolve_budget_alerts(cursor, budget_id):
    cursor.execute(
        "UPDATE budget_alerts SET resolved_at=datetime('now') WHERE budget_id=? AND resolved_at IS NULL",
        (budget_id,),
    )


def _record_budget_alert(cursor, budget_id, current_spend, threshold_usd):
    cursor.execute(
        "INSERT INTO budget_alerts (budget_id, triggered_at, resolved_at, current_spend, threshold_usd) VALUES (?, datetime('now'), NULL, ?, ?)",
        (budget_id, current_spend, threshold_usd),
    )


def _sync_budget_alert_states(conn, statuses):
    c = conn.cursor()
    _ensure_budget_alert_columns(conn)
    triggered_ids = set()
    for status in statuses:
        active_triggered_at = _get_active_budget_alert(c, status["id"])
        status["alert_active"] = bool(active_triggered_at)
        status["last_alert_triggered_at"] = active_triggered_at
        if status["is_over"]:
            if not active_triggered_at:
                _record_budget_alert(c, status["id"], status["current_spend"], status["threshold_usd"])
                status["alert_active"] = True
                status["last_alert_triggered_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                triggered_ids.add(status["id"])
        else:
            if active_triggered_at:
                _resolve_budget_alerts(c, status["id"])
                status["alert_active"] = False
                status["last_alert_triggered_at"] = None
    if triggered_ids:
        conn.commit()
    else:
        conn.commit()
    return triggered_ids



def _fetch_budget_alert_history(limit=20):
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        rows = c.execute(
            "SELECT a.id, a.budget_id, b.name as budget_name, b.period, b.provider_filter,             COALESCE(b.scope_kind, 'global') as scope_kind, b.scope_value,             a.triggered_at, a.resolved_at, a.current_spend, a.threshold_usd             FROM budget_alerts a             INNER JOIN budgets b ON b.id = a.budget_id             ORDER BY a.triggered_at DESC LIMIT ?",
            (max(1, min(int(limit or 20), 200)),)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _fetch_budget_forecasts(budgets):
    proxied = _fetch_proxy_json('/api/budget-forecasts')
    if proxied:
        return proxied.get('forecasts') or []
    forecasts = []
    for budget in budgets or []:
        if not budget.get("enabled", True):
            continue
        period = budget.get("period") or "monthly"
        trailing_days = 1 if period == "daily" else 7
        current_spend = budget.get("current_spend", 0.0) or 0.0
        threshold = budget.get("threshold_usd", 0.0) or 0.0
        average_daily_spend = 0.0
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            average_daily_spend = _budget_current_spend(
                c,
                f"trailing_{trailing_days}",
                budget.get("provider_filter"),
                budget.get("scope_kind"),
                budget.get("scope_value"),
            ) / max(trailing_days, 1)
            conn.close()
        except Exception:
            average_daily_spend = 0.0
        period_days = 1 if period == "daily" else 7 if period == "weekly" else 30
        projected_period_spend = average_daily_spend * period_days
        remaining_budget = threshold - current_spend
        days_until_threshold = None
        if average_daily_spend > 0 and remaining_budget > 0:
            days_until_threshold = remaining_budget / average_daily_spend
        forecasts.append({
            "budget_id": budget.get("id"),
            "budget_name": budget.get("name"),
            "period": period,
            "provider_filter": budget.get("provider_filter"),
            "scope_kind": budget.get("scope_kind"),
            "scope_value": budget.get("scope_value"),
            "current_spend": current_spend,
            "threshold_usd": threshold,
            "trailing_days": trailing_days,
            "average_daily_spend": average_daily_spend,
            "projected_period_spend": projected_period_spend,
            "remaining_budget": remaining_budget,
            "days_until_threshold": days_until_threshold,
            "is_over": bool(budget.get("is_over")),
        })
    return forecasts


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


def _fetch_forecast_data():
    """Fetch cost projection / spending forecast data."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Daily average spend over last 7 days (API only)
        c.execute(
            "SELECT COALESCE(AVG(daily_cost), 0) FROM ("
            "  SELECT date(timestamp) as day, SUM(cost_usd) as daily_cost"
            "  FROM requests"
            "  WHERE provider_type = 'api' AND timestamp >= datetime('now', '-7 days')"
            "  GROUP BY day"
            ")"
        )
        daily_avg = c.fetchone()[0] or 0.0

        # Current month spend so far
        c.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM requests "
            "WHERE provider_type = 'api' AND timestamp >= datetime('now', 'start of month')"
        )
        month_to_date = c.fetchone()[0] or 0.0

        # Last month's total spend
        c.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM requests "
            "WHERE provider_type = 'api' "
            "AND timestamp >= datetime('now', 'start of month', '-1 month') "
            "AND timestamp < datetime('now', 'start of month')"
        )
        last_month_total = c.fetchone()[0] or 0.0

        # Busiest single day cost (last 30 days)
        c.execute(
            "SELECT COALESCE(MAX(daily_cost), 0) FROM ("
            "  SELECT date(timestamp) as day, SUM(cost_usd) as daily_cost"
            "  FROM requests"
            "  WHERE provider_type = 'api' AND timestamp >= datetime('now', '-30 days')"
            "  GROUP BY day"
            ")"
        )
        busiest_day_cost = c.fetchone()[0] or 0.0

        conn.close()

        # Calculate projections
        now = datetime.now()
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        projected_month = daily_avg * days_in_month
        days_elapsed = now.day
        days_remaining = days_in_month - days_elapsed

        # Budget hit date calculation
        budget_hit_date = None  # Will be set if budgets exist

        return {
            "daily_avg": daily_avg,
            "month_to_date": month_to_date,
            "last_month_total": last_month_total,
            "projected_month": projected_month,
            "days_in_month": days_in_month,
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "busiest_day_cost": busiest_day_cost,
        }
    except Exception:
        return {}


def _fallback_model_for(model_name):
    if not model_name:
        return None
    key = model_name.strip().lower()
    return DOWNGRADE_MAP.get(key)


def _reliability_recommendation(kind, model_name, recent_latency, baseline_latency, recent_error_rate):
    fallback_model = _fallback_model_for(model_name)
    if kind == "latency_spike":
        if fallback_model:
            return (
                f"Route time-sensitive work to {fallback_model} until latency settles. "
                f"Keep {model_name} for higher-value prompts only.",
                fallback_model,
            )
        return (
            "Avoid long-running interactive prompts on this model for now. Keep a second provider ready as a manual fallback.",
            None,
        )

    if fallback_model:
        return (
            f"Retry traffic on {fallback_model} or your next-cheapest stable model while {model_name} is erroring. "
            f"This reduces wasted retries and protects interactive flows.",
            fallback_model,
        )
    return (
        "This model is failing more than normal. Add a provider-level fallback or temporarily pin critical work to a more stable model.",
        None,
    )


def _fetch_context_audit_data(time_range):
    """Fetch context audit heuristics from the local proxy when available."""
    proxied = _fetch_proxy_json(f'/api/context-audit?range={time_range}')
    if proxied:
        return proxied.get('context_audit') or {}
    return {}


def _fetch_reliability_data(time_range):
    """Fetch latency/reliability rollups plus anomaly candidates."""
    proxied = _fetch_proxy_json(f'/api/reliability?range={time_range}')
    if proxied:
        return proxied.get('reliability') or {}
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        where = _time_filter_sql(time_range, "WHERE")

        c.execute(
            f"SELECT COUNT(*) as total_requests, "
            f"SUM(CASE WHEN COALESCE(error_message, '') = '' THEN 1 ELSE 0 END) as successful_requests, "
            f"SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) as failed_requests, "
            f"AVG(COALESCE(latency_ms, 0)) as avg_latency_ms, "
            f"SUM(CASE WHEN COALESCE(latency_ms, 0) >= 5000 THEN 1 ELSE 0 END) as slow_requests "
            f"FROM requests{where}"
        )
        row = c.fetchone()
        total_requests = row["total_requests"] or 0
        successful_requests = row["successful_requests"] or 0
        failed_requests = row["failed_requests"] or 0
        avg_latency_ms = float(row["avg_latency_ms"] or 0.0)
        slow_requests = row["slow_requests"] or 0

        success_rate_pct = round((100.0 * successful_requests / total_requests), 1) if total_requests else 100.0
        slow_request_pct = round((100.0 * slow_requests / total_requests), 1) if total_requests else 0.0

        c.execute(
            f"SELECT provider, model, COUNT(*) as total_requests, "
            f"SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) as failed_requests, "
            f"AVG(COALESCE(latency_ms, 0)) as avg_latency_ms, "
            f"MAX(COALESCE(latency_ms, 0)) as max_latency_ms "
            f"FROM requests{where} GROUP BY provider, model "
            f"ORDER BY total_requests DESC, avg_latency_ms DESC LIMIT 8"
        )
        providers = []
        for r in c.fetchall():
            total = r["total_requests"] or 0
            failed = r["failed_requests"] or 0
            providers.append({
                "provider": r["provider"],
                "model": r["model"],
                "total_requests": total,
                "failed_requests": failed,
                "success_rate_pct": round((100.0 * (total - failed) / total), 1) if total else 100.0,
                "avg_latency_ms": float(r["avg_latency_ms"] or 0.0),
                "max_latency_ms": r["max_latency_ms"] or 0,
            })

        c.execute(
            "WITH recent AS ("
            "  SELECT provider, model, COUNT(*) as recent_requests, "
            "         AVG(COALESCE(latency_ms,0)) as recent_avg_latency, "
            "         1.0 * SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) / COUNT(*) as recent_error_rate, "
            "         COALESCE(SUM(cost_usd), 0.0) as recent_cost "
            "  FROM requests WHERE timestamp >= datetime('now', '-24 hours') "
            "  GROUP BY provider, model HAVING COUNT(*) >= 5"
            "), baseline AS ("
            "  SELECT provider, model, COUNT(*) as baseline_requests, "
            "         AVG(COALESCE(latency_ms,0)) as baseline_avg_latency, "
            "         1.0 * SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) / COUNT(*) as baseline_error_rate "
            "  FROM requests WHERE timestamp >= datetime('now', '-8 days') "
            "    AND timestamp < datetime('now', '-24 hours') "
            "  GROUP BY provider, model HAVING COUNT(*) >= 10"
            ") "
            "SELECT recent.provider, recent.model, recent.recent_requests, baseline.baseline_requests, "
            "recent.recent_avg_latency, baseline.baseline_avg_latency, recent.recent_error_rate, baseline.baseline_error_rate, recent.recent_cost "
            "FROM recent JOIN baseline ON recent.provider = baseline.provider AND recent.model = baseline.model"
        )
        anomalies = []
        for r in c.fetchall():
            recent_latency = float(r["recent_avg_latency"] or 0.0)
            baseline_latency = float(r["baseline_avg_latency"] or 0.0)
            recent_error_rate = float(r["recent_error_rate"] or 0.0)
            baseline_error_rate = float(r["baseline_error_rate"] or 0.0)
            recent_cost = float(r["recent_cost"] or 0.0)
            base = {
                "provider": r["provider"],
                "model": r["model"],
                "recent_requests": r["recent_requests"] or 0,
                "baseline_requests": r["baseline_requests"] or 0,
                "recent_cost": recent_cost,
            }
            if baseline_latency > 0 and recent_latency > baseline_latency * 1.5 and (recent_latency - baseline_latency) >= 250:
                recommendation, fallback_model = _reliability_recommendation(
                    "latency_spike", r["model"], recent_latency, baseline_latency, recent_error_rate
                )
                anomalies.append({
                    **base,
                    "kind": "latency_spike",
                    "severity": "high" if recent_latency > baseline_latency * 2.0 else "medium",
                    "summary": f"Latency jumped from {baseline_latency:.0f}ms to {recent_latency:.0f}ms in the last 24h",
                    "recent_value": recent_latency,
                    "baseline_value": baseline_latency,
                    "delta_pct": ((recent_latency - baseline_latency) / baseline_latency * 100.0) if baseline_latency else 0.0,
                    "recommendation": recommendation,
                    "fallback_model": fallback_model,
                })
            if recent_error_rate >= 0.10 and recent_error_rate > baseline_error_rate + 0.05:
                recommendation, fallback_model = _reliability_recommendation(
                    "error_spike", r["model"], recent_latency, baseline_latency, recent_error_rate
                )
                anomalies.append({
                    **base,
                    "kind": "error_spike",
                    "severity": "high" if recent_error_rate >= 0.25 else "medium",
                    "summary": f"Error rate rose from {baseline_error_rate * 100:.1f}% to {recent_error_rate * 100:.1f}% in the last 24h",
                    "recent_value": recent_error_rate * 100,
                    "baseline_value": baseline_error_rate * 100,
                    "delta_pct": (recent_error_rate - baseline_error_rate) * 100.0,
                    "recommendation": recommendation,
                    "fallback_model": fallback_model,
                })

        anomalies.sort(key=lambda item: ((2 if item.get("severity") == "high" else 1), item.get("recent_cost", 0.0), item.get("recent_value", 0)), reverse=True)
        conn.close()
        return {
            "summary": {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "success_rate_pct": success_rate_pct,
                "avg_latency_ms": avg_latency_ms,
                "slow_requests": slow_requests,
                "slow_request_pct": slow_request_pct,
            },
            "providers": providers,
            "anomalies": anomalies[:8],
        }
    except Exception:
        return {}


def _fetch_error_data(time_range):
    """Fetch error monitoring data."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        where = _time_filter_sql(time_range, "WHERE")
        and_clause = _time_filter_sql(time_range, "AND")

        # Total error count and rate for current time range
        c.execute(
            f"SELECT COUNT(*) as total, "
            f"SUM(CASE WHEN error_message IS NOT NULL AND error_message != '' THEN 1 ELSE 0 END) as errors "
            f"FROM requests{where}"
        )
        row = c.fetchone()
        total_requests = row["total"] or 0
        total_errors = row["errors"] or 0
        error_rate = (100.0 * total_errors / total_requests) if total_requests > 0 else 0.0

        # Wasted cost on errors
        c.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0) as wasted "
            f"FROM requests WHERE error_message IS NOT NULL AND error_message != ''{and_clause}"
        )
        wasted_cost = c.fetchone()["wasted"] or 0.0

        # Error rate by model (last 7 days)
        c.execute(
            "SELECT model, provider, "
            "COUNT(*) as total, "
            "SUM(CASE WHEN error_message IS NOT NULL AND error_message != '' THEN 1 ELSE 0 END) as errors, "
            "ROUND(100.0 * SUM(CASE WHEN error_message IS NOT NULL AND error_message != '' THEN 1 ELSE 0 END) / COUNT(*), 1) as error_rate "
            "FROM requests "
            "WHERE timestamp >= datetime('now', '-7 days') "
            "GROUP BY model, provider "
            "HAVING errors > 0 "
            "ORDER BY error_rate DESC"
        )
        error_by_model = [dict(r) for r in c.fetchall()]

        # Error timeline (errors per hour, last 24 hours)
        c.execute(
            "SELECT strftime('%Y-%m-%d %H:00', timestamp) as hour, COUNT(*) as cnt "
            "FROM requests "
            "WHERE error_message IS NOT NULL AND error_message != '' "
            "AND timestamp >= datetime('now', '-24 hours') "
            "GROUP BY hour ORDER BY hour"
        )
        error_timeline = [dict(r) for r in c.fetchall()]

        # Recent errors (last 10)
        c.execute(
            "SELECT timestamp, provider, model, error_message, input_tokens, cost_usd "
            "FROM requests "
            "WHERE error_message IS NOT NULL AND error_message != '' "
            "ORDER BY timestamp DESC LIMIT 10"
        )
        recent_errors = [dict(r) for r in c.fetchall()]

        # Worst model by error rate (for insights)
        worst_model = None
        worst_model_rate = 0.0
        if error_by_model:
            worst_model = error_by_model[0].get("model", "unknown")
            worst_model_rate = error_by_model[0].get("error_rate", 0.0)

        conn.close()
        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "wasted_cost": wasted_cost,
            "error_by_model": error_by_model,
            "error_timeline": error_timeline,
            "recent_errors": recent_errors,
            "worst_model": worst_model,
            "worst_model_rate": worst_model_rate,
        }
    except Exception:
        return {
            "total_requests": 0, "total_errors": 0, "error_rate": 0.0,
            "wasted_cost": 0.0, "error_by_model": [], "error_timeline": [],
            "recent_errors": [], "worst_model": None, "worst_model_rate": 0.0,
        }


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


def _format_budget_alert_time(ts):
    if not ts:
        return ""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %I:%M %p")
    except Exception:
        return ts


def _build_budget_section(budgets, all_budgets, alert_history):
    """Build the budget status section with progress bars."""
    if not budgets:
        status_html = _render_empty_state(
            "No budgets yet",
            "Set spending limits to stay in control as usage grows across providers and projects.",
            "Action hint: open Manage budgets and add a daily, weekly, or monthly threshold.",
            '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 7h16M7 4v6M17 4v6M5 11h14v8H5z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        )
    else:
        items = []
        for b in budgets:
            name = _escape_html(b["name"])
            period = b["period"]
            current = b["current_spend"]
            threshold = b["threshold_usd"]
            pct = min(b["percentage"], 100.0)
            pct_raw = b["percentage"]
            is_over = b["is_over"]
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
            meta_bits = [_budget_scope_badge(b.get("scope_kind"), b.get("scope_value"))]
            if pf:
                meta_bits.append(f'<span style="color:#8b949e">{_escape_html(pf)}</span>')
            meta_html = "".join(meta_bits)
            over_badge = '<span class="over-badge">&#9888; OVER BUDGET</span>' if is_over else ""

            alert_state = ""
            if b.get("alert_active"):
                alert_state = (
                    f'<div class="budget-alert-state active">Active alert since '
                    f'{_escape_html(_format_budget_alert_time(b.get("last_alert_triggered_at")))}</div>'
                )
            elif b.get("last_alert_triggered_at"):
                alert_state = (
                    f'<div class="budget-alert-state resolved">Last alert triggered '
                    f'{_escape_html(_format_budget_alert_time(b.get("last_alert_triggered_at")))}</div>'
                )

            status_copy = 'Already over threshold' if is_over else ('Close to the limit' if pct_raw >= 80 else 'Within budget')
            alert_display = alert_state or f'<div class="budget-alert-state">{fmt_cost(max(threshold-current, 0.0))} remaining before the limit</div>'
            items.append(
                f'<div class="budget-item">'
                f'<div class="budget-header">'
                f'<div class="budget-title">'
                f'<div class="budget-name-row">'
                f'<span class="budget-name">{name}</span>'
                f'<span class="budget-period-badge">{period}</span>'
                f'</div>'
                f'<div class="budget-meta">{meta_html.lstrip(" &middot;")}</div>'
                f'</div>'
                f'<div class="budget-summary-row">'
                f'{over_badge}'
                f'<span class="budget-amount" style="color:{"#ef4444" if is_over else "#f0f6fc"}">{fmt_cost(current)} / {fmt_cost(threshold)}</span>'
                f'<span class="budget-percent">{pct_raw:.0f}% used</span>'
                f'</div>'
                f'</div>'
                f'<div class="budget-bar-bg">'
                f'<div class="{bar_class}" style="width:{pct:.1f}%"></div>'
                f'</div>'
                f'<div class="budget-supporting">'
                f'<div class="budget-status-copy">{status_copy}</div>'
                f'{alert_display}'
                f'</div>'
                f'</div>'
            )
        status_html = "\n".join(items)

    manage_rows = ""
    for b in all_budgets:
        bid = b["id"]
        bname = _escape_html(b["name"])
        period = b["period"]
        threshold = b["threshold_usd"]
        scope_kind = _normalize_budget_scope_kind(b.get("scope_kind")) or "global"
        scope_value = (b.get("scope_value") or "").strip()
        provider_filter = (b.get("provider_filter") or "").strip()
        enabled_checked = "checked" if b.get("enabled", 1) else ""
        meta_parts = [_budget_scope_label(scope_kind, scope_value), provider_filter or "all providers"]
        manage_rows += (
            f'<div class="budget-manage-row" id="bmrow-{bid}" '
            f'data-name="{bname}" data-period="{_escape_html(period)}" '
            f'data-threshold="{threshold}" data-provider="{_escape_html(provider_filter)}" '
            f'data-scope-kind="{_escape_html(scope_kind)}" data-scope-value="{_escape_html(scope_value)}" '
            f'data-enabled="{1 if b.get("enabled", 1) else 0}">'
            f'<div>'
            f'<div class="budget-manage-info">{bname} &mdash; {fmt_cost(threshold)} / {period}</div>'
            f'<div class="budget-manage-sub">{_escape_html(" · ".join(meta_parts))}</div>'
            f'</div>'
            f'<div class="budget-manage-actions">'
            f'<label class="budget-toggle"><input type="checkbox" onchange="toggleBudgetEnabled({bid}, this.checked)" {enabled_checked}> enabled</label>'
            f'<button class="btn-edit-budget" onclick="startBudgetEdit({bid})">Edit</button>'
            f'<button class="btn-delete-budget" onclick="deleteBudget({bid})">Delete</button>'
            f'</div>'
            f'</div>'
        )
    if not manage_rows:
        manage_rows = '<div style="color:#6e7681;font-size:13px">No budgets yet.</div>'

    history_rows = ""
    for item in alert_history or []:
        status_class = "active" if not item.get("resolved_at") else "resolved"
        status_label = "Active" if not item.get("resolved_at") else "Resolved"
        meta_parts = [item.get("period") or "monthly", _budget_scope_label(item.get("scope_kind"), item.get("scope_value"))]
        if item.get("provider_filter"):
            meta_parts.append(item.get("provider_filter"))
        resolved_copy = "Still active"
        if item.get("resolved_at"):
            resolved_copy = f'Resolved {_format_budget_alert_time(item.get("resolved_at"))}'
        history_rows += (
            f'<div class="budget-history-item">'
            f'<div class="budget-history-main">'
            f'<div class="budget-history-title">{_escape_html(item.get("budget_name") or "Budget")}</div>'
            f'<div class="budget-history-meta">'
            f'{_escape_html(" · ".join(meta_parts))}<br>'
            f'Triggered {_escape_html(_format_budget_alert_time(item.get("triggered_at")))} · {_escape_html(resolved_copy)}<br>'
            f'{fmt_cost(item.get("current_spend", 0.0))} / {fmt_cost(item.get("threshold_usd", 0.0))}'
            f'</div>'
            f'</div>'
            f'<div class="budget-history-status {status_class}">{status_label}</div>'
            f'</div>'
        )
    if not history_rows:
        history_rows = '<div class="budget-history-empty">No budget alerts have fired yet.</div>'

    budget_count = len(budgets or [])
    over_count = sum(1 for b in budgets or [] if b.get("is_over"))
    active_alerts = sum(1 for b in budgets or [] if b.get("alert_active"))
    tracked_spend = sum((b.get("current_spend") or 0.0) for b in budgets or [])
    overview_html = f"""<div class="budget-overview">
    <div class="budget-overview-card">
      <div class="budget-overview-label">Tracked budgets</div>
      <div class="budget-overview-value">{budget_count}</div>
      <div class="budget-overview-sub">{active_alerts} active alert{'s' if active_alerts != 1 else ''}</div>
    </div>
    <div class="budget-overview-card">
      <div class="budget-overview-label">Over budget</div>
      <div class="budget-overview-value">{over_count}</div>
      <div class="budget-overview-sub">Budgets already beyond their threshold</div>
    </div>
    <div class="budget-overview-card">
      <div class="budget-overview-label">Spend in tracked budgets</div>
      <div class="budget-overview-value">{fmt_cost(tracked_spend)}</div>
      <div class="budget-overview-sub">Current period spend across visible budgets</div>
    </div>
  </div>"""

    status_html = f'<div class="budget-list">{status_html}</div>' if budgets else status_html

    return f"""<div class="budget-section loading-surface reveal reveal-delay-1">
  <div class="section-header">
    <div class="section-heading">
      <div class="section-kicker">Spend control</div>
      <div class="section-title" style="margin-bottom:0">Budgets</div>
      <div class="section-subtitle">See live budget pressure at a glance, then expand the manager only when you need to change rules.</div>
    </div>
    <a class="budget-manage-link" onclick="toggleBudgetPanel()">&#9881; Manage budgets</a>
  </div>
  {overview_html}
  {status_html}
  <div class="budget-manage-panel" id="budgetManagePanel">
    <div style="font-size:13px;font-weight:700;color:#f0f6fc;margin-bottom:10px" id="budgetFormTitle">Add Budget</div>
    <input type="hidden" id="bEditId" value="">
    <div class="budget-form" id="budgetForm">
      <div class="budget-form-group span-2">
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
        <label class="budget-form-label">Scope</label>
        <select id="bScopeKind" onchange="syncBudgetScopeInput()">
          <option value="global" selected>Overall</option>
          <option value="source_tag">Project / Source Tag</option>
        </select>
      </div>
      <div class="budget-form-group span-2">
        <label class="budget-form-label">Scope Value</label>
        <input type="text" id="bScopeValue" placeholder="all projects" disabled>
      </div>
      <div class="budget-form-group">
        <label class="budget-form-label">Threshold ($)</label>
        <input type="number" id="bThreshold" placeholder="10.00" min="0.01" step="0.01">
      </div>
      <div class="budget-form-group span-2">
        <label class="budget-form-label">Provider (optional)</label>
        <input type="text" id="bProvider" placeholder="all providers">
      </div>
    </div>
    <div class="budget-form-actions">
      <button class="btn-add-budget" id="bSubmitBtn" onclick="submitBudgetForm()">+ Add budget</button>
      <button class="btn-secondary-budget" id="bCancelBtn" onclick="cancelBudgetEdit()" style="display:none">Cancel edit</button>
    </div>
    <div style="font-size:13px;font-weight:700;color:#f0f6fc;margin:18px 0 8px">Existing budgets</div>
    <div class="budget-list-manage" id="budgetListManage">
      {manage_rows}
    </div>
  </div>
  <div class="budget-history">
    <div style="font-size:13px;font-weight:700;color:#f0f6fc">Recent alert history</div>
    <div class="budget-history-list">{history_rows}</div>
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
        desc = (f"{cnt} requests to {_escape_html(model)} averaged {int(avg_tokens):,} tokens — "
                f"under the 1K threshold. {_escape_html(downgrade)} handles simple tasks at a fraction of the cost.")
        savings_str = f"~{fmt_cost(savings)}" if savings > 0.001 else None
        recommendations.append({
            "icon": "💰",
            "title": f"Downgrade {_escape_html(model)} → {_escape_html(downgrade)}",
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
                desc = (f"Cost per 1K tokens: {_escape_html(cheapest[0])} ${cheapest[1]:.4f} vs "
                        f"{_escape_html(most_exp[0])} ${most_exp[1]:.4f}. "
                        f"Consider {_escape_html(cheapest[0])} for cost-sensitive workloads.")
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
  {_render_empty_state(
      "Looking good",
      "No optimization opportunities found. Current usage looks efficient across the models and providers TokenPulse can evaluate.",
      "Action hint: revisit this panel after larger prompt, model, or routing changes.",
      '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  )}
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
    return f"""<div class="optimizer-section loading-surface reveal reveal-delay-2">
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
  {_render_empty_state(
      "No tagged requests yet",
      "Project cards appear when requests include a detected or explicit source tag.",
      "Action hint: TokenPulse can infer tags from User-Agent, or you can send the X-TokenPulse-Project header.",
      '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 6h8l2 2h6v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  )}
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
    return f"""<div class="project-section loading-surface reveal reveal-delay-2">
  <div class="section-title">By Project</div>
  <div class="project-grid">
    {cards_html}
  </div>
</div>"""


def _build_forecast_section(forecast, budgets, budget_forecasts):
    """Build the spending forecast section."""
    if not forecast or forecast.get("daily_avg", 0) == 0:
        return f"""<div class="forecast-section">
  <div class="section-title">Spending Forecast</div>
  {_render_empty_state(
      "Forecast waiting on more data",
      "TokenPulse needs at least one day of paid API activity before it can project burn and runway with confidence.",
      "Action hint: once spend starts landing, this section will estimate month-end cost and budget pressure.",
      _pulse_mark_svg(28)
  )}
</div>"""

    daily_avg = forecast["daily_avg"]
    month_to_date = forecast["month_to_date"]
    projected_month = forecast["projected_month"]
    last_month_total = forecast["last_month_total"]
    days_in_month = forecast["days_in_month"]
    days_remaining = forecast["days_remaining"]
    busiest_day_cost = forecast["busiest_day_cost"]

    if last_month_total > 0:
        if projected_month > last_month_total:
            pct_diff = ((projected_month - last_month_total) / last_month_total) * 100
            trend_html = f'<span class="forecast-trend over">&#8593; {pct_diff:.0f}% vs last month ({fmt_cost(last_month_total)})</span>'
        elif projected_month < last_month_total:
            pct_diff = ((last_month_total - projected_month) / last_month_total) * 100
            trend_html = f'<span class="forecast-trend under">&#8595; {pct_diff:.0f}% vs last month ({fmt_cost(last_month_total)})</span>'
        else:
            trend_html = '<span class="forecast-trend neutral">&#8212; same as last month</span>'
    else:
        trend_html = '<span class="forecast-trend neutral">No last month data for comparison</span>'

    budget_html = ""
    if budgets:
        for b in budgets:
            if b.get("period") == "monthly" and not b.get("is_over"):
                threshold = b.get("threshold_usd", 0)
                current = b.get("current_spend", 0)
                remaining_budget = threshold - current
                if daily_avg > 0 and remaining_budget > 0:
                    days_until_hit = remaining_budget / daily_avg
                    if days_until_hit <= days_remaining:
                        hit_date = datetime.now() + timedelta(days=days_until_hit)
                        budget_html += f"<div class=\"forecast-sub\" style=\"color:#f59e0b;margin-top:8px\">&#9888; You'll hit your {fmt_cost(threshold)}/month budget by {hit_date.strftime('%b %d')}</div>"
                    else:
                        budget_html += f'<div class="forecast-sub" style="color:#22c55e;margin-top:8px">&#10003; On track to stay under {fmt_cost(threshold)}/month budget</div>'
            elif b.get("period") == "monthly" and b.get("is_over"):
                threshold = b.get("threshold_usd", 0)
                budget_html += f'<div class="forecast-sub" style="color:#f85149;margin-top:8px">&#9888; Already over your {fmt_cost(threshold)}/month budget!</div>'

    budget_forecast_html = ""
    for item in budget_forecasts or []:
        note_class = "ok"
        note = f'On current burn, projected {fmt_cost(item.get("projected_period_spend", 0.0))} this {item.get("period")}. '
        pct_used = ((item.get("current_spend", 0.0) / item.get("threshold_usd", 1.0)) * 100.0) if item.get("threshold_usd", 0.0) > 0 else 0.0
        if item.get("is_over"):
            note_class = "over"
            note = f'Already over budget by {fmt_cost(abs(item.get("remaining_budget", 0.0)))}.'
        elif item.get("days_until_threshold") is not None and item.get("days_until_threshold") <= 1.5:
            note_class = "caution"
            note = f'Urgent: at this pace, threshold hit in {item.get("days_until_threshold"):.1f} days.'
        elif item.get("days_until_threshold") is not None and item.get("days_until_threshold") <= item.get("trailing_days", 7):
            note_class = "warn"
            note = f'At this pace, threshold hit in {item.get("days_until_threshold"):.1f} days.'
        elif pct_used >= 80:
            note_class = "caution"
            note = f'{pct_used:.0f}% used already. Watch expensive prompts and retries.'
        budget_forecast_html += (
            f'<div class="forecast-budget-item">'
            f'<div class="forecast-budget-head">'
            f'<div class="forecast-budget-name">{_escape_html(item.get("budget_name") or "Budget")}</div>'
            f'<div class="budget-period-badge">{_escape_html(item.get("period") or "monthly")}</div>'
            f'</div>'
            f'<div class="forecast-sub">{_escape_html(_budget_scope_label(item.get("scope_kind"), item.get("scope_value")))}'
            f'{(" · " + _escape_html(item.get("provider_filter"))) if item.get("provider_filter") else ""}</div>'
            f'<div class="forecast-budget-metrics">'
            f'<div class="forecast-budget-metric"><strong>{fmt_cost(item.get("average_daily_spend", 0.0))}</strong>daily burn</div>'
            f'<div class="forecast-budget-metric"><strong>{fmt_cost(item.get("projected_period_spend", 0.0))}</strong>projected period spend</div>'
            f'<div class="forecast-budget-metric"><strong>{fmt_cost(item.get("remaining_budget", 0.0))}</strong>budget remaining</div>'
            f'</div>'
            f'<div class="forecast-budget-note {note_class}">{_escape_html(note)}</div>'
            f'</div>'
        )
    if budget_forecast_html:
        budget_forecast_html = f'<div class="forecast-card"><div class="forecast-label">Scoped Budget Burn</div><div class="forecast-budget-list">{budget_forecast_html}</div></div>'

    busiest_month_cost = busiest_day_cost * days_in_month

    return f"""<div class="forecast-section loading-surface reveal reveal-delay-2">
  <div class="section-title">Spending Forecast</div>
  <div class="forecast-grid">
    <div class="forecast-card">
      <div class="forecast-label">Projected This Month</div>
      <div class="forecast-value clr-amber">{fmt_cost(projected_month)}</div>
      <div class="forecast-sub">Based on your 7-day average of {fmt_cost(daily_avg)}/day</div>
      {trend_html}
      {budget_html}
    </div>
    <div class="forecast-card">
      <div class="forecast-label">Month to Date</div>
      <div class="forecast-value clr-green">{fmt_cost(month_to_date)}</div>
      <div class="forecast-sub">{forecast['days_elapsed']} days elapsed &middot; {days_remaining} remaining</div>
    </div>
    <div class="forecast-card">
      <div class="forecast-label">Busiest Day Scenario</div>
      <div class="forecast-value" style="color:#f87171">{fmt_cost(busiest_month_cost)}</div>
      <div class="forecast-sub">If every day cost {fmt_cost(busiest_day_cost)} (your peak)</div>
    </div>
    {budget_forecast_html}
  </div>
</div>"""


def _build_attention_section(budgets, budget_forecasts, reliability_data, error_data):
    """Build an action-first summary of what needs attention right now."""
    cards = []

    for item in (budget_forecasts or []):
        remaining_budget = item.get("remaining_budget", 0.0)
        pct_used = ((item.get("current_spend", 0.0) / item.get("threshold_usd", 1.0)) * 100.0) if item.get("threshold_usd", 0.0) > 0 else 0.0
        if item.get("is_over"):
            cards.append({
                "severity": "high",
                "title": f'{item.get("budget_name") or "Budget"} is over budget',
                "body": (
                    f'{_budget_scope_label(item.get("scope_kind"), item.get("scope_value"))} has already overshot by '
                    f'{fmt_cost(abs(remaining_budget))}. Tighten prompts or move cheaper workloads before the next cycle.'
                ),
                "foot": f'Projected period spend: {fmt_cost(item.get("projected_period_spend", 0.0))}',
            })
        elif item.get("days_until_threshold") is not None and item.get("days_until_threshold") <= 3:
            cards.append({
                "severity": "high" if item.get("days_until_threshold") <= 1 else "medium",
                "title": f'{item.get("budget_name") or "Budget"} will hit soon',
                "body": (
                    f'At the current burn of {fmt_cost(item.get("average_daily_spend", 0.0))}/day, '
                    f'this budget is on pace to hit in {item.get("days_until_threshold"):.1f} days.'
                ),
                "foot": f'{pct_used:.0f}% used · {fmt_cost(max(remaining_budget, 0.0))} remaining',
            })
        elif pct_used >= 80:
            cards.append({
                "severity": "medium",
                "title": f'{item.get("budget_name") or "Budget"} is in the caution zone',
                "body": (
                    f'{pct_used:.0f}% of this {item.get("period") or "monthly"} budget is already used. '
                    'Watch for unnecessary retries or expensive model drift.'
                ),
                "foot": f'{fmt_cost(max(remaining_budget, 0.0))} remaining',
            })

    for item in (reliability_data or {}).get("anomalies", [])[:3]:
        fallback = item.get("fallback_model")
        foot = f'{fmt_cost(item.get("recent_cost", 0.0))} spend touched in last 24h'
        if fallback:
            foot += f' · Suggested fallback: {fallback}'
        cards.append({
            "severity": item.get("severity") or "medium",
            "title": f'{item.get("model") or "Model"} needs a fallback plan',
            "body": item.get("recommendation") or item.get("summary") or '',
            "foot": foot,
        })

    total_errors = (error_data or {}).get("total_errors", 0)
    error_rate = (error_data or {}).get("error_rate", 0.0)
    wasted_cost = (error_data or {}).get("wasted_cost", 0.0)
    if total_errors and error_rate >= 3.0:
        cards.append({
            "severity": "high" if error_rate >= 8.0 else "medium",
            "title": 'Errors are burning paid requests',
            "body": (
                f'{total_errors} failed requests landed in this range, with {fmt_cost(wasted_cost)} already spent on failures. '
                'If this is a live workflow, temporarily reduce retries and route critical tasks to the cleanest provider.'
            ),
            "foot": f'Current blended error rate: {error_rate:.1f}%',
        })

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    cards.sort(key=lambda item: severity_rank.get(item.get("severity"), 3))
    visible_cards = cards[:6]
    high_count = sum(1 for item in cards if item.get("severity") == "high")
    medium_count = sum(1 for item in cards if item.get("severity") == "medium")
    covered_spend = sum((item.get("recent_cost", 0.0) or 0.0) for item in (reliability_data or {}).get("anomalies", [])) + (wasted_cost or 0.0)
    summary_html = (
        f'<div class="attention-summary">'
        f'<div class="attention-stat"><div class="attention-stat-label">Needs action</div><div class="attention-stat-value">{len(cards)}</div><div class="attention-stat-sub">{high_count} high priority · {medium_count} medium</div></div>'
        f'<div class="attention-stat"><div class="attention-stat-label">Error rate</div><div class="attention-stat-value">{error_rate:.1f}%</div><div class="attention-stat-sub">{total_errors:,} failed requests in this range</div></div>'
        f'<div class="attention-stat"><div class="attention-stat-label">Spend at risk</div><div class="attention-stat-value">{fmt_cost(covered_spend)}</div><div class="attention-stat-sub">Reliability anomalies and failed request waste</div></div>'
        f'</div>'
    )

    if not visible_cards:
        return f"""<div class=\"attention-section\">
  <div class=\"section-header\">
    <div class=\"section-heading\">
      <div class=\"section-kicker\">Priority view</div>
      <div class=\"section-title\" style=\"margin-bottom:0\">Attention Center</div>
      <div class=\"section-subtitle\">Start here first. This rolls up budget pressure, error waste, and reliability risk into the few things that actually need a decision.</div>
    </div>
  </div>
  {summary_html}
  {_render_empty_state(
      "Nothing urgent right now",
      "Budget pressure, failed-request waste, and reliability drift are all within a healthy range.",
      "Action hint: use this area as the first stop when spend rises, alerts trigger, or a provider starts degrading.",
      '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      "attention-empty"
  )}
</div>"""

    cards_html = ''.join(
        f'<div class=\"attention-card {item.get("severity", "medium")}\">'
        f'<div class=\"attention-head\">'
        f'<div class=\"attention-title\">{_escape_html(item.get("title") or "Attention")}</div>'
        f'<span class=\"attention-pill {item.get("severity", "medium")}\">{_escape_html(item.get("severity") or "medium")}</span>'
        f'</div>'
        f'<div class=\"attention-body\">{_escape_html(item.get("body") or "")}</div>'
        f'<div class=\"attention-foot\">{_escape_html(item.get("foot") or "")}</div>'
        f'</div>'
        for item in visible_cards
    )

    return f"""<div class=\"attention-section\">
  <div class=\"section-header\">
    <div class=\"section-heading\">
      <div class=\"section-kicker\">Priority view</div>
      <div class=\"section-title\" style=\"margin-bottom:0\">Attention Center</div>
      <div class=\"section-subtitle\">Start here first. This rolls up budget pressure, error waste, and reliability risk into the few things that actually need a decision.</div>
    </div>
  </div>
  {summary_html}
  <div class=\"attention-grid\">{cards_html}</div>
</div>"""


def _build_context_audit_section(audit_data):
    """Build the Context Audit section."""
    if not audit_data:
        return ""

    score = int(audit_data.get("score", 100) or 100)
    estimated_savings = float(audit_data.get("estimated_savings_usd", 0.0) or 0.0)
    findings = audit_data.get("findings") or []

    score_tone = "good" if score >= 80 else "warn" if score >= 55 else "bad"
    score_label = "Clean" if score >= 80 else "Needs work" if score >= 55 else "Wasteful"

    summary_html = f"""<div class="reliability-summary">
  <div class="reliability-card">
    <div class="reliability-label">Audit Score</div>
    <div class="reliability-value">{score}/100</div>
    <div class="reliability-sub">{score_label} context hygiene</div>
  </div>
  <div class="reliability-card">
    <div class="reliability-label">Estimated Savings</div>
    <div class="reliability-value">{fmt_cost(estimated_savings)}</div>
    <div class="reliability-sub">Heuristic recoverable waste in this range</div>
  </div>
  <div class="reliability-card">
    <div class="reliability-label">Findings</div>
    <div class="reliability-value">{len(findings)}</div>
    <div class="reliability-sub">Top waste patterns detected</div>
  </div>
</div>"""

    if not findings:
        return f"""<div class="reliability-section">
  <div class="section-title">Context Audit</div>
  {summary_html}
  {_render_empty_state(
      "No obvious context waste",
      "This range looks pretty clean based on current heuristics.",
      "Action hint: revisit after bigger prompt changes, routing changes, or a week of heavier usage.",
      _pulse_mark_svg(28)
  )}
</div>"""

    items = []
    for item in findings[:6]:
        severity = item.get("severity") or "medium"
        meta_bits = [f'{item.get("requests", 0)} request(s)']
        impact = float(item.get("estimated_cost_impact_usd", 0.0) or 0.0)
        if impact > 0:
            meta_bits.append(f'{fmt_cost(impact)} impact')
        items.append(
            f'<div class="anomaly-item">'
            f'<div class="anomaly-header">'
            f'<div class="anomaly-title">{_escape_html(item.get("title") or "Finding")}</div>'
            f'<span class="severity-badge {severity}">{_escape_html(severity)}</span>'
            f'</div>'
            f'<div class="anomaly-meta"><span>{_escape_html(" · ".join(meta_bits))}</span></div>'
            f'<div class="reliability-sub" style="margin-top:8px">{_escape_html(item.get("summary") or "")}</div>'
            f'<div class="anomaly-recommendation"><strong>Recommendation:</strong> {_escape_html(item.get("recommendation") or "")}</div>'
            f'</div>'
        )

    score_banner = f'<div class="attention-card {score_tone}" style="margin-bottom:14px"><div class="attention-head"><div class="attention-title">Context hygiene verdict</div><span class="attention-pill {score_tone}">{score_label}</span></div><div class="attention-body">This panel flags likely prompt waste, model misuse, and cache misses using the request data TokenPulse already tracks.</div><div class="attention-foot">Use it to decide what to preprocess, what to reroute, and what to trim.</div></div>'

    return f"""<div class="reliability-section">
  <div class="section-title">Context Audit</div>
  {summary_html}
  {score_banner}
  <div class="anomaly-list">{''.join(items)}</div>
</div>"""


def _build_reliability_section(reliability_data):
    """Build latency/reliability overview section."""
    if not reliability_data:
        return ""

    summary = reliability_data.get("summary") or {}
    providers = reliability_data.get("providers") or []
    anomalies = reliability_data.get("anomalies") or []
    total_requests = summary.get("total_requests", 0)
    if total_requests == 0:
        return f"""<div class="reliability-section">
  <div class="section-title">Reliability &amp; Latency</div>
  {_render_empty_state(
      "No reliability data yet",
      "This panel needs tracked requests in the selected range before it can summarize success rates and anomaly risk.",
      "Action hint: send a few requests through the proxy or widen the time window.",
      _pulse_mark_svg(28)
  )}
</div>"""

    summary_html = f"""<div class="reliability-summary">
  <div class="reliability-card">
    <div class="reliability-label">Success Rate</div>
    <div class="reliability-value">{summary.get('success_rate_pct', 100.0):.1f}%</div>
    <div class="reliability-sub">{summary.get('successful_requests', 0):,} successful of {total_requests:,}</div>
  </div>
  <div class="reliability-card">
    <div class="reliability-label">Avg Latency</div>
    <div class="reliability-value">{fmt_latency(summary.get('avg_latency_ms', 0))}</div>
    <div class="reliability-sub">Across all tracked requests</div>
  </div>
  <div class="reliability-card">
    <div class="reliability-label">Slow Requests</div>
    <div class="reliability-value">{summary.get('slow_requests', 0):,}</div>
    <div class="reliability-sub">{summary.get('slow_request_pct', 0.0):.1f}% above 5s</div>
  </div>
</div>"""

    provider_items = []
    for item in providers:
        provider_items.append(
            f'<div class="reliability-item">'
            f'<div class="reliability-item-header">'
            f'<div class="reliability-item-name" title="{_escape_html(item.get("model") or "unknown")}">{_escape_html(item.get("model") or "unknown")}</div>'
            f'{provider_badge_html(item.get("provider") or "unknown")}'
            f'</div>'
            f'<div class="reliability-item-stats">'
            f'<span>{item.get("total_requests", 0):,} reqs</span>'
            f'<span>{item.get("success_rate_pct", 100.0):.1f}% success</span>'
            f'<span>{fmt_latency(item.get("avg_latency_ms", 0))} avg</span>'
            f'<span>{fmt_latency(item.get("max_latency_ms", 0))} max</span>'
            f'</div>'
            f'</div>'
        )
    if not provider_items:
        provider_items = ['<div class="reliability-empty">No provider rollups yet.</div>']

    anomaly_items = []
    for item in anomalies:
        severity = item.get("severity") or "medium"
        recommendation = item.get("recommendation") or ""
        fallback_model = item.get("fallback_model")
        impact_bits = [f'{item.get("recent_requests", 0)} recent / {item.get("baseline_requests", 0)} baseline']
        if item.get("recent_cost", 0.0) > 0:
            impact_bits.append(f'{fmt_cost(item.get("recent_cost", 0.0))} spend in 24h')
        recommendation_html = ""
        if recommendation:
            recommendation_html = (
                '<div class="anomaly-recommendation"><strong>Fallback:</strong> '
                + _escape_html(recommendation)
            )
            if fallback_model:
                recommendation_html += '<br><strong>Switch target:</strong> ' + _escape_html(fallback_model)
            recommendation_html += '</div>'
        anomaly_items.append(
            f'<div class="anomaly-item">'
            f'<div class="anomaly-header">'
            f'<div class="anomaly-title">{_escape_html(item.get("model") or "unknown")}</div>'
            f'<span class="severity-badge {severity}">{severity}</span>'
            f'</div>'
            f'<div class="anomaly-meta">'
            f'{provider_badge_html(item.get("provider") or "unknown")}'
            f'<span>{_escape_html(" · ".join(impact_bits))}</span>'
            f'</div>'
            f'<div class="reliability-sub" style="margin-top:8px">{_escape_html(item.get("summary") or "")}</div>'
            f'{recommendation_html}'
            f'</div>'
        )
    if not anomaly_items:
        anomaly_items = ['<div class="reliability-empty">No current latency or error spikes detected.</div>']

    return f"""<div class="reliability-section">
  <div class="section-title">Reliability &amp; Latency</div>
  {summary_html}
  <div class="reliability-grid">
    <div>
      <div style="font-size:12px;font-weight:600;color:#f0f6fc;margin-bottom:8px">Top Providers / Models</div>
      <div class="reliability-list">{''.join(provider_items)}</div>
    </div>
    <div>
      <div style="font-size:12px;font-weight:600;color:#f0f6fc;margin-bottom:8px">Anomalies (24h vs baseline)</div>
      <div class="anomaly-list">{''.join(anomaly_items)}</div>
    </div>
  </div>
</div>"""


def _build_error_section(error_data, time_range):
    """Build the error monitor section."""
    if not error_data:
        return ""

    total_errors = error_data.get("total_errors", 0)
    total_requests = error_data.get("total_requests", 0)
    error_rate = error_data.get("error_rate", 0.0)
    wasted_cost = error_data.get("wasted_cost", 0.0)
    error_by_model = error_data.get("error_by_model", [])
    error_timeline = error_data.get("error_timeline", [])
    recent_errors = error_data.get("recent_errors", [])

    range_label = RANGE_LABELS.get(time_range, "today").lower()

    # Summary bar
    if total_errors == 0:
        indicator_class = "green"
        summary_text = '<strong>No errors detected &#10003;</strong>'
    elif error_rate < 1:
        indicator_class = "green"
        summary_text = f'<strong>{total_errors}</strong> error{"s" if total_errors != 1 else ""} out of <strong>{total_requests:,}</strong> requests ({error_rate:.1f}%)'
    elif error_rate < 5:
        indicator_class = "yellow"
        summary_text = f'<strong>{total_errors}</strong> errors out of <strong>{total_requests:,}</strong> requests ({error_rate:.1f}%)'
    else:
        indicator_class = "red"
        summary_text = f'<strong>{total_errors}</strong> errors out of <strong>{total_requests:,}</strong> requests ({error_rate:.1f}%)'

    summary_bar = f"""<div class="error-summary-bar">
  <div class="error-indicator {indicator_class}"></div>
  <div class="error-summary-text">{summary_text}</div>
</div>"""

    # If no errors at all, just show the summary bar
    if total_errors == 0:
        return f"""<div class="error-section">
  <div class="section-title" style="margin-bottom:14px">Error Monitor</div>
  {summary_bar}
</div>"""

    # Error rate by model
    model_items = ""
    for m in error_by_model[:8]:
        model_name = _escape_html(m.get("model", "unknown"))
        provider = m.get("provider", "unknown")
        total = m.get("total", 0)
        errors = m.get("errors", 0)
        rate = m.get("error_rate", 0.0)

        if rate > 5:
            rate_class = "red"
            item_class = "error-model-item high-error"
        elif rate > 1:
            rate_class = "yellow"
            item_class = "error-model-item"
        else:
            rate_class = "green"
            item_class = "error-model-item"

        model_items += (
            f'<div class="{item_class}">'
            f'<div class="error-model-left">'
            f'<span class="error-model-name" title="{model_name}">{model_name}</span>'
            f'{provider_badge_html(provider)}'
            f'</div>'
            f'<div class="error-model-stats">'
            f'<span>{total:,} reqs</span>'
            f'<span>{errors} errors</span>'
            f'<span class="error-rate-badge {rate_class}">{rate}%</span>'
            f'</div>'
            f'</div>'
        )

    model_section = ""
    if model_items:
        model_section = f"""<div style="margin-bottom:14px">
  <div style="font-size:12px;font-weight:600;color:#f0f6fc;margin-bottom:8px">Error Rate by Model (7 days)</div>
  <div class="error-models">{model_items}</div>
</div>"""

    # Error timeline (last 24 hours bar chart)
    timeline_section = ""
    if error_timeline:
        now = datetime.now()
        # Build all 24 hours
        hours_map = {}
        for et in error_timeline:
            hours_map[et["hour"]] = et["cnt"]

        max_cnt = max((et["cnt"] for et in error_timeline), default=1)
        if max_cnt == 0:
            max_cnt = 1

        bars_html = ""
        for i in range(24):
            h = now - timedelta(hours=23 - i)
            hour_key = h.strftime("%Y-%m-%d %H:00")
            cnt = hours_map.get(hour_key, 0)
            if cnt > 0:
                height_pct = max(4, int((cnt / max_cnt) * 100))
                tooltip = f"{h.strftime('%b %d, %H:00')} — {cnt} error{'s' if cnt != 1 else ''}"
                bars_html += f'<div class="error-bar" style="height:{height_pct}%" title="{_escape_html(tooltip)}"></div>'
            else:
                bars_html += '<div class="error-bar-empty"></div>'

        timeline_section = f"""<div class="error-timeline-wrap">
  <div class="error-timeline-label">Error Timeline (last 24h)</div>
  <div class="error-timeline-chart">{bars_html}</div>
</div>"""

    # Recent errors list
    recent_section = ""
    if recent_errors:
        items_html = ""
        for idx, err in enumerate(recent_errors):
            ts = relative_time(err.get("timestamp", ""))
            model = _escape_html(err.get("model", "unknown"))
            provider = err.get("provider", "unknown")
            msg = err.get("error_message", "")
            cost = err.get("cost_usd", 0)
            short_msg = _escape_html(msg[:100]) + ("..." if len(msg) > 100 else "")
            full_msg = _escape_html(msg)
            cost_html = f'<span class="error-recent-cost">{fmt_cost(cost)} wasted</span>' if cost > 0 else ""

            items_html += (
                f'<div class="error-recent-item" onclick="this.classList.toggle(\'expanded\')">'
                f'<div class="error-recent-header">'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<span class="error-recent-time">{ts}</span>'
                f'<span class="error-recent-model">{model}</span>'
                f'{provider_badge_html(provider)}'
                f'</div>'
                f'{cost_html}'
                f'</div>'
                f'<div class="error-recent-msg">{short_msg}</div>'
                f'<div class="error-recent-full">{full_msg}</div>'
                f'</div>'
            )

        recent_section = f"""<div>
  <div style="font-size:12px;font-weight:600;color:#f0f6fc;margin-bottom:8px">Recent Errors</div>
  <div class="error-recent-list">{items_html}</div>
</div>"""

    return f"""<div class="error-section">
  <div class="section-title" style="margin-bottom:14px">Error Monitor</div>
  {summary_bar}
  {model_section}
  {timeline_section}
  {recent_section}
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
  <div class="stat-card loading-surface reveal reveal-delay-1">
    <div class="stat-label">API Spend</div>
    <div class="stat-value clr-green" data-countup="{data['api_cost']:.4f}" data-prefix="$" data-decimals="2">{fmt_cost(data['api_cost'])}</div>
    <div class="stat-sub">paid API calls</div>
    {api_trend}
    {spend_spark}
  </div>
  <div class="stat-card loading-surface reveal reveal-delay-2">
    <div class="stat-label">Subscription Usage</div>
    <div class="stat-value clr-blue" data-countup="{float(data['sub_tokens'])}" data-format="compact">{fmt_tokens(data['sub_tokens'])}</div>
    <div class="stat-sub">tokens &middot; included in plan</div>
    {sub_trend}
    {sub_spark}
  </div>
  <div class="stat-card loading-surface reveal reveal-delay-3">
    <div class="stat-label">Local Usage</div>
    <div class="stat-value clr-purple" data-countup="{float(data['local_tokens'])}" data-format="compact">{fmt_tokens(data['local_tokens'])}</div>
    <div class="stat-sub">tokens &middot; free</div>
    {local_trend}
    {local_spark}
  </div>
  <div class="stat-card loading-surface reveal reveal-delay-4">
    <div class="stat-label">Total Requests</div>
    <div class="stat-value" data-countup="{float(data['total_requests'])}">{data['total_requests']:,}</div>
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
        return (
            '<div class="chart-empty">'
            + _render_empty_state(
                "No spend data yet",
                "This chart will light up once paid API usage starts flowing through the local proxy.",
                "Action hint: make a tracked API request or change the range to inspect an earlier period.",
                _pulse_mark_svg(28),
            )
            + '</div>'
        )

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
        return (
            '<div class="chart-empty">'
            + _render_empty_state(
                "No spend data yet",
                "There are requests in this range, but none with billable API spend.",
                "Action hint: compare another range or check whether recent usage is local or subscription based.",
                _pulse_mark_svg(28),
            )
            + '</div>'
        )

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
        return (
            '<div class="chart-empty">'
            + _render_empty_state(
                "No spend data yet",
                "Nothing billable landed in the selected window.",
                "Action hint: expand the range to see the most recent spend-bearing requests.",
                _pulse_mark_svg(28),
            )
            + '</div>'
        )

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
        prov_safe = _escape_html(prov)
        color = _provider_color(prov)
        if color.startswith("#") and len(color) == 7:
            r2, g2, b2 = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            top_c = f"rgba({r2},{g2},{b2},0.4)"
            bot_c = f"rgba({r2},{g2},{b2},0.05)"
        else:
            top_c, bot_c = "rgba(255,255,255,0.4)", "rgba(255,255,255,0.05)"
        svg_parts.append(
            f'<linearGradient id="grad_{prov_safe}" x1="0" y1="0" x2="0" y2="1">'
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
        prov_safe = _escape_html(prov)
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

        def pts_to_d(pts, smooth=False):
            d_str = f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"
            if not smooth or len(pts) < 3:
                for px, py in pts[1:]:
                    d_str += f" L {px:.1f},{py:.1f}"
                return d_str
            for i in range(1, len(pts)):
                prev_pt = pts[i - 1]
                curr_pt = pts[i]
                next_pt = pts[i + 1] if i + 1 < len(pts) else curr_pt
                cp1x = prev_pt[0] + (curr_pt[0] - prev_pt[0]) * 0.55
                cp1y = prev_pt[1]
                cp2x = curr_pt[0] - (next_pt[0] - prev_pt[0]) * 0.12
                cp2y = curr_pt[1]
                d_str += f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {curr_pt[0]:.1f},{curr_pt[1]:.1f}"
            return d_str

        top_d = pts_to_d(top_pts)
        # Area: top path forward, then bottom path reversed
        rev_bot = list(reversed(bot_pts))
        area_d = top_d
        for px, py in rev_bot:
            area_d += f" L {px:.1f},{py:.1f}"
        area_d += " Z"

        # Stroke path (top line only)
        stroke_d = pts_to_d(top_pts, smooth=True)

        svg_parts.append(
            f'<path d="{area_d}" fill="url(#grad_{prov_safe})" opacity="0.85"/>'
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
    legend_html = '<div class="chart-legend">' + "".join(
        f'<span class="chart-legend-item" style="color:{_provider_color(prov)}"><span class="chart-legend-swatch" style="background:{_provider_color(prov)}"></span>{_escape_html("LM Studio" if prov == "lmstudio" else prov)}</span>'
        for prov in all_provs
    ) + '</div>'

    return (
        legend_html
        + f'<div class="spend-svg-wrap" id="spendChartWrap">'
        + "".join(svg_parts)
        + tooltip_html
        + "</div>"
    )


def _build_model_breakdown(data):
    models = data["models"]
    if not models:
        return (
            '<div class="chart-empty">'
            + _render_empty_state(
                "No model activity yet",
                "Model usage cards appear once TokenPulse sees at least one tracked request in this range.",
                "Action hint: send a request through the proxy to populate provider and model breakdowns.",
                _pulse_mark_svg(28),
            )
            + '</div>'
        )

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
            f'<div class="model-item loading-surface reveal reveal-delay-1">'
            f'<div class="model-row">'
            f'<div>'
            f'<div class="model-name" title="{_escape_html(model_name)}">{_escape_html(model_name)}</div>'
            f'<div class="model-meta">'
            f"{provider_badge_html(prov)} "
            f"<span>{m['cnt']} reqs</span> "
            f"<span title=\"{fmt_tokens(tok)} tokens\">{fmt_compact_number(tok)} tokens</span>"
            f"</div>"
            f"</div>"
            f"{cost_html}"
            f"</div>"
            f'<div class="usage-bar-bg">'
            f'<div class="usage-bar-fill" style="width:{bar_w}%;background:{bar_color};color:{bar_color}"></div>'
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


def _build_insights(data, forecast=None, error_data=None, reliability_data=None):
    """Build auto-generated insights panel."""
    ir = data.get("insights_raw", {})
    time_range = data.get("time_range", "today")
    range_label = RANGE_LABELS.get(time_range, "today").lower()

    cards = []

    # Forecast insights
    if forecast and forecast.get("daily_avg", 0) > 0:
        projected = forecast["projected_month"]
        last_month = forecast["last_month_total"]
        if last_month > 0:
            cards.append(
                ('<span class="insight-emoji">&#128200;</span>',
                 "Monthly Projection",
                 f"At current rates, you'll spend {fmt_cost(projected)} this month (vs {fmt_cost(last_month)} last month)")
            )
        else:
            cards.append(
                ('<span class="insight-emoji">&#128200;</span>',
                 "Monthly Projection",
                 f"At current rates, you'll spend {fmt_cost(projected)} this month")
            )

        busiest = forecast.get("busiest_day_cost", 0)
        if busiest > 0:
            busiest_monthly = busiest * forecast.get("days_in_month", 30)
            cards.append(
                ('<span class="insight-emoji">&#128293;</span>',
                 "Peak Day Impact",
                 f"Your busiest day cost {fmt_cost(busiest)} — if every day was like that, monthly cost would be {fmt_cost(busiest_monthly)}")
            )

    # Error insights
    if error_data and error_data.get("total_errors", 0) > 0:
        err_total = error_data["total_errors"]
        err_rate = error_data["error_rate"]
        wasted = error_data["wasted_cost"]
        if wasted > 0:
            cards.append(
                ('<span class="insight-emoji">&#9888;</span>',
                 "Error Waste",
                 f"{err_rate:.1f}% of requests failed {range_label} — costing {fmt_cost(wasted)} in wasted tokens")
            )

        worst = error_data.get("worst_model")
        worst_rate = error_data.get("worst_model_rate", 0)
        if worst and worst_rate > 2:
            cards.append(
                ('<span class="insight-emoji">&#128308;</span>',
                 "Model Alert",
                 f"{_escape_html(worst)} has a {worst_rate:.1f}% error rate — check your configuration")
            )

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

    if reliability_data and (reliability_data.get("anomalies") or []):
        first_anomaly = reliability_data["anomalies"][0]
        cards.append(
            ('<span class="insight-emoji">&#128680;</span>',
             "Reliability Spike",
             _escape_html(first_anomaly.get("summary") or "Recent reliability anomaly detected"))
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
            '<div class="chart-empty" style="padding:28px">'
            + _render_empty_state(
                "No requests in this range",
                "There are no tracked requests for the selected filter yet.",
                "Action hint: switch ranges or send a new request through the local proxy to populate the table.",
                _pulse_mark_svg(28),
            )
            + "</div></div>"
        )

    rows_html = []
    for idx, r in enumerate(requests):
        ts_full = fmt_timestamp_full(r["timestamp"])
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
            f'<td class="td-time" style="border-left:3px solid {prov_color}" title="{_escape_html(ts_full)}">{ts}</td>'
            f'<td class="td-provider">{provider_badge_html(prov)}</td>'
            f'<td class="td-model" title="{model_name}">{model_name}</td>'
            f'<td class="td-num" title="{r["input_tokens"]:,}">{inp}</td>'
            f'<td class="td-num" title="{r["output_tokens"]:,}">{out}</td>'
            f'<td class="td-cost">{cost_td}</td>'
            f'<td class="latency td-latency">{lat}</td>'
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


var seenNotificationKeys = {{}};
var previousRecentCount = parseInt(window.sessionStorage.getItem('tpRecentCount') || '0', 10);

function formatCompactNumber(value) {{
  var num = Number(value || 0);
  if (!isFinite(num)) return '0';
  if (Math.abs(num) >= 1000000) return (num / 1000000).toFixed(1).replace(/\\.0$/, '') + 'M';
  if (Math.abs(num) >= 1000) return (num / 1000).toFixed(1).replace(/\\.0$/, '') + 'K';
  return Math.round(num).toLocaleString();
}}

function formatCurrency(value) {{
  var num = Number(value || 0);
  if (!isFinite(num)) return '$0.00';
  if (Math.abs(num) < 0.01 && num !== 0) return '$' + num.toFixed(4);
  return new Intl.NumberFormat('en-US', {{ style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }}).format(num);
}}

function formatCurrencyPrecise(value) {{
  var num = Number(value || 0);
  if (!isFinite(num)) return '$0.00';
  return '$' + num.toLocaleString('en-US', {{ minimumFractionDigits: num < 1 ? 4 : 2, maximumFractionDigits: num < 1 ? 4 : 2 }});
}}

function requestBrowserNotifications() {{
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {{
    Notification.requestPermission().catch(function(){{}});
  }}
}}

function pollNotifications() {{
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  fetch('/api/notifications?limit=20')
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      (data.notifications || []).forEach(function(item) {{
        if (seenNotificationKeys[item.dedupe_key]) return;
        seenNotificationKeys[item.dedupe_key] = true;
        try {{ new Notification(item.title || 'TokenPulse', {{ body: item.body || '' }}); }} catch (e) {{}}
      }});
    }})
    .catch(function(){{}});
}}
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

function initRangeIndicators() {{
  document.querySelectorAll('.range-pill-group').forEach(function(group) {{
    var indicator = group.querySelector('.range-indicator');
    var active = group.querySelector('.range-btn.active');
    if (!indicator || !active) return;
    indicator.style.left = active.offsetLeft + 'px';
    indicator.style.width = active.offsetWidth + 'px';
    indicator.style.opacity = '1';
  }});
}}

function initCountups() {{
  document.querySelectorAll('[data-countup]').forEach(function(el) {{
    var target = Number(el.getAttribute('data-countup') || '0');
    var decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
    var prefix = el.getAttribute('data-prefix') || '';
    var format = el.getAttribute('data-format') || '';
    var start = 0;
    var duration = 700;
    var startTs = null;
    function render(value) {{
      if (format === 'compact') {{
        el.textContent = formatCompactNumber(value);
      }} else if (prefix === '$') {{
        el.textContent = prefix + value.toLocaleString('en-US', {{ minimumFractionDigits: decimals, maximumFractionDigits: decimals }});
      }} else {{
        el.textContent = Math.round(value).toLocaleString();
      }}
    }}
    function step(ts) {{
      if (!startTs) startTs = ts;
      var progress = Math.min((ts - startTs) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      render(start + ((target - start) * eased));
      if (progress < 1) window.requestAnimationFrame(step);
    }}
    window.requestAnimationFrame(step);
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
      lines += 'Total: ' + formatCurrencyPrecise(total) + '<br>';
      var provs = Object.keys(costs).sort();
      provs.forEach(function(p) {{
        if (costs[p] > 0) {{
          var clr = provColors[p] || '#8b949e';
          lines += '<span style="color:' + clr + '">' + p + '</span>: ' + formatCurrencyPrecise(costs[p]) + '<br>';
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

function initScrollTop() {{
  var btn = document.getElementById('scrollTopBtn');
  if (!btn) return;
  window.addEventListener('scroll', function() {{
    if ((window.scrollY || window.pageYOffset) > 420) btn.classList.add('visible');
    else btn.classList.remove('visible');
  }});
  btn.addEventListener('click', function() {{
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }});
}}

function markLiveUpdate() {{
  if (recentCount > previousRecentCount) {{
    document.querySelectorAll('.live-badge').forEach(function(el) {{
      el.classList.add('has-update');
    }});
  }}
  window.sessionStorage.setItem('tpRecentCount', String(recentCount));
}}

function initLoadedState() {{
  document.body.classList.remove('preload');
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

function syncBudgetScopeInput() {{
  var scopeKindEl = document.getElementById('bScopeKind');
  var scopeValueEl = document.getElementById('bScopeValue');
  if (!scopeKindEl || !scopeValueEl) return;
  var scoped = scopeKindEl.value === 'source_tag';
  scopeValueEl.disabled = !scoped;
  scopeValueEl.placeholder = scoped ? 'e.g. project-alpha' : 'all projects';
  if (!scoped) scopeValueEl.value = '';
}}

function collectBudgetFormState() {{
  var editIdEl = document.getElementById('bEditId');
  var nameEl = document.getElementById('bName');
  var periodEl = document.getElementById('bPeriod');
  var scopeKindEl = document.getElementById('bScopeKind');
  var scopeValueEl = document.getElementById('bScopeValue');
  var threshEl = document.getElementById('bThreshold');
  var provEl = document.getElementById('bProvider');
  return {{
    id: editIdEl ? editIdEl.value : '',
    name: nameEl ? nameEl.value.trim() : '',
    period: periodEl ? periodEl.value : 'monthly',
    scopeKind: scopeKindEl ? scopeKindEl.value : 'global',
    scopeValue: scopeValueEl ? scopeValueEl.value.trim() : '',
    threshold: parseFloat(threshEl ? threshEl.value : '0'),
    provider: provEl ? provEl.value.trim() : ''
  }};
}}

function resetBudgetForm() {{
  var ids = ['bEditId','bName','bScopeValue','bThreshold','bProvider'];
  ids.forEach(function(id) {{ var el = document.getElementById(id); if (el) el.value = ''; }});
  var periodEl = document.getElementById('bPeriod');
  if (periodEl) periodEl.value = 'monthly';
  var scopeKindEl = document.getElementById('bScopeKind');
  if (scopeKindEl) scopeKindEl.value = 'global';
  syncBudgetScopeInput();
  var titleEl = document.getElementById('budgetFormTitle');
  if (titleEl) titleEl.textContent = 'Add Budget';
  var submitEl = document.getElementById('bSubmitBtn');
  if (submitEl) submitEl.textContent = '+ Add';
  var cancelEl = document.getElementById('bCancelBtn');
  if (cancelEl) cancelEl.style.display = 'none';
}}

function startBudgetEdit(id) {{
  var row = document.getElementById('bmrow-' + id);
  if (!row) return;
  document.getElementById('bEditId').value = id;
  document.getElementById('bName').value = row.dataset.name || '';
  document.getElementById('bPeriod').value = row.dataset.period || 'monthly';
  document.getElementById('bScopeKind').value = row.dataset.scopeKind || 'global';
  document.getElementById('bScopeValue').value = row.dataset.scopeValue || '';
  document.getElementById('bThreshold').value = row.dataset.threshold || '';
  document.getElementById('bProvider').value = row.dataset.provider || '';
  syncBudgetScopeInput();
  var titleEl = document.getElementById('budgetFormTitle');
  if (titleEl) titleEl.textContent = 'Edit Budget';
  var submitEl = document.getElementById('bSubmitBtn');
  if (submitEl) submitEl.textContent = 'Save';
  var cancelEl = document.getElementById('bCancelBtn');
  if (cancelEl) cancelEl.style.display = 'inline-block';
}}

function cancelBudgetEdit() {{
  resetBudgetForm();
}}

function submitBudgetForm() {{
  var form = collectBudgetFormState();
  if (!form.name) {{ alert('Please enter a budget name.'); return; }}
  if (form.scopeKind === 'source_tag' && !form.scopeValue) {{ alert('Please enter a project/source tag.'); return; }}
  if (!form.threshold || form.threshold <= 0) {{ alert('Please enter a valid threshold.'); return; }}

  var body = 'name=' + encodeURIComponent(form.name) +
    '&period=' + encodeURIComponent(form.period) +
    '&threshold=' + encodeURIComponent(form.threshold);
  if (form.provider) body += '&provider_filter=' + encodeURIComponent(form.provider);
  if (form.scopeKind) body += '&scope_kind=' + encodeURIComponent(form.scopeKind);
  if (form.scopeValue) body += '&scope_value=' + encodeURIComponent(form.scopeValue);

  var isEdit = !!form.id;
  if (isEdit) body += '&enabled=' + encodeURIComponent(1);

  fetch(isEdit ? '/api/budgets/' + form.id : '/api/budgets', {{
    method: isEdit ? 'PUT' : 'POST',
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

function toggleBudgetEnabled(id, enabled) {{
  var body = 'enabled=' + encodeURIComponent(enabled ? '1' : '0');
  fetch('/api/budgets/' + id + '/enabled', {{
    method: 'PUT',
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
  initLoadedState();
  initStickyNav();
  initRangeIndicators();
  var actLevel = Math.min(10, Math.round(recentCount / 2));
  initTokenFlow(actLevel);
  initActivityFeed(activityDots, recentCount);
  resetBudgetForm();
  initSpendChart();
  initExpandableRows();
  initCountups();
  initScrollTop();
  updatePulseDots(recentCount);
  markLiveUpdate();
  requestBrowserNotifications();
  pollNotifications();
  setInterval(pollNotifications, 30000);
  window.addEventListener('resize', initRangeIndicators);
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
    favicon_href = _favicon_href()
    pulse_mark_small = _pulse_mark_svg(18)
    pulse_mark_large = _pulse_mark_svg(28)
    proxy_online, proxy_label = _proxy_status_summary()
    proxy_status_class = "online" if proxy_online else "offline"

    try:
        data = _fetch_data(time_range)
    except Exception as e:
        error_body = ERROR_TEMPLATE.substitute(
            icon_svg='<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 8v5m0 4h.01M10.3 3.85 1.82 18a2 2 0 0 0 1.72 3h16.92a2 2 0 0 0 1.72-3L13.7 3.85a2 2 0 0 0-3.4 0Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            error_message=_escape_html(str(e)),
            db_path=_escape_html(DB_PATH),
        )
        empty_scripts = "<script>document.body.classList.remove('preload');setTimeout(function(){location.reload()},3000);</script>"
        return PAGE_TEMPLATE.substitute(
            range_label=range_label,
            range_buttons=range_buttons,
            body_content=error_body,
            favicon_href=favicon_href,
            pulse_mark_small=pulse_mark_small,
            pulse_mark_large=pulse_mark_large,
            version=VERSION,
            proxy_status_class=proxy_status_class,
            proxy_status_label=proxy_label,
            last_request_at="—",
            total_requests="0",
            updated_at=now_str,
            page_scripts=empty_scripts,
        )

    if data["total_requests"] == 0:
        empty_body = EMPTY_TEMPLATE.substitute(
            icon_svg=_pulse_mark_svg(28),
            db_path=_escape_html(DB_PATH),
        )
        empty_scripts = "<script>document.body.classList.remove('preload');setTimeout(function(){location.reload()},3000);</script>"
        return PAGE_TEMPLATE.substitute(
            range_label=range_label,
            range_buttons=range_buttons,
            body_content=empty_body,
            favicon_href=favicon_href,
            pulse_mark_small=pulse_mark_small,
            pulse_mark_large=pulse_mark_large,
            version=VERSION,
            proxy_status_class=proxy_status_class,
            proxy_status_label=proxy_label,
            last_request_at="—",
            total_requests="0",
            updated_at=now_str,
            page_scripts=empty_scripts,
        )

    data["time_range"] = time_range

    # Activity feed section
    activity_60s = data.get("activity_60s", [])
    recent_count = len(activity_60s)
    last_request_at = fmt_timestamp_full(data["requests"][0]["timestamp"]) if data.get("requests") else "—"

    activity_section = f"""<div class="activity-section loading-surface reveal reveal-delay-1">
  <div class="activity-label">Live Activity</div>
  <div class="activity-timeline" id="activityTimeline"></div>
  <div class="activity-count" id="activityCount"></div>
</div>"""

    stats_html = _build_stats_cards(data)
    spend_chart = _build_svg_spend_chart(data)
    model_breakdown = _build_model_breakdown(data)
    heatmap_html = _build_heatmap(data)
    requests_table = _build_requests_table(data, time_range=time_range, page=page)

    # Paid feature sections
    budgets_status = _fetch_budgets_with_status()
    all_budgets = _fetch_all_budgets()
    budget_alert_history = _fetch_budget_alert_history()
    budget_html = _build_budget_section(budgets_status, all_budgets, budget_alert_history)

    # Spending forecast
    forecast = _fetch_forecast_data()
    budget_forecasts = _fetch_budget_forecasts(budgets_status)
    forecast_html = _build_forecast_section(forecast, budgets_status, budget_forecasts)

    # Error monitoring
    error_data = _fetch_error_data(time_range)
    error_html = _build_error_section(error_data, time_range)

    reliability_data = _fetch_reliability_data(time_range)
    reliability_html = _build_reliability_section(reliability_data)
    context_audit_data = _fetch_context_audit_data(time_range)
    context_audit_html = _build_context_audit_section(context_audit_data)
    attention_html = _build_attention_section(budgets_status, budget_forecasts, reliability_data, error_data)

    opt_data = _fetch_optimizer_data()
    optimizer_html = _build_optimizer_section(opt_data)

    projects = _fetch_project_breakdown()
    project_html = _build_project_section(projects)

    # Insights (now with forecast and error data)
    insights_html = _build_insights(data, forecast=forecast, error_data=error_data, reliability_data=reliability_data)

    body = f"""{activity_section}

{stats_html}

  {attention_html}

  <div class="primary-grid">
    {budget_html}
    {forecast_html}
  </div>

  <div class="secondary-grid">
    {optimizer_html}
    {reliability_html}
  </div>

  {context_audit_html}

  {project_html}

  <!-- Charts -->
  <div class="charts-row">
    <div class="chart-panel loading-surface reveal reveal-delay-2">
      <div class="chart-title">Daily Spend</div>
      {spend_chart}
    </div>
    <div class="chart-panel loading-surface reveal reveal-delay-3">
      <div class="chart-title">Model Breakdown</div>
      {model_breakdown}
    </div>
  </div>

  <!-- Error Monitor -->
  {error_html}

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
        favicon_href=favicon_href,
        pulse_mark_small=pulse_mark_small,
        pulse_mark_large=pulse_mark_large,
        version=VERSION,
        proxy_status_class=proxy_status_class,
        proxy_status_label=proxy_label,
        last_request_at=last_request_at,
        total_requests=f"{data['total_requests']:,}",
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
    handler.end_headers()
    handler.wfile.write(body)


def _api_get_budgets():
    """Return all budgets with current status as JSON."""
    budgets = _fetch_budgets_with_status()
    return {"ok": True, "budgets": budgets}


def _api_get_budget_alert_history(limit=20):
    return {"ok": True, "alerts": _fetch_budget_alert_history(limit=limit)}


def _api_get_budget_forecasts():
    budgets = _fetch_budgets_with_status()
    return {"ok": True, "forecasts": _fetch_budget_forecasts(budgets)}


def _api_get_notifications(limit=20):
    proxied = _fetch_proxy_json(f'/api/notifications?limit={max(1, min(int(limit or 20), 50))}')
    if proxied:
        return {"ok": True, "notifications": proxied.get('notifications') or []}
    return {"ok": True, "notifications": []}


def _parse_budget_form(form_data):
    name = (form_data.get("name") or [""])[0].strip()
    period = (form_data.get("period") or ["monthly"])[0].strip()
    try:
        threshold = float((form_data.get("threshold") or ["0"])[0])
    except (ValueError, TypeError):
        return None, {"ok": False, "error": "Invalid threshold value"}
    provider_filter = (form_data.get("provider_filter") or [""])[0].strip() or None
    scope_kind_raw = (form_data.get("scope_kind") or ["global"])[0].strip()
    scope_kind = _normalize_budget_scope_kind(scope_kind_raw)
    scope_value = (form_data.get("scope_value") or [""])[0].strip() or None
    enabled_raw = (form_data.get("enabled") or ["1"])[0].strip().lower()
    enabled = enabled_raw not in ("0", "false", "off", "no")

    if not name:
        return None, {"ok": False, "error": "Name is required"}
    if period not in ("daily", "weekly", "monthly"):
        return None, {"ok": False, "error": "Period must be daily, weekly, or monthly"}
    if threshold <= 0:
        return None, {"ok": False, "error": "Threshold must be positive"}
    if scope_kind is None:
        return None, {"ok": False, "error": "Scope must be overall or project/source tag"}
    if scope_kind == "source_tag" and not scope_value:
        return None, {"ok": False, "error": "Project/source tag budgets require a scope value"}
    if scope_kind == "global":
        scope_value = None

    return {
        "name": name,
        "period": period,
        "threshold": threshold,
        "provider_filter": provider_filter,
        "scope_kind": scope_kind,
        "scope_value": scope_value,
        "enabled": enabled,
    }, None


def _api_create_budget(form_data):
    """Create a new budget from POST form data."""
    payload, error = _parse_budget_form(form_data)
    if error:
        return error

    try:
        conn = sqlite3.connect(DB_PATH)
        _ensure_budget_scope_columns(conn)
        _ensure_budget_alert_columns(conn)
        c = conn.cursor()
        c.execute(
            "INSERT INTO budgets (name, period, threshold_usd, provider_filter, scope_kind, scope_value, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (payload["name"], payload["period"], payload["threshold"], payload["provider_filter"], payload["scope_kind"], payload["scope_value"], 1 if payload["enabled"] else 0)
        )
        bid = c.lastrowid
        conn.commit()
        conn.close()
        return {"ok": True, "id": bid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_update_budget(budget_id, form_data):
    payload, error = _parse_budget_form(form_data)
    if error:
        return error

    try:
        conn = sqlite3.connect(DB_PATH)
        _ensure_budget_scope_columns(conn)
        _ensure_budget_alert_columns(conn)
        c = conn.cursor()
        c.execute(
            "UPDATE budgets SET name=?, period=?, threshold_usd=?, provider_filter=?, scope_kind=?, scope_value=?, enabled=? WHERE id=?",
            (payload["name"], payload["period"], payload["threshold"], payload["provider_filter"], payload["scope_kind"], payload["scope_value"], 1 if payload["enabled"] else 0, budget_id)
        )
        _resolve_budget_alerts(c, budget_id)
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_set_budget_enabled(budget_id, form_data):
    enabled_raw = (form_data.get("enabled") or ["1"])[0].strip().lower()
    enabled = enabled_raw not in ("0", "false", "off", "no")
    try:
        conn = sqlite3.connect(DB_PATH)
        _ensure_budget_alert_columns(conn)
        c = conn.cursor()
        c.execute("UPDATE budgets SET enabled=? WHERE id=?", (1 if enabled else 0, budget_id))
        if not enabled:
            _resolve_budget_alerts(c, budget_id)
        conn.commit()
        conn.close()
        return {"ok": True}
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


def _export_csv(time_range):
    """Generate CSV content for all requests in the given time range."""
    import csv
    import io

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    where = _time_filter_sql(time_range, "WHERE")

    try:
        c.execute(
            f"SELECT timestamp, provider, model, input_tokens, output_tokens, "
            f"COALESCE(cached_tokens, 0) as cached_tokens, "
            f"COALESCE(reasoning_tokens, 0) as reasoning_tokens, "
            f"cost_usd, latency_ms, "
            f"COALESCE(tokens_per_second, 0) as tokens_per_second, "
            f"COALESCE(time_to_first_token_ms, 0) as time_to_first_token_ms, "
            f"is_streaming, "
            f"COALESCE(source_tag, '') as source_tag, "
            f"COALESCE(provider_type, 'api') as provider_type, "
            f"COALESCE(error_message, '') as error_message "
            f"FROM requests{where} ORDER BY timestamp DESC"
        )
        rows = c.fetchall()
    except Exception:
        rows = []

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "provider", "model", "input_tokens", "output_tokens",
        "cached_tokens", "reasoning_tokens", "cost_usd", "latency_ms",
        "tokens_per_second", "time_to_first_token_ms", "is_streaming",
        "source_tag", "provider_type", "error_message",
    ])
    for r in rows:
        writer.writerow([
            r["timestamp"], r["provider"], r["model"],
            r["input_tokens"], r["output_tokens"],
            r["cached_tokens"], r["reasoning_tokens"],
            f"{r['cost_usd']:.6f}", r["latency_ms"],
            f"{r['tokens_per_second']:.1f}", r["time_to_first_token_ms"],
            bool(r["is_streaming"]),
            r["source_tag"], r["provider_type"], r["error_message"],
        ])

    return output.getvalue()


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API endpoint: GET /api/budgets
        if path == "/api/budgets":
            _json_response(self, 200, _api_get_budgets())
            return

        if path == "/api/budget-alerts":
            params = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit", ["20"])[0])
            except (ValueError, TypeError):
                limit = 20
            _json_response(self, 200, _api_get_budget_alert_history(limit))
            return

        if path == "/api/budget-forecasts":
            _json_response(self, 200, _api_get_budget_forecasts())
            return

        if path == "/api/notifications":
            params = parse_qs(parsed.query)
            try:
                limit = int((params.get('limit') or ['20'])[0] or 20)
            except (TypeError, ValueError):
                limit = 20
            _json_response(self, 200, _api_get_notifications(limit))
            return

        if path == "/api/context-audit":
            params = parse_qs(parsed.query)
            time_range = (params.get("range") or ["today"])[0]
            _json_response(self, 200, {"ok": True, "context_audit": _fetch_context_audit_data(time_range)})
            return

        # CSV export endpoint
        if path == "/export/csv":
            params = parse_qs(parsed.query)
            time_range = params.get("range", ["all"])[0]
            if time_range not in RANGE_LABELS:
                time_range = "all"

            try:
                csv_content = _export_csv(time_range)
                csv_bytes = csv_content.encode("utf-8")
                date_str = datetime.now().strftime("%Y-%m-%d")
                filename = f"tokenpulse-export-{time_range}-{date_str}.csv"

                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(csv_bytes)))
                self.end_headers()
                self.wfile.write(csv_bytes)
            except Exception as e:
                error_body = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(error_body)))
                self.end_headers()
                self.wfile.write(error_body)
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

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else ""
        form_data = parse_qs(raw_body)

        if path.startswith("/api/budgets/") and path.endswith("/enabled"):
            try:
                bid = int(path.split("/")[-2])
            except (ValueError, IndexError):
                _json_response(self, 400, {"ok": False, "error": "Invalid budget ID"})
                return
            result = _api_set_budget_enabled(bid, form_data)
            _json_response(self, 200 if result.get("ok") else 400, result)
            return

        if path.startswith("/api/budgets/"):
            try:
                bid = int(path.split("/")[-1])
            except (ValueError, IndexError):
                _json_response(self, 400, {"ok": False, "error": "Invalid budget ID"})
                return
            result = _api_update_budget(bid, form_data)
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    import time

    PORT = 4200
    MAX_RETRIES = 5

    ThreadingHTTPServer.allow_reuse_address = True

    for attempt in range(MAX_RETRIES):
        try:
            server = ThreadingHTTPServer(("", PORT), DashboardHandler)
            break
        except OSError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"Port {PORT} busy, retrying in 2s (attempt {attempt + 1}/{MAX_RETRIES})...",
                      flush=True)
                time.sleep(2)
            else:
                print(f"FATAL: Could not bind to port {PORT} after {MAX_RETRIES} attempts: {e}",
                      flush=True)
                raise
    print(f"TokenPulse Web Dashboard v{VERSION}", flush=True)
    print(f"  -> http://0.0.0.0:{PORT}", flush=True)
    print(f"  -> Database: {DB_PATH}", flush=True)
    server.serve_forever()
