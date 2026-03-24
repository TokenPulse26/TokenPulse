#!/usr/bin/env python3
"""TokenPulse Web Dashboard — lightweight web view for remote access"""
import sqlite3
import json
import os
import string
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

DB_PATH = os.path.expanduser("~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db")

TEMPLATE = string.Template("""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenPulse Dashboard</title>
<meta http-equiv="refresh" content="10">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; padding: 24px; min-height: 100vh; }
h1 { font-size: 28px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }
h2 { font-size: 18px; font-weight: 600; color: #f8fafc; margin-bottom: 16px; }
.header { display: flex; align-items: center; margin-bottom: 24px; }
.subtitle { color: #64748b; font-size: 13px; margin-bottom: 24px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
.stat-card { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 12px; padding: 20px; }
.stat-label { color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.stat-value { font-size: 32px; font-weight: 700; color: #f8fafc; }
.cost { color: #22c55e; }
.table-wrap { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 12px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
th { background: #1e2030; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; padding: 12px 16px; text-align: left; }
td { padding: 10px 16px; border-top: 1px solid #2a2d3a; font-size: 13px; }
tr:hover { background: #1e2030; }
.provider { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.provider-cliproxy { background: rgba(212,165,116,0.13); color: #d4a574; }
.provider-openai { background: rgba(16,163,127,0.13); color: #10a37f; }
.provider-anthropic { background: rgba(212,165,116,0.13); color: #d4a574; }
.provider-google { background: rgba(66,133,244,0.13); color: #4285f4; }
.provider-mistral { background: rgba(255,112,0,0.13); color: #ff7000; }
.provider-groq { background: rgba(245,80,54,0.13); color: #f55036; }
.provider-ollama { background: rgba(255,255,255,0.08); color: #ffffff; }
.provider-lmstudio { background: rgba(139,92,246,0.13); color: #8b5cf6; }
.empty { text-align: center; padding: 60px; color: #64748b; }
.badge { background: rgba(34,197,94,0.13); color: #22c55e; padding: 4px 12px; border-radius: 20px; font-size: 12px; display: inline-block; margin-left: 12px; }
.model-section { margin-bottom: 32px; }
.model-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.model-card { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px; padding: 16px; }
.model-name { font-size: 14px; font-weight: 600; color: #f8fafc; margin-bottom: 4px; }
.model-stats { color: #94a3b8; font-size: 12px; }
.model-cost { color: #22c55e; font-size: 18px; font-weight: 700; margin-top: 8px; }
.model-bar { height: 4px; background: #2a2d3a; border-radius: 2px; margin-top: 8px; }
.model-bar-fill { height: 4px; background: #22c55e; border-radius: 2px; }
</style>
</head><body>
<div class="header">
    <h1>TokenPulse</h1>
    <span class="badge">● Live</span>
</div>
<p class="subtitle">Auto-refreshes every 10 seconds — $timestamp</p>

<div class="stats">
    <div class="stat-card">
        <div class="stat-label">Today's Spend</div>
        <div class="stat-value cost">$today_cost</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Requests Today</div>
        <div class="stat-value">$today_requests</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Tokens Today</div>
        <div class="stat-value">$today_tokens</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Total Recorded</div>
        <div class="stat-value">$total_requests</div>
    </div>
</div>

$model_section

<h2>Recent Requests</h2>
<div class="table-wrap">
$table
</div>
</body></html>""")

def get_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Today's stats
        c.execute("SELECT COALESCE(SUM(cost_usd),0), COUNT(*), COALESCE(SUM(input_tokens+output_tokens),0) FROM requests WHERE DATE(timestamp)=DATE('now')")
        today_cost, today_requests, today_tokens = c.fetchone()
        
        # Total
        c.execute("SELECT COUNT(*) FROM requests")
        total_requests = c.fetchone()[0]
        
        # Model breakdown
        c.execute("""SELECT model, provider, COUNT(*) as cnt, 
                     COALESCE(SUM(input_tokens),0) as inp, 
                     COALESCE(SUM(output_tokens),0) as outp,
                     COALESCE(SUM(cost_usd),0) as cost
                     FROM requests 
                     GROUP BY model, provider 
                     ORDER BY cost DESC LIMIT 10""")
        models = c.fetchall()
        
        max_cost = max((m[5] for m in models), default=0) if models else 0
        
        if models:
            model_section = '<div class="model-section"><h2>Model Breakdown</h2><div class="model-list">'
            for m in models:
                name = m[0] or "unknown"
                prov = m[1] or "unknown"
                cnt = m[2]
                inp = m[3]
                outp = m[4]
                cost = m[5]
                bar_width = int((cost / max_cost * 100)) if max_cost > 0 else 0
                model_section += f'''<div class="model-card">
                    <div class="model-name">{name}</div>
                    <div class="model-stats"><span class="provider provider-{prov}">{prov}</span> · {cnt} requests · {inp + outp:,} tokens</div>
                    <div class="model-cost">${cost:.4f}</div>
                    <div class="model-bar"><div class="model-bar-fill" style="width:{bar_width}%"></div></div>
                </div>'''
            model_section += '</div></div>'
        else:
            model_section = ''
        
        # Recent requests
        c.execute("""SELECT timestamp, provider, model, input_tokens, output_tokens, 
                     cost_usd, latency_ms, is_streaming 
                     FROM requests ORDER BY timestamp DESC LIMIT 30""")
        rows = c.fetchall()
        
        conn.close()
        
        if rows:
            table = "<table><tr><th>Time</th><th>Provider</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th><th>Latency</th></tr>"
            for r in rows:
                ts = r[0][:19].replace("T", " ") if r[0] else "—"
                prov = r[1] or "unknown"
                model = r[2] or "unknown"
                inp = f"{r[3]:,}" if r[3] else "0"
                out = f"{r[4]:,}" if r[4] else "0"
                cost = f"${r[5]:.4f}" if r[5] else "$0.00"
                lat = f"{r[6]}ms" if r[6] else "—"
                streaming = " 🔄" if r[7] else ""
                table += f'<tr><td>{ts}</td><td><span class="provider provider-{prov}">{prov}</span></td><td>{model}{streaming}</td><td>{inp}</td><td>{out}</td><td>{cost}</td><td>{lat}</td></tr>'
            table += "</table>"
        else:
            table = '<div class="empty">No requests tracked yet. Configure your tools to use the TokenPulse proxy.</div>'
        
        return TEMPLATE.substitute(
            today_cost=f"{today_cost:.4f}" if today_cost else "0.0000",
            today_requests=str(today_requests or 0),
            today_tokens=f"{today_tokens:,}" if today_tokens else "0",
            total_requests=str(total_requests or 0),
            model_section=model_section,
            table=table,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception as e:
        return f"<html><body style='background:#0f1117;color:white;padding:40px;font-family:sans-serif;'><h1>TokenPulse</h1><p style='color:#ef4444;margin-top:20px;'>Database error: {e}</p><p style='color:#64748b;margin-top:12px;'>DB path: {DB_PATH}</p></body></html>"

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(get_stats().encode("utf-8"))
    
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 4200), DashboardHandler)
    print("TokenPulse Web Dashboard running on http://0.0.0.0:4200")
    server.serve_forever()
