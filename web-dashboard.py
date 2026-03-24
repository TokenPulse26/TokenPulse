#!/usr/bin/env python3
"""TokenPulse Web Dashboard — lightweight web view for remote access"""
import sqlite3
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/Library/Application Support/com.tokenpulse.desktop/tokenpulse.db")

HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenPulse Dashboard</title>
<meta http-equiv="refresh" content="10">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; padding: 24px; }
h1 { font-size: 28px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }
.subtitle { color: #64748b; font-size: 14px; margin-bottom: 24px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
.stat-card { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 12px; padding: 20px; }
.stat-label { color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.stat-value { font-size: 32px; font-weight: 700; color: #f8fafc; }
.stat-value.cost { color: #22c55e; }
table { width: 100%%; border-collapse: collapse; background: #1a1d27; border-radius: 12px; overflow: hidden; }
th { background: #1e2030; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; padding: 12px 16px; text-align: left; }
td { padding: 10px 16px; border-top: 1px solid #2a2d3a; font-size: 13px; }
tr:hover { background: #1e2030; }
.provider { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.provider-cliproxy { background: #d4a57422; color: #d4a574; }
.provider-openai { background: #10a37f22; color: #10a37f; }
.provider-anthropic { background: #d4a57422; color: #d4a574; }
.provider-google { background: #4285f422; color: #4285f4; }
.empty { text-align: center; padding: 60px; color: #64748b; }
.badge { background: #22c55e22; color: #22c55e; padding: 4px 12px; border-radius: 20px; font-size: 12px; display: inline-block; margin-left: 12px; }
</style>
</head><body>
<div style="display:flex; align-items:center; margin-bottom:24px;">
    <h1>TokenPulse</h1>
    <span class="badge">● Live</span>
</div>
<p class="subtitle">Auto-refreshes every 10 seconds — {timestamp}</p>
<div class="stats">
    <div class="stat-card"><div class="stat-label">Today's Spend</div><div class="stat-value cost">${today_cost:.4f}</div></div>
    <div class="stat-card"><div class="stat-label">Requests Today</div><div class="stat-value">{today_requests}</div></div>
    <div class="stat-card"><div class="stat-label">Tokens Today</div><div class="stat-value">{today_tokens:,}</div></div>
    <div class="stat-card"><div class="stat-label">Total Recorded</div><div class="stat-value">{total_requests}</div></div>
</div>
<h2 style="font-size:18px; margin-bottom:16px;">Recent Requests</h2>
{table}
</body></html>"""

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
        
        # Recent requests
        c.execute("SELECT timestamp, provider, model, input_tokens, output_tokens, cost_usd, latency_ms FROM requests ORDER BY timestamp DESC LIMIT 30")
        rows = c.fetchall()
        
        conn.close()
        
        if rows:
            table = "<table><tr><th>Time</th><th>Provider</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th><th>Latency</th></tr>"
            for r in rows:
                ts = r[0][:19] if r[0] else "—"
                prov = r[1] or "unknown"
                prov_class = f"provider-{prov}"
                model = r[2] or "unknown"
                inp = f"{r[3]:,}" if r[3] else "0"
                out = f"{r[4]:,}" if r[4] else "0"
                cost = f"${r[5]:.4f}" if r[5] else "$0.00"
                lat = f"{r[6]}ms" if r[6] else "—"
                table += f'<tr><td>{ts}</td><td><span class="provider {prov_class}">{prov}</span></td><td>{model}</td><td>{inp}</td><td>{out}</td><td>{cost}</td><td>{lat}</td></tr>'
            table += "</table>"
        else:
            table = '<div class="empty">No requests tracked yet. Configure your tools to use the TokenPulse proxy.</div>'
        
        return HTML.format(
            today_cost=today_cost or 0,
            today_requests=today_requests or 0,
            today_tokens=today_tokens or 0,
            total_requests=total_requests or 0,
            table=table,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception as e:
        return f"<html><body style='background:#0f1117;color:white;padding:40px;'><h1>TokenPulse</h1><p>Database error: {e}</p></body></html>"

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(get_stats().encode())
    
    def log_message(self, format, *args):
        pass  # Suppress log spam

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 4200), DashboardHandler)
    print("TokenPulse Web Dashboard running on http://0.0.0.0:4200")
    server.serve_forever()
