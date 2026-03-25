#!/usr/bin/env python3
"""TokenPulse Web Dashboard — production-quality web view for token usage analytics."""
import sqlite3
import os
import json
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
VERSION = "0.1.0"

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
# HTML / CSS Template
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenPulse · $range_label</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* ── Reset ───────────────────────────────────────────── */
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}

/* ── Base ────────────────────────────────────────────── */
body{
  background:#0f1117;color:#c9d1d9;
  font-family:'Inter',system-ui,-apple-system,sans-serif;
  line-height:1.5;min-height:100vh;
}
a{color:inherit;text-decoration:none}

/* ── Layout shell ────────────────────────────────────── */
.shell{max-width:1320px;margin:0 auto;padding:24px 28px 40px}

/* ── Header ──────────────────────────────────────────── */
.header{
  display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:16px;margin-bottom:28px;
}
.header-left{display:flex;align-items:center;gap:14px}
.wordmark{font-size:24px;font-weight:800;color:#f0f6fc;letter-spacing:-0.5px}
.live-badge{
  display:inline-flex;align-items:center;gap:6px;
  background:rgba(34,197,94,0.1);color:#22c55e;
  padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;
}
.pulse-dot{
  width:7px;height:7px;border-radius:50%;background:#22c55e;
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{
  0%,100%{opacity:1;transform:scale(1)}
  50%{opacity:.4;transform:scale(.85)}
}

/* ── Range buttons ───────────────────────────────────── */
.range-bar{display:flex;gap:6px;flex-wrap:wrap}
.range-btn{
  padding:6px 18px;border-radius:8px;font-size:13px;font-weight:500;
  background:#1a1d27;border:1px solid #2a2d3a;color:#8b949e;
  cursor:pointer;transition:all .15s ease;
}
.range-btn:hover{border-color:#3d4250;color:#e6edf3}
.range-btn.active{background:#22c55e;border-color:#22c55e;color:#0f1117;font-weight:600}

/* ── Stat cards ──────────────────────────────────────── */
.stats{
  display:grid;grid-template-columns:repeat(4,1fr);
  gap:16px;margin-bottom:28px;
}
.stat-card{
  background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;
  padding:22px 24px;
  transition:border-color .2s;
}
.stat-card:hover{border-color:#3d4250}
.stat-label{
  font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.8px;color:#8b949e;margin-bottom:10px;
}
.stat-value{font-size:30px;font-weight:800;color:#f0f6fc;line-height:1}
.stat-sub{font-size:11px;color:#6e7681;margin-top:8px}
.clr-green{color:#22c55e}
.clr-blue{color:#58a6ff}
.clr-purple{color:#a78bfa}

/* ── Charts row ──────────────────────────────────────── */
.charts-row{
  display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px;
}
.chart-panel{
  background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;
  padding:22px 24px;min-height:320px;display:flex;flex-direction:column;
}
.chart-title{
  font-size:14px;font-weight:700;color:#f0f6fc;margin-bottom:18px;
}

/* Daily spend chart ─────────────────────────────────── */
.spend-chart{
  flex:1;display:flex;align-items:flex-end;gap:6px;
  padding-bottom:28px;position:relative;
}
.chart-col{
  flex:1;display:flex;flex-direction:column;justify-content:flex-end;
  align-items:stretch;position:relative;min-width:0;
}
.chart-bar{
  display:flex;flex-direction:column;justify-content:flex-end;
  border-radius:5px 5px 0 0;overflow:hidden;min-height:2px;
  transition:opacity .2s;cursor:default;
}
.chart-bar:hover{opacity:.85}
.bar-segment{min-height:0;transition:height .3s ease}
.chart-date{
  position:absolute;bottom:-24px;left:50%;transform:translateX(-50%);
  font-size:10px;color:#6e7681;white-space:nowrap;
}

/* No-data chart placeholder */
.chart-empty{
  flex:1;display:flex;align-items:center;justify-content:center;
  color:#6e7681;font-size:13px;
}

/* ── Model breakdown ─────────────────────────────────── */
.model-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.model-item{
  background:#161922;border:1px solid #2a2d3a;border-radius:10px;
  padding:14px 16px;transition:border-color .2s;
}
.model-item:hover{border-color:#3d4250}
.model-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.model-name{
  font-size:13px;font-weight:600;color:#f0f6fc;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;
}
.model-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.model-meta span{font-size:11px;color:#8b949e}
.model-cost{font-size:15px;font-weight:700;white-space:nowrap}
.usage-bar-bg{height:3px;background:#2a2d3a;border-radius:2px;margin-top:10px}
.usage-bar-fill{height:3px;border-radius:2px;transition:width .3s ease}

/* ── Provider badge ──────────────────────────────────── */
.prov-badge{
  display:inline-block;padding:2px 8px;border-radius:4px;
  font-size:10px;font-weight:600;white-space:nowrap;
}

/* ── Requests table ──────────────────────────────────── */
.table-section{margin-bottom:28px}
.section-title{font-size:14px;font-weight:700;color:#f0f6fc;margin-bottom:14px}
.table-wrap{
  background:#1a1d27;border:1px solid #2a2d3a;border-radius:14px;
  overflow:hidden;overflow-x:auto;
}
table{width:100%;border-collapse:collapse;min-width:720px}
th{
  background:#161922;color:#6e7681;font-size:10px;font-weight:600;
  text-transform:uppercase;letter-spacing:.8px;
  padding:12px 16px;text-align:left;white-space:nowrap;
  border-bottom:1px solid #2a2d3a;
}
td{
  padding:11px 16px;font-size:12px;
  border-top:1px solid rgba(42,45,58,.5);
  white-space:nowrap;
}
tr:hover td{background:rgba(22,25,34,.6)}
.td-time{color:#6e7681}
.td-model{
  max-width:200px;overflow:hidden;text-overflow:ellipsis;color:#c9d1d9;
}
.cost-api{color:#22c55e;font-weight:600}
.cost-sub{color:#8b949e;font-style:italic}
.cost-local{color:#a78bfa;font-style:italic}
.stream-badge{
  display:inline-block;padding:1px 6px;border-radius:3px;
  background:rgba(88,166,255,.1);color:#58a6ff;
  font-size:9px;font-weight:600;margin-left:4px;
}
.latency{color:#6e7681}

/* ── Footer ──────────────────────────────────────────── */
.footer{
  text-align:center;color:#30363d;font-size:11px;padding:16px 0;
  border-top:1px solid #1a1d27;
}

/* ── Empty state ─────────────────────────────────────── */
.empty-state{
  text-align:center;padding:60px 20px;color:#6e7681;
}
.empty-state h2{color:#f0f6fc;font-size:20px;margin-bottom:12px}
.empty-state p{max-width:480px;margin:0 auto 8px;font-size:13px;line-height:1.7}
.empty-state code{
  background:#1a1d27;padding:2px 6px;border-radius:4px;font-size:12px;color:#c9d1d9;
}

/* ── Error state ─────────────────────────────────────── */
.error-state{
  text-align:center;padding:60px 20px;
}
.error-state h2{color:#f85149;font-size:20px;margin-bottom:12px}
.error-state p{color:#6e7681;font-size:13px}
.error-state code{
  display:block;margin-top:16px;background:#1a1d27;padding:12px;
  border-radius:8px;color:#c9d1d9;font-size:12px;text-align:left;
  max-width:600px;margin-left:auto;margin-right:auto;word-break:break-all;
}

/* ── Responsive ──────────────────────────────────────── */
@media(max-width:900px){
  .charts-row{grid-template-columns:1fr}
  .stats{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:600px){
  .shell{padding:16px 14px 32px}
  .stats{grid-template-columns:1fr 1fr;gap:10px}
  .stat-value{font-size:22px}
  .stat-card{padding:16px}
  .header{gap:10px}
  .wordmark{font-size:20px}
  td,th{padding:8px 10px;font-size:11px}
  .model-name{max-width:140px}
}
@media(max-width:400px){
  .stats{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="shell">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <span class="wordmark">TokenPulse</span>
      <span class="live-badge"><span class="pulse-dot"></span> Live</span>
    </div>
    <div class="range-bar">
      $range_buttons
    </div>
  </div>

  $body_content

  <div class="footer">
    TokenPulse v$version &nbsp;&middot;&nbsp; Proxy: localhost:4100 &nbsp;&middot;&nbsp; Last updated: $updated_at
  </div>
</div>

<script>setTimeout(function(){location.reload()},5000);</script>
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
    """Return hex color for a provider."""
    return PROVIDER_COLORS.get((provider or "").lower(), "#8b949e")


def _provider_bg(provider):
    """Return rgba background for a provider badge."""
    c = _provider_color(provider)
    # Convert hex to rgba at 0.12 opacity
    if c.startswith("#") and len(c) == 7:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return f"rgba({r},{g},{b},0.12)"
    return "rgba(255,255,255,0.08)"


def provider_badge_html(provider):
    """Render a colored provider badge."""
    p = (provider or "unknown").lower()
    color = _provider_color(p)
    bg = _provider_bg(p)
    label = p if p != "lmstudio" else "LM Studio"
    return f'<span class="prov-badge" style="background:{bg};color:{color}">{label}</span>'


def fmt_tokens(n):
    """Format token count with comma separators."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_cost(cost):
    """Format cost with appropriate decimal places."""
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
    """Format latency value."""
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
    """Convert timestamp to relative human-readable string."""
    if not ts_str:
        return "—"
    try:
        ts = datetime.fromisoformat(
            ts_str.replace("T", " ").replace("Z", "").split(".")[0]
        )
        now = datetime.now()
        diff = (now - ts).total_seconds()
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
    """Return a SQL clause filtering by time range."""
    if time_range == "today":
        return f" {prefix} timestamp >= datetime('now', 'start of day')"
    elif time_range == "7d":
        return f" {prefix} timestamp >= datetime('now', '-7 days')"
    elif time_range == "30d":
        return f" {prefix} timestamp >= datetime('now', '-30 days')"
    return ""  # 'all' — no filter


def _chart_days(time_range):
    """How many days to show in the spend chart."""
    if time_range in ("today", "7d"):
        return 7
    return 30


def _escape_html(text):
    """Minimal HTML escaping."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
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

    # ── Summary stats ────────────────────────────────
    c.execute(
        f"SELECT COUNT(*) as cnt, "
        f"COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens "
        f"FROM requests{where}"
    )
    row = c.fetchone()
    total_requests = row["cnt"]
    total_tokens = row["total_tokens"]

    # Provider-type breakdowns (graceful fallback if provider_type missing)
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
        # provider_type column might not exist
        c.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0) as v FROM requests{where}"
        )
        api_cost = c.fetchone()["v"] or 0

    # ── Daily spend chart ────────────────────────────
    days = _chart_days(time_range)
    c.execute(
        f"SELECT date(timestamp) as day, "
        f"LOWER(provider) as prov, "
        f"COALESCE(SUM(cost_usd), 0) as cost "
        f"FROM requests "
        f"WHERE timestamp >= datetime('now', '-{days} days') "
        f"GROUP BY day, prov ORDER BY day"
    )
    daily_raw = c.fetchall()

    # ── Model breakdown ──────────────────────────────
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

    # ── Recent requests ──────────────────────────────
    c.execute(
        f"SELECT timestamp, provider, model, input_tokens, output_tokens, "
        f"cost_usd, latency_ms, is_streaming, "
        f"COALESCE(provider_type, 'api') as ptype "
        f"FROM requests{where} "
        f"ORDER BY timestamp DESC LIMIT 50"
    )
    requests = [dict(r) for r in c.fetchall()]
    conn.close()

    return {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "api_cost": api_cost,
        "sub_tokens": sub_tokens,
        "local_tokens": local_tokens,
        "daily_raw": daily_raw,
        "models": models,
        "requests": requests,
        "chart_days": days,
    }


# ---------------------------------------------------------------------------
# HTML Builders
# ---------------------------------------------------------------------------


def _build_range_buttons(active):
    """Build HTML for time range selector buttons."""
    parts = []
    for key, label in RANGE_LABELS.items():
        cls = "range-btn active" if key == active else "range-btn"
        parts.append(f'<a href="?range={key}" class="{cls}">{label}</a>')
    return "\n      ".join(parts)


def _build_stats_cards(data):
    """Build the 4 stat cards."""
    return f"""<div class="stats">
  <div class="stat-card">
    <div class="stat-label">API Spend</div>
    <div class="stat-value clr-green">{fmt_cost(data['api_cost'])}</div>
    <div class="stat-sub">paid API calls</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Subscription Usage</div>
    <div class="stat-value clr-blue">{fmt_tokens(data['sub_tokens'])}</div>
    <div class="stat-sub">tokens &middot; included in plan</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Local Usage</div>
    <div class="stat-value clr-purple">{fmt_tokens(data['local_tokens'])}</div>
    <div class="stat-sub">tokens &middot; free</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Total Requests</div>
    <div class="stat-value">{data['total_requests']:,}</div>
    <div class="stat-sub">{fmt_tokens(data['total_tokens'])} total tokens</div>
  </div>
</div>"""


def _build_spend_chart(data):
    """Build the CSS-only daily spend bar chart."""
    daily_raw = data["daily_raw"]
    days = data["chart_days"]

    if not daily_raw:
        return '<div class="chart-empty">No spend data for this period</div>'

    # Organize by day → { day: { provider: cost } }
    day_data = {}
    all_days = set()
    for r in daily_raw:
        d = r["day"]
        all_days.add(d)
        if d not in day_data:
            day_data[d] = {}
        prov = r["prov"] or "unknown"
        day_data[d][prov] = (day_data[d].get(prov, 0)) + (r["cost"] or 0)

    # Build sorted list of days (fill gaps)
    today = datetime.now().date()
    date_range = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        date_range.append(d)

    # Find max daily total for scaling
    max_daily = 0
    for d in date_range:
        total = sum(day_data.get(d, {}).values())
        if total > max_daily:
            max_daily = total

    if max_daily == 0:
        return '<div class="chart-empty">No spend data for this period</div>'

    # Build bars
    cols_html = []
    for d in date_range:
        providers = day_data.get(d, {})
        day_total = sum(providers.values())
        bar_height = max(int((day_total / max_daily) * 100), 1) if day_total > 0 else 0
        day_label = d[5:]  # MM-DD

        # Tooltip
        tooltip = f"{d}: ${day_total:.4f}"

        # Build segments (bottom to top)
        segments_html = ""
        if day_total > 0:
            for prov, cost in sorted(providers.items(), key=lambda x: x[1]):
                pct = max(int((cost / day_total) * 100), 5) if day_total > 0 else 0
                color = _provider_color(prov)
                segments_html += (
                    f'<div class="bar-segment" '
                    f'style="height:{pct}%;background:{color}"></div>'
                )

        cols_html.append(
            f'<div class="chart-col">'
            f'<div class="chart-bar" style="height:{bar_height}%" title="{_escape_html(tooltip)}">'
            f"{segments_html}"
            f"</div>"
            f'<span class="chart-date">{day_label}</span>'
            f"</div>"
        )

    return '<div class="spend-chart">' + "\n".join(cols_html) + "</div>"


def _build_model_breakdown(data):
    """Build the model breakdown cards."""
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
        ptype = m["ptype"]
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


def _build_requests_table(data):
    """Build the recent requests table."""
    requests = data["requests"]
    if not requests:
        return (
            '<div class="table-wrap">'
            '<div class="chart-empty" style="padding:40px">'
            "No requests in this time range"
            "</div></div>"
        )

    rows_html = []
    for r in requests:
        ts = relative_time(r["timestamp"])
        prov = r["provider"] or "unknown"
        ptype = r["ptype"]
        model_name = _escape_html(r["model"] or "unknown")
        inp = fmt_tokens(r["input_tokens"])
        out = fmt_tokens(r["output_tokens"])
        lat = fmt_latency(r["latency_ms"])

        # Cost display
        if ptype == "subscription":
            cost_td = '<span class="cost-sub">included</span>'
        elif ptype == "local":
            cost_td = '<span class="cost-local">free</span>'
        else:
            cost_td = f'<span class="cost-api">{fmt_cost(r["cost_usd"])}</span>'

        # Type column
        type_html = ""
        if r.get("is_streaming"):
            type_html = '<span class="stream-badge">STREAM</span>'

        rows_html.append(
            f"<tr>"
            f'<td class="td-time">{ts}</td>'
            f"<td>{provider_badge_html(prov)}</td>"
            f'<td class="td-model" title="{model_name}">{model_name}</td>'
            f"<td>{inp}</td>"
            f"<td>{out}</td>"
            f"<td>{cost_td}</td>"
            f'<td class="latency">{lat}</td>'
            f"<td>{type_html}</td>"
            f"</tr>"
        )

    return (
        '<div class="table-wrap"><table>'
        "<tr>"
        "<th>Time</th><th>Provider</th><th>Model</th>"
        "<th>Input</th><th>Output</th><th>Cost</th>"
        "<th>Latency</th><th>Type</th>"
        "</tr>"
        + "\n".join(rows_html)
        + "</table></div>"
    )


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------


def build_page(time_range):
    """Build the complete dashboard HTML page."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    range_label = RANGE_LABELS.get(time_range, "Today")
    range_buttons = _build_range_buttons(time_range)

    # Try to fetch data
    try:
        data = _fetch_data(time_range)
    except Exception as e:
        error_body = ERROR_TEMPLATE.substitute(
            error_message=_escape_html(str(e)),
            db_path=_escape_html(DB_PATH),
        )
        return PAGE_TEMPLATE.substitute(
            range_label=range_label,
            range_buttons=range_buttons,
            body_content=error_body,
            version=VERSION,
            updated_at=now_str,
        )

    # Check for empty database
    if data["total_requests"] == 0:
        empty_body = EMPTY_TEMPLATE.substitute(
            db_path=_escape_html(DB_PATH),
        )
        return PAGE_TEMPLATE.substitute(
            range_label=range_label,
            range_buttons=range_buttons,
            body_content=empty_body,
            version=VERSION,
            updated_at=now_str,
        )

    # Build sections
    stats_html = _build_stats_cards(data)
    spend_chart = _build_spend_chart(data)
    model_breakdown = _build_model_breakdown(data)
    requests_table = _build_requests_table(data)

    body = f"""{stats_html}

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

  <!-- Recent Requests -->
  <div class="table-section">
    <div class="section-title">Recent Requests</div>
    {requests_table}
  </div>"""

    return PAGE_TEMPLATE.substitute(
        range_label=range_label,
        range_buttons=range_buttons,
        body_content=body,
        version=VERSION,
        updated_at=now_str,
    )


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        time_range = params.get("range", ["today"])[0]
        if time_range not in RANGE_LABELS:
            time_range = "today"

        html = build_page(time_range).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, fmt, *args):
        pass  # Suppress default logging


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 4200), DashboardHandler)
    print(f"TokenPulse Web Dashboard v{VERSION}")
    print(f"  → http://0.0.0.0:4200")
    print(f"  → Database: {DB_PATH}")
    server.serve_forever()
