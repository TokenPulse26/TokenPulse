#!/usr/bin/env python3
"""TokenPulse Web Dashboard — lightweight web view for remote access"""
import sqlite3
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db")
VERSION = "0.1.0"

PROVIDER_COLORS = {
    "openai":    ("rgba(16,163,127,0.15)", "#10a37f"),
    "anthropic": ("rgba(212,165,116,0.15)", "#d4a574"),
    "cliproxy":  ("rgba(212,165,116,0.15)", "#d4a574"),
    "google":    ("rgba(66,133,244,0.15)", "#4285f4"),
    "mistral":   ("rgba(255,112,0,0.15)", "#ff7000"),
    "groq":      ("rgba(245,80,54,0.15)", "#f55036"),
    "ollama":    ("rgba(255,255,255,0.08)", "#ffffff"),
    "lmstudio":  ("rgba(139,92,246,0.15)", "#8b5cf6"),
}

RANGE_LABELS = {
    "today": "Today",
    "7d": "7 Days",
    "30d": "30 Days",
    "all": "All Time",
}

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0f1117; color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    padding: 20px; min-height: 100vh;
}
a { color: inherit; text-decoration: none; }
h1 { font-size: 26px; font-weight: 700; color: #f8fafc; }
h2 { font-size: 16px; font-weight: 600; color: #f8fafc; margin-bottom: 14px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.badge { background: rgba(34,197,94,0.13); color: #22c55e; padding: 3px 10px;
         border-radius: 20px; font-size: 11px; font-weight: 600; }
.subtitle { color: #64748b; font-size: 12px; margin-bottom: 18px; }
.range-bar { display: flex; gap: 8px; margin-bottom: 22px; flex-wrap: wrap; }
.range-btn {
    padding: 6px 16px; border-radius: 8px; font-size: 13px; font-weight: 500;
    background: #1a1d27; border: 1px solid #2a2d3a; color: #94a3b8; cursor: pointer;
    transition: all 0.15s;
}
.range-btn:hover { border-color: #3a3d4a; color: #e2e8f0; }
.range-btn.active { background: #22c55e; border-color: #22c55e; color: #0f1117; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
         gap: 14px; margin-bottom: 28px; }
.card { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 12px; padding: 18px; }
.card-label { color: #64748b; font-size: 11px; text-transform: uppercase;
              letter-spacing: 0.8px; margin-bottom: 8px; }
.card-value { font-size: 28px; font-weight: 700; color: #f8fafc; line-height: 1; }
.card-sub { color: #64748b; font-size: 11px; margin-top: 6px; }
.green { color: #22c55e; }
.blue  { color: #60a5fa; }
.purple { color: #a78bfa; }
.section { margin-bottom: 28px; }
.model-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.model-card { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px; padding: 14px; }
.model-name { font-size: 13px; font-weight: 600; color: #f8fafc; margin-bottom: 6px;
              white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.model-meta { color: #94a3b8; font-size: 11px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.model-cost { font-size: 16px; font-weight: 700; margin-top: 8px; }
.bar-bg { height: 3px; background: #2a2d3a; border-radius: 2px; margin-top: 8px; }
.bar-fill { height: 3px; border-radius: 2px; }
.table-wrap { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 12px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
th { background: #1e2030; color: #64748b; font-size: 10px; text-transform: uppercase;
     letter-spacing: 0.8px; padding: 10px 14px; text-align: left; white-space: nowrap; }
td { padding: 9px 14px; border-top: 1px solid #1e2030; font-size: 12px; }
tr:hover td { background: #1e2030; }
.tag { display: inline-block; padding: 2px 7px; border-radius: 4px;
       font-size: 10px; font-weight: 600; white-space: nowrap; }
.cost-api { color: #22c55e; }
.cost-sub { color: #94a3b8; font-style: italic; }
.cost-local { color: #60a5fa; font-style: italic; }
.empty { text-align: center; padding: 50px; color: #64748b; font-size: 14px; }
.footer { margin-top: 32px; text-align: center; color: #374151; font-size: 11px; padding: 12px; }
@media (max-width: 600px) {
    body { padding: 12px; }
    .cards { grid-template-columns: 1fr 1fr; }
    td, th { padding: 8px 10px; }
    .card-value { font-size: 22px; }
    table { font-size: 11px; }
}
"""

def relative_time(ts_str):
    if not ts_str:
        return "—"
    try:
        ts = datetime.fromisoformat(ts_str.replace("T", " ").replace("Z", "").split(".")[0])
        now = datetime.now()
        diff = (now - ts).total_seconds()
        if diff < 60:
            return f"{int(diff)}s ago"
        elif diff < 3600:
            return f"{int(diff / 60)}m ago"
        elif diff < 86400:
            return f"{int(diff / 3600)}h ago"
        else:
            return ts_str[:10]
    except Exception:
        return ts_str[:16] if ts_str else "—"

def provider_tag(prov):
    prov = prov or "unknown"
    bg, fg = PROVIDER_COLORS.get(prov, ("rgba(255,255,255,0.08)", "#94a3b8"))
    return f'<span class="tag" style="background:{bg};color:{fg}">{prov}</span>'

def fmt_tokens(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"

def time_filter_sql(time_range, and_prefix=False):
    prefix = " AND " if and_prefix else " WHERE "
    if time_range == "today":
        return f"{prefix}timestamp >= datetime('now', 'start of day')"
    elif time_range == "7d":
        return f"{prefix}timestamp >= datetime('now', '-7 days')"
    elif time_range == "30d":
        return f"{prefix}timestamp >= datetime('now', '-30 days')"
    return ""

def get_stats(time_range="today"):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        tf = time_filter_sql(time_range)
        tf_and = time_filter_sql(time_range, and_prefix=True)

        # Summary cards
        c.execute(f"SELECT COALESCE(SUM(cost_usd),0), COUNT(*), "
                  f"COALESCE(SUM(input_tokens+output_tokens),0) FROM requests{tf}")
        total_cost, total_requests, total_tokens = c.fetchone()

        # Provider-type breakdown (graceful if column missing)
        api_cost = sub_tokens = local_tokens = 0
        try:
            c.execute(f"SELECT COALESCE(SUM(cost_usd),0) FROM requests WHERE 1=1{tf_and} "
                      f"AND COALESCE(provider_type,'api')='api'")
            api_cost = c.fetchone()[0] or 0

            c.execute(f"SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM requests "
                      f"WHERE 1=1{tf_and} AND provider_type='subscription'")
            sub_tokens = c.fetchone()[0] or 0

            c.execute(f"SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM requests "
                      f"WHERE 1=1{tf_and} AND provider_type='local'")
            local_tokens = c.fetchone()[0] or 0
        except Exception:
            api_cost = total_cost

        # Model breakdown — sorted by total tokens desc
        c.execute(f"""SELECT model, provider, COUNT(*) as cnt,
                     COALESCE(SUM(input_tokens),0) as inp,
                     COALESCE(SUM(output_tokens),0) as outp,
                     COALESCE(SUM(cost_usd),0) as cost,
                     COALESCE(provider_type,'api') as ptype
                     FROM requests{tf}
                     GROUP BY model, provider
                     ORDER BY (inp+outp) DESC LIMIT 12""")
        models = c.fetchall()

        max_tokens = max((m["inp"] + m["outp"] for m in models), default=1) if models else 1

        # Recent requests
        c.execute(f"""SELECT timestamp, provider, model, input_tokens, output_tokens,
                     cost_usd, latency_ms, is_streaming,
                     COALESCE(provider_type,'api') as ptype
                     FROM requests{tf}
                     ORDER BY timestamp DESC LIMIT 50""")
        rows = c.fetchall()
        conn.close()

        # Build range selector
        range_html = '<div class="range-bar">'
        for key, label in RANGE_LABELS.items():
            active = " active" if key == time_range else ""
            range_html += f'<a href="?range={key}" class="range-btn{active}">{label}</a>'
        range_html += '</div>'

        # Cards
        cards_html = f'''<div class="cards">
  <div class="card">
    <div class="card-label">API Spend</div>
    <div class="card-value green">${api_cost:.4f}</div>
    <div class="card-sub">paid API calls</div>
  </div>
  <div class="card">
    <div class="card-label">Subscription Usage</div>
    <div class="card-value blue">{fmt_tokens(sub_tokens)}</div>
    <div class="card-sub">tokens · included in plan</div>
  </div>
  <div class="card">
    <div class="card-label">Local Usage</div>
    <div class="card-value purple">{fmt_tokens(local_tokens)}</div>
    <div class="card-sub">tokens · free (local)</div>
  </div>
  <div class="card">
    <div class="card-label">Requests</div>
    <div class="card-value">{total_requests:,}</div>
    <div class="card-sub">{fmt_tokens(total_tokens)} total tokens</div>
  </div>
</div>'''

        # Model breakdown section
        if models:
            model_cards = ""
            for m in models:
                prov = m["provider"] or "unknown"
                ptype = m["ptype"]
                tok = m["inp"] + m["outp"]
                bar_w = int(tok / max_tokens * 100) if max_tokens > 0 else 0

                if ptype == "subscription":
                    cost_html = f'<div class="model-cost" style="color:#60a5fa">included</div>'
                    bar_color = "#60a5fa"
                elif ptype == "local":
                    cost_html = f'<div class="model-cost" style="color:#a78bfa">free</div>'
                    bar_color = "#a78bfa"
                else:
                    cost_html = f'<div class="model-cost green">${m["cost"]:.4f}</div>'
                    bar_color = "#22c55e"

                model_cards += f'''<div class="model-card">
  <div class="model-name" title="{m["model"]}">{m["model"] or "unknown"}</div>
  <div class="model-meta">{provider_tag(prov)} <span>{m["cnt"]} reqs</span> <span>{fmt_tokens(tok)} tokens</span></div>
  {cost_html}
  <div class="bar-bg"><div class="bar-fill" style="width:{bar_w}%;background:{bar_color}"></div></div>
</div>'''

            model_section = f'<div class="section"><h2>Model Breakdown</h2><div class="model-grid">{model_cards}</div></div>'
        else:
            model_section = ""

        # Request table
        if rows:
            table = """<table>
<tr>
  <th>Time</th><th>Provider</th><th>Model</th>
  <th>Input</th><th>Output</th><th>Cost</th><th>Latency</th>
</tr>"""
            for r in rows:
                ts = relative_time(r["timestamp"])
                prov = r["provider"] or "unknown"
                ptype = r["ptype"]
                model_name = r["model"] or "unknown"
                inp = fmt_tokens(r["input_tokens"])
                out = fmt_tokens(r["output_tokens"])
                lat = f'{r["latency_ms"]:,}ms' if r["latency_ms"] else "—"
                stream_icon = " ⟳" if r["is_streaming"] else ""

                if ptype == "subscription":
                    cost_html = '<span class="cost-sub">included</span>'
                elif ptype == "local":
                    cost_html = '<span class="cost-local">free</span>'
                else:
                    cost_val = r["cost_usd"] or 0
                    cost_html = f'<span class="cost-api">${cost_val:.4f}</span>'

                table += f"""<tr>
  <td style="color:#64748b;white-space:nowrap">{ts}</td>
  <td>{provider_tag(prov)}</td>
  <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{model_name}">{model_name}{stream_icon}</td>
  <td>{inp}</td><td>{out}</td><td>{cost_html}</td>
  <td style="color:#64748b">{lat}</td>
</tr>"""
            table += "</table>"
        else:
            table = '<div class="empty">No requests in this time range yet.</div>'

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        range_label = RANGE_LABELS.get(time_range, time_range)

        return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenPulse · {range_label}</title>
<style>{CSS}</style>
</head><body>
<div class="header">
  <h1>TokenPulse</h1>
  <span class="badge">● Live</span>
</div>
<p class="subtitle">Auto-refreshes every 5s &nbsp;·&nbsp; {range_label} &nbsp;·&nbsp; {now_str}</p>

{range_html}
{cards_html}
{model_section}
<div class="section">
  <h2>Recent Requests</h2>
  <div class="table-wrap">{table}</div>
</div>

<div class="footer">TokenPulse v{VERSION} &nbsp;·&nbsp; Proxy: localhost:4100 &nbsp;·&nbsp; {now_str}</div>

<script>setTimeout(() => location.reload(), 5000);</script>
</body></html>"""

    except Exception as e:
        return f"""<html><body style="background:#0f1117;color:white;padding:40px;font-family:sans-serif">
<h1>TokenPulse</h1>
<p style="color:#ef4444;margin-top:20px">Database error: {e}</p>
<p style="color:#64748b;margin-top:12px">DB path: {DB_PATH}</p>
</body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        time_range = params.get("range", ["today"])[0]
        if time_range not in RANGE_LABELS:
            time_range = "today"

        html = get_stats(time_range).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 4200), DashboardHandler)
    print(f"TokenPulse Web Dashboard v{VERSION} running on http://0.0.0.0:4200")
    server.serve_forever()
