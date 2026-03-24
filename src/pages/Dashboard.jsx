import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const s = {
  root: {
    backgroundColor: "#0a0d14",
    color: "#e2e8f0",
    minHeight: "100vh",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  nav: {
    display: "flex",
    alignItems: "center",
    padding: "0 32px",
    height: "56px",
    borderBottom: "1px solid #1a1f2e",
    backgroundColor: "#0d1117",
    gap: "24px",
  },
  navWordmark: {
    fontSize: "18px",
    fontWeight: "800",
    letterSpacing: "-0.02em",
    background: "linear-gradient(135deg, #38bdf8, #818cf8)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
    backgroundClip: "text",
    marginRight: "12px",
  },
  navLink: (active) => ({
    fontSize: "14px",
    fontWeight: active ? "600" : "400",
    color: active ? "#f1f5f9" : "#64748b",
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "4px 0",
    borderBottom: active ? "2px solid #6366f1" : "2px solid transparent",
  }),
  proxyBadge: (running) => ({
    marginLeft: "auto",
    backgroundColor: running ? "#14532d22" : "#450a0a22",
    color: running ? "#4ade80" : "#f87171",
    padding: "4px 12px",
    borderRadius: "20px",
    fontSize: "12px",
    fontWeight: "600",
    border: `1px solid ${running ? "#16a34a44" : "#991b1b44"}`,
  }),
  body: {
    padding: "28px 32px",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "24px",
  },
  rangeBtn: (active) => ({
    backgroundColor: active ? "#6366f1" : "#131720",
    color: active ? "#fff" : "#64748b",
    border: `1px solid ${active ? "#4f46e5" : "#1e2636"}`,
    borderRadius: "8px",
    padding: "6px 16px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "all 0.12s",
  }),
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
    gap: "16px",
    marginBottom: "24px",
  },
  statCard: {
    backgroundColor: "#131720",
    borderRadius: "12px",
    padding: "20px",
    border: "1px solid #1e2636",
  },
  statLabel: {
    fontSize: "11px",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    marginBottom: "8px",
    fontWeight: "600",
  },
  statValue: {
    fontSize: "26px",
    fontWeight: "700",
    color: "#f8fafc",
  },
  statValueGreen: {
    fontSize: "26px",
    fontWeight: "700",
    color: "#22c55e",
  },
  twoCol: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "16px",
    marginBottom: "20px",
  },
  panel: {
    backgroundColor: "#131720",
    borderRadius: "12px",
    border: "1px solid #1e2636",
    overflow: "hidden",
  },
  panelHeader: {
    padding: "14px 20px",
    borderBottom: "1px solid #1a1f2e",
    fontSize: "13px",
    fontWeight: "600",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  panelBody: {
    padding: "16px 20px",
  },
  tableContainer: {
    backgroundColor: "#131720",
    borderRadius: "12px",
    border: "1px solid #1e2636",
    overflow: "hidden",
  },
  tableHeader: {
    padding: "14px 20px",
    borderBottom: "1px solid #1a1f2e",
    fontSize: "13px",
    fontWeight: "600",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  th: {
    padding: "10px 16px",
    textAlign: "left",
    fontSize: "11px",
    fontWeight: "600",
    color: "#475569",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    borderBottom: "1px solid #1a1f2e",
    backgroundColor: "#0d1117",
  },
  td: {
    padding: "11px 16px",
    fontSize: "13px",
    borderBottom: "1px solid #111827",
    color: "#cbd5e1",
  },
  emptyState: {
    padding: "48px 20px",
    textAlign: "center",
    color: "#475569",
  },
  emptyTitle: {
    fontSize: "15px",
    marginBottom: "8px",
    color: "#64748b",
  },
  emptySubtitle: {
    fontSize: "13px",
  },
  modelRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "10px 0",
    borderBottom: "1px solid #111827",
  },
  modelName: {
    fontFamily: "monospace",
    fontSize: "12px",
    color: "#cbd5e1",
  },
  modelMeta: {
    fontSize: "12px",
    color: "#475569",
    marginTop: "2px",
  },
  modelCost: {
    fontSize: "13px",
    fontWeight: "600",
    color: "#22c55e",
  },
};

const PROVIDER_COLORS = {
  openai: { bg: "#10a37f22", text: "#10a37f", border: "#10a37f44" },
  anthropic: { bg: "#d97b4622", text: "#f59e0b", border: "#d97b4644" },
  google: { bg: "#4285f422", text: "#60a5fa", border: "#4285f444" },
  ollama: { bg: "#8b5cf622", text: "#a78bfa", border: "#8b5cf644" },
  lmstudio: { bg: "#ec489922", text: "#f472b6", border: "#ec489944" },
  mistral: { bg: "#ff7a0022", text: "#fb923c", border: "#ff7a0044" },
  groq: { bg: "#f59e0b22", text: "#fbbf24", border: "#f59e0b44" },
};

function providerBadgeStyle(provider) {
  const c = PROVIDER_COLORS[provider] || { bg: "#ffffff11", text: "#94a3b8", border: "#ffffff22" };
  return { backgroundColor: c.bg, color: c.text, border: `1px solid ${c.border}`, padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: "600" };
}

function formatCost(cost) {
  if (cost === 0) return "$0.00";
  if (cost < 0.001) return `$${cost.toFixed(6)}`;
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

function formatDateShort(dateStr) {
  const [, month, day] = dateStr.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(month) - 1]} ${parseInt(day)}`;
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div style={{ backgroundColor: "#131720", border: "1px solid #1e2636", borderRadius: "8px", padding: "10px 14px" }}>
        <div style={{ fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>{label}</div>
        <div style={{ fontSize: "14px", fontWeight: "600", color: "#22c55e" }}>${payload[0].value.toFixed(4)}</div>
        {payload[0].payload.total_requests != null && (
          <div style={{ fontSize: "11px", color: "#64748b" }}>{payload[0].payload.total_requests} requests</div>
        )}
      </div>
    );
  }
  return null;
};

const TIME_RANGES = [
  { label: "Today", value: "today" },
  { label: "7 Days", value: "7d" },
  { label: "30 Days", value: "30d" },
  { label: "All Time", value: "all" },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const [timeRange, setTimeRange] = useState("7d");
  const [requests, setRequests] = useState([]);
  const [dailyStats, setDailyStats] = useState([]);
  const [modelBreakdown, setModelBreakdown] = useState([]);
  const [summary, setSummary] = useState({ total_cost: 0, total_requests: 0, total_input_tokens: 0, total_output_tokens: 0 });
  const [proxyStatus, setProxyStatus] = useState({ running: false, port: 4100 });

  useEffect(() => {
    invoke("get_proxy_status").then(setProxyStatus).catch(console.error);
  }, []);

  useEffect(() => {
    const fetchAll = () => {
      invoke("get_requests_range", { limit: 50, timeRange: timeRange })
        .then(setRequests)
        .catch(console.error);

      invoke("get_daily_stats_range", { timeRange: timeRange })
        .then(setDailyStats)
        .catch(console.error);

      invoke("get_model_breakdown_range", { timeRange: timeRange })
        .then(setModelBreakdown)
        .catch(console.error);

      invoke("get_dashboard_stats", { timeRange: timeRange })
        .then(setSummary)
        .catch(console.error);
    };

    fetchAll();
    const interval = setInterval(fetchAll, 2000);
    return () => clearInterval(interval);
  }, [timeRange]);

  const today = new Date().toISOString().slice(0, 10);

  const chartData = dailyStats.map((d) => ({
    date: formatDateShort(d.date),
    total_cost: d.total_cost,
    total_requests: d.total_requests,
    isToday: d.date === today,
  }));

  const rangeLabel = TIME_RANGES.find((r) => r.value === timeRange)?.label ?? "";

  return (
    <div style={s.root}>
      <nav style={s.nav}>
        <span style={s.navWordmark}>TokenPulse</span>
        <button style={s.navLink(true)}>Dashboard</button>
        <button style={s.navLink(false)} onClick={() => navigate("/setup")}>Setup</button>
        <button style={s.navLink(false)} onClick={() => navigate("/settings")}>Settings</button>
        <span style={s.proxyBadge(proxyStatus.running)}>
          {proxyStatus.running ? `● Proxy :${proxyStatus.port}` : "● Proxy offline"}
        </span>
      </nav>

      <div style={s.body}>
        <div style={s.toolbar}>
          {TIME_RANGES.map((r) => (
            <button
              key={r.value}
              style={s.rangeBtn(timeRange === r.value)}
              onClick={() => setTimeRange(r.value)}
            >
              {r.label}
            </button>
          ))}
        </div>

        <div style={s.statsGrid}>
          <div style={s.statCard}>
            <div style={s.statLabel}>Total Spend</div>
            <div style={s.statValueGreen}>{formatCost(summary.total_cost)}</div>
          </div>
          <div style={s.statCard}>
            <div style={s.statLabel}>Requests</div>
            <div style={s.statValue}>{summary.total_requests}</div>
          </div>
          <div style={s.statCard}>
            <div style={s.statLabel}>Input Tokens</div>
            <div style={s.statValue}>{formatTokens(summary.total_input_tokens)}</div>
          </div>
          <div style={s.statCard}>
            <div style={s.statLabel}>Output Tokens</div>
            <div style={s.statValue}>{formatTokens(summary.total_output_tokens)}</div>
          </div>
        </div>

        <div style={s.twoCol}>
          <div style={s.panel}>
            <div style={s.panelHeader}>Daily Spend — {rangeLabel}</div>
            <div style={s.panelBody}>
              {chartData.length === 0 ? (
                <div style={{ ...s.emptyState, padding: "24px 0" }}>
                  <div style={{ color: "#475569", fontSize: "13px" }}>No data yet</div>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                    <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v.toFixed(2)}`} width={50} />
                    <Tooltip content={<CustomTooltip />} cursor={{ fill: "#ffffff06" }} />
                    <Bar dataKey="total_cost" radius={[4, 4, 0, 0]}>
                      {chartData.map((entry, i) => (
                        <Cell key={i} fill={entry.isToday ? "#22c55e" : "#4f46e5"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div style={s.panel}>
            <div style={s.panelHeader}>Model Breakdown — {rangeLabel}</div>
            <div style={s.panelBody}>
              {modelBreakdown.length === 0 ? (
                <div style={{ ...s.emptyState, padding: "24px 0" }}>
                  <div style={{ color: "#475569", fontSize: "13px" }}>No data yet</div>
                </div>
              ) : (
                <div>
                  {modelBreakdown.slice(0, 8).map((m, i) => (
                    <div key={i} style={{ ...s.modelRow, borderBottom: i < Math.min(modelBreakdown.length, 8) - 1 ? "1px solid #111827" : "none" }}>
                      <div>
                        <div style={s.modelName}>{m.model}</div>
                        <div style={s.modelMeta}>
                          <span style={providerBadgeStyle(m.provider)}>{m.provider}</span>
                          <span style={{ marginLeft: "6px" }}>{m.total_requests} req · {formatTokens(m.total_tokens)} tok</span>
                        </div>
                      </div>
                      <div style={s.modelCost}>{formatCost(m.total_cost)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={s.tableContainer}>
          <div style={s.tableHeader}>Recent Requests</div>
          {requests.length === 0 ? (
            <div style={s.emptyState}>
              <div style={s.emptyTitle}>No requests tracked yet</div>
              <div style={s.emptySubtitle}>
                Set your AI client's base URL to{" "}
                <strong style={{ color: "#94a3b8" }}>http://localhost:4100</strong> to start tracking
              </div>
            </div>
          ) : (
            <table style={s.table}>
              <thead>
                <tr>
                  <th style={s.th}>Time</th>
                  <th style={s.th}>Provider</th>
                  <th style={s.th}>Model</th>
                  <th style={s.th}>Input</th>
                  <th style={s.th}>Output</th>
                  <th style={s.th}>Cost</th>
                  <th style={s.th}>Latency</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((req, i) => (
                  <tr key={req.id || i} style={{ backgroundColor: i % 2 === 0 ? "transparent" : "#0d1117" }}>
                    <td style={s.td}>{formatTime(req.timestamp)}</td>
                    <td style={s.td}><span style={providerBadgeStyle(req.provider)}>{req.provider}</span></td>
                    <td style={{ ...s.td, fontFamily: "monospace", fontSize: "12px" }}>{req.model}</td>
                    <td style={s.td}>{formatTokens(req.input_tokens)}</td>
                    <td style={s.td}>{formatTokens(req.output_tokens)}</td>
                    <td style={{ ...s.td, color: "#22c55e" }}>{formatCost(req.cost_usd)}</td>
                    <td style={{ ...s.td, color: "#64748b" }}>{formatLatency(req.latency_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
