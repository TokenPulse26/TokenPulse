import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";

const styles = {
  app: {
    backgroundColor: "#0f1117",
    color: "#e2e8f0",
    minHeight: "100vh",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    padding: "24px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "24px",
  },
  title: {
    fontSize: "24px",
    fontWeight: "700",
    color: "#f8fafc",
    margin: 0,
  },
  badge: {
    backgroundColor: "#22c55e22",
    color: "#22c55e",
    padding: "4px 12px",
    borderRadius: "20px",
    fontSize: "12px",
    fontWeight: "600",
    border: "1px solid #22c55e44",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "16px",
    marginBottom: "24px",
  },
  statCard: {
    backgroundColor: "#1e2130",
    borderRadius: "12px",
    padding: "20px",
    border: "1px solid #2d3748",
  },
  statLabel: {
    fontSize: "12px",
    color: "#94a3b8",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: "8px",
  },
  statValue: {
    fontSize: "28px",
    fontWeight: "700",
    color: "#f8fafc",
  },
  statValueGreen: {
    fontSize: "28px",
    fontWeight: "700",
    color: "#22c55e",
  },
  tableContainer: {
    backgroundColor: "#1e2130",
    borderRadius: "12px",
    border: "1px solid #2d3748",
    overflow: "hidden",
  },
  tableHeader: {
    padding: "16px 20px",
    borderBottom: "1px solid #2d3748",
    fontSize: "14px",
    fontWeight: "600",
    color: "#94a3b8",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  th: {
    padding: "12px 16px",
    textAlign: "left",
    fontSize: "11px",
    fontWeight: "600",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    borderBottom: "1px solid #2d3748",
    backgroundColor: "#161821",
  },
  td: {
    padding: "12px 16px",
    fontSize: "13px",
    borderBottom: "1px solid #1a1f2e",
    color: "#cbd5e1",
  },
  providerBadge: (provider) => {
    const colors = {
      openai: { bg: "#10a37f22", text: "#10a37f", border: "#10a37f44" },
      anthropic: { bg: "#d97b4622", text: "#f59e0b", border: "#d97b4644" },
      google: { bg: "#4285f422", text: "#60a5fa", border: "#4285f444" },
      ollama: { bg: "#8b5cf622", text: "#a78bfa", border: "#8b5cf644" },
      lmstudio: { bg: "#ec489922", text: "#f472b6", border: "#ec489944" },
    };
    const c = colors[provider] || { bg: "#ffffff11", text: "#94a3b8", border: "#ffffff22" };
    return {
      backgroundColor: c.bg,
      color: c.text,
      border: `1px solid ${c.border}`,
      padding: "2px 8px",
      borderRadius: "4px",
      fontSize: "11px",
      fontWeight: "600",
    };
  },
  emptyState: {
    padding: "48px 20px",
    textAlign: "center",
    color: "#64748b",
  },
  emptyTitle: {
    fontSize: "16px",
    marginBottom: "8px",
    color: "#94a3b8",
  },
  emptySubtitle: {
    fontSize: "13px",
  },
};

function formatCost(cost) {
  if (cost === 0) return "$0.00";
  if (cost < 0.001) return `$${cost.toFixed(6)}`;
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(4)}`;
}

function formatTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatLatency(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTokens(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export default function App() {
  const [requests, setRequests] = useState([]);
  const [proxyStatus, setProxyStatus] = useState({ running: false, port: 4100 });

  useEffect(() => {
    invoke("get_proxy_status")
      .then(setProxyStatus)
      .catch(console.error);
  }, []);

  useEffect(() => {
    const fetchRequests = () => {
      invoke("get_recent_requests", { limit: 50 })
        .then(setRequests)
        .catch(console.error);
    };

    fetchRequests();
    const interval = setInterval(fetchRequests, 2000);
    return () => clearInterval(interval);
  }, []);

  const today = new Date().toISOString().slice(0, 10);
  const todayRequests = requests.filter((r) => r.timestamp.startsWith(today));
  const todaySpend = todayRequests.reduce((sum, r) => sum + r.cost_usd, 0);
  const todayTokens = todayRequests.reduce((sum, r) => sum + r.input_tokens + r.output_tokens, 0);

  return (
    <div style={styles.app}>
      <div style={styles.header}>
        <h1 style={styles.title}>TokenPulse</h1>
        <span style={styles.badge}>
          {proxyStatus.running ? `Proxy :${proxyStatus.port}` : "Proxy offline"}
        </span>
      </div>

      <div style={styles.statsGrid}>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>Today's Spend</div>
          <div style={styles.statValueGreen}>${todaySpend.toFixed(4)}</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>Requests Today</div>
          <div style={styles.statValue}>{todayRequests.length}</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>Tokens Today</div>
          <div style={styles.statValue}>{formatTokens(todayTokens)}</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>Total Recorded</div>
          <div style={styles.statValue}>{requests.length}</div>
        </div>
      </div>

      <div style={styles.tableContainer}>
        <div style={styles.tableHeader}>Recent Requests</div>
        {requests.length === 0 ? (
          <div style={styles.emptyState}>
            <div style={styles.emptyTitle}>No requests yet</div>
            <div style={styles.emptySubtitle}>
              Point your AI client to <strong style={{ color: "#94a3b8" }}>http://localhost:4100</strong> to start tracking
            </div>
          </div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Time</th>
                <th style={styles.th}>Provider</th>
                <th style={styles.th}>Model</th>
                <th style={styles.th}>Input</th>
                <th style={styles.th}>Output</th>
                <th style={styles.th}>Cost</th>
                <th style={styles.th}>Latency</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((req, i) => (
                <tr key={req.id || i} style={{ backgroundColor: i % 2 === 0 ? "transparent" : "#161821" }}>
                  <td style={styles.td}>{formatTime(req.timestamp)}</td>
                  <td style={styles.td}>
                    <span style={styles.providerBadge(req.provider)}>{req.provider}</span>
                  </td>
                  <td style={{ ...styles.td, fontFamily: "monospace", fontSize: "12px" }}>
                    {req.model}
                  </td>
                  <td style={styles.td}>{formatTokens(req.input_tokens)}</td>
                  <td style={styles.td}>{formatTokens(req.output_tokens)}</td>
                  <td style={{ ...styles.td, color: "#22c55e" }}>{formatCost(req.cost_usd)}</td>
                  <td style={{ ...styles.td, color: "#94a3b8" }}>{formatLatency(req.latency_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
