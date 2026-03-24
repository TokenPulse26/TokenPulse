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
    cursor: "pointer",
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
    padding: "64px 20px",
    textAlign: "center",
  },
  emptyIcon: {
    fontSize: "48px",
    marginBottom: "16px",
    opacity: 0.4,
  },
  emptyTitle: {
    fontSize: "16px",
    fontWeight: "600",
    marginBottom: "8px",
    color: "#64748b",
  },
  emptySubtitle: {
    fontSize: "13px",
    color: "#475569",
    marginBottom: "20px",
    lineHeight: 1.6,
  },
  emptyBtn: {
    backgroundColor: "#6366f1",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "8px 20px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
  },
  modelRow: {
    padding: "10px 0",
    borderBottom: "1px solid #111827",
  },
  modelRowTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "6px",
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
    flexShrink: 0,
    marginLeft: "8px",
  },
  progressBar: (pct, color) => ({
    height: "3px",
    borderRadius: "2px",
    backgroundColor: "#1a1f2e",
    overflow: "hidden",
  }),
  progressFill: (pct, color) => ({
    height: "100%",
    width: `${pct}%`,
    backgroundColor: color,
    borderRadius: "2px",
  }),
};

// Provider colors per spec
const PROVIDER_COLORS = {
  openai:    { bar: "#10a37f", badge: { bg: "#10a37f22", text: "#10a37f", border: "#10a37f44" } },
  anthropic: { bar: "#d4a574", badge: { bg: "#d4a57422", text: "#d4a574", border: "#d4a57444" } },
  google:    { bar: "#4285f4", badge: { bg: "#4285f422", text: "#60a5fa", border: "#4285f444" } },
  mistral:   { bar: "#ff7000", badge: { bg: "#ff700022", text: "#fb923c", border: "#ff700044" } },
  groq:      { bar: "#f55036", badge: { bg: "#f5503622", text: "#f87171", border: "#f5503644" } },
  ollama:    { bar: "#888888", badge: { bg: "#ffffff11", text: "#94a3b8", border: "#ffffff22" } },
  lmstudio:  { bar: "#8b5cf6", badge: { bg: "#8b5cf622", text: "#a78bfa", border: "#8b5cf644" } },
};

function getProviderColor(provider) {
  return PROVIDER_COLORS[provider] || PROVIDER_COLORS.ollama;
}

function providerBadgeStyle(provider) {
  const c = getProviderColor(provider).badge;
  return {
    backgroundColor: c.bg,
    color: c.text,
    border: `1px solid ${c.border}`,
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: "600",
  };
}

function providerDot(provider) {
  const color = getProviderColor(provider).bar;
  return {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    backgroundColor: color,
    display: "inline-block",
    marginRight: "6px",
    flexShrink: 0,
  };
}

function formatCost(cost) {
  if (cost === 0) return "$0.00";
  if (cost < 0.001) return `$${cost.toFixed(6)}`;
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

function formatTokenCount(n) {
  return n.toLocaleString();
}

function formatTokensShort(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatRelativeTime(isoString) {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return new Date(isoString).toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatLatency(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatDateShort(dateStr) {
  const [, month, day] = dateStr.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(month) - 1]} ${parseInt(day)}`;
}

const PROVIDERS_ORDER = ["openai", "anthropic", "google", "mistral", "groq", "ollama", "lmstudio"];

function buildStackedChartData(dailyStats, providerStats) {
  // Build a map of date -> { provider: cost }
  const providerByDate = {};
  for (const ps of providerStats) {
    if (!providerByDate[ps.date]) providerByDate[ps.date] = {};
    providerByDate[ps.date][ps.provider] = ps.cost;
  }

  return dailyStats.map((d) => {
    const entry = {
      date: formatDateShort(d.date),
      total_requests: d.total_requests,
      total_cost: d.total_cost,
      rawDate: d.date,
    };
    const providers = providerByDate[d.date] || {};
    for (const p of Object.keys(providers)) {
      entry[p] = providers[p];
    }
    return entry;
  });
}

function getActiveProviders(chartData) {
  const providerSet = new Set();
  for (const row of chartData) {
    for (const key of Object.keys(row)) {
      if (PROVIDERS_ORDER.includes(key)) providerSet.add(key);
    }
  }
  return PROVIDERS_ORDER.filter((p) => providerSet.has(p));
}

const StackedTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;
  const total = payload.reduce((sum, p) => sum + (p.value || 0), 0);
  const requests = payload[0]?.payload?.total_requests;
  return (
    <div style={{
      backgroundColor: "#131720",
      border: "1px solid #1e2636",
      borderRadius: "8px",
      padding: "10px 14px",
      minWidth: "140px",
    }}>
      <div style={{ fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ display: "flex", justifyContent: "space-between", gap: "16px", fontSize: "12px", marginBottom: "2px" }}>
          <span style={{ color: p.fill }}>{p.dataKey}</span>
          <span style={{ color: "#e2e8f0", fontWeight: "600" }}>{formatCost(p.value)}</span>
        </div>
      ))}
      <div style={{ borderTop: "1px solid #1e2636", marginTop: "6px", paddingTop: "6px", display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
        <span style={{ color: "#64748b" }}>Total</span>
        <span style={{ color: "#22c55e", fontWeight: "600" }}>{formatCost(total)}</span>
      </div>
      {requests != null && (
        <div style={{ fontSize: "11px", color: "#475569", marginTop: "2px" }}>{requests} requests</div>
      )}
    </div>
  );
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
  const [providerStats, setProviderStats] = useState([]);
  const [modelBreakdown, setModelBreakdown] = useState([]);
  const [summary, setSummary] = useState({ total_cost: 0, total_requests: 0, total_input_tokens: 0, total_output_tokens: 0 });
  const [proxyStatus, setProxyStatus] = useState({ running: false, port: 4100, paused: false });
  const [hoveredRow, setHoveredRow] = useState(null);

  useEffect(() => {
    invoke("get_proxy_status").then(setProxyStatus).catch(console.error);
  }, []);

  useEffect(() => {
    const fetchAll = () => {
      invoke("get_requests_range", { limit: 50, timeRange })
        .then(setRequests)
        .catch(console.error);
      invoke("get_daily_stats_range", { timeRange })
        .then(setDailyStats)
        .catch(console.error);
      invoke("get_daily_provider_stats", { timeRange })
        .then(setProviderStats)
        .catch(console.error);
      invoke("get_model_breakdown_range", { timeRange })
        .then(setModelBreakdown)
        .catch(console.error);
      invoke("get_dashboard_stats", { timeRange })
        .then(setSummary)
        .catch(console.error);
      invoke("get_proxy_status")
        .then(setProxyStatus)
        .catch(console.error);
    };

    fetchAll();
    const interval = setInterval(fetchAll, 2000);
    return () => clearInterval(interval);
  }, [timeRange]);

  const chartData = buildStackedChartData(dailyStats, providerStats);
  const activeProviders = getActiveProviders(chartData);
  const rangeLabel = TIME_RANGES.find((r) => r.value === timeRange)?.label ?? "";
  const maxModelCost = modelBreakdown.length > 0 ? modelBreakdown[0].total_cost : 1;

  const proxyBadgeLabel = proxyStatus.paused
    ? "● Proxy paused"
    : proxyStatus.running
    ? `● Proxy :${proxyStatus.port}`
    : "● Proxy offline";

  return (
    <div style={s.root}>
      <nav style={s.nav}>
        <span style={s.navWordmark} onClick={() => navigate("/")}>TokenPulse</span>
        <button style={s.navLink(true)}>Dashboard</button>
        <button style={s.navLink(false)} onClick={() => navigate("/setup")}>Setup</button>
        <button style={s.navLink(false)} onClick={() => navigate("/settings")}>Settings</button>
        <span style={s.proxyBadge(proxyStatus.running && !proxyStatus.paused)}>
          {proxyBadgeLabel}
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
            <div style={s.statValue}>{summary.total_requests.toLocaleString()}</div>
          </div>
          <div style={s.statCard}>
            <div style={s.statLabel}>Input Tokens</div>
            <div style={s.statValue}>{formatTokensShort(summary.total_input_tokens)}</div>
          </div>
          <div style={s.statCard}>
            <div style={s.statLabel}>Output Tokens</div>
            <div style={s.statValue}>{formatTokensShort(summary.total_output_tokens)}</div>
          </div>
        </div>

        <div style={s.twoCol}>
          {/* Daily Spend Chart */}
          <div style={s.panel}>
            <div style={s.panelHeader}>Daily Spend — {rangeLabel}</div>
            <div style={s.panelBody}>
              {chartData.length === 0 ? (
                <div style={{ padding: "24px 0", textAlign: "center" }}>
                  <div style={{ color: "#475569", fontSize: "13px" }}>No data yet</div>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                    <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v.toFixed(2)}`} width={52} />
                    <Tooltip content={<StackedTooltip />} cursor={{ fill: "#ffffff06" }} />
                    {activeProviders.length > 0 ? (
                      activeProviders.map((provider, idx) => (
                        <Bar
                          key={provider}
                          dataKey={provider}
                          stackId="a"
                          fill={getProviderColor(provider).bar}
                          radius={idx === activeProviders.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                        />
                      ))
                    ) : (
                      <Bar dataKey="total_cost" radius={[4, 4, 0, 0]} fill="#4f46e5" />
                    )}
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Model Breakdown */}
          <div style={s.panel}>
            <div style={s.panelHeader}>Model Breakdown — {rangeLabel}</div>
            <div style={s.panelBody}>
              {modelBreakdown.length === 0 ? (
                <div style={{ padding: "24px 0", textAlign: "center" }}>
                  <div style={{ color: "#475569", fontSize: "13px" }}>No data yet</div>
                </div>
              ) : (
                <div>
                  {modelBreakdown.slice(0, 8).map((m, i) => {
                    const costPct = maxModelCost > 0 ? (m.total_cost / maxModelCost) * 100 : 0;
                    const barColor = getProviderColor(m.provider).bar;
                    const isLast = i === Math.min(modelBreakdown.length, 8) - 1;
                    return (
                      <div key={i} style={{ ...s.modelRow, borderBottom: isLast ? "none" : "1px solid #111827" }}>
                        <div style={s.modelRowTop}>
                          <div>
                            <div style={s.modelName}>{m.model}</div>
                            <div style={s.modelMeta}>
                              <span style={providerBadgeStyle(m.provider)}>{m.provider}</span>
                              <span style={{ marginLeft: "6px" }}>
                                {m.total_requests.toLocaleString()} req · {formatTokensShort(m.total_tokens)} tok
                              </span>
                            </div>
                          </div>
                          <div style={s.modelCost}>{formatCost(m.total_cost)}</div>
                        </div>
                        <div style={s.progressBar(costPct, barColor)}>
                          <div style={s.progressFill(costPct, barColor)} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Recent Requests Table */}
        <div style={s.tableContainer}>
          <div style={s.tableHeader}>Recent Requests</div>
          {requests.length === 0 ? (
            <div style={s.emptyState}>
              <div style={s.emptyIcon}>📡</div>
              <div style={s.emptyTitle}>No requests tracked yet</div>
              <div style={s.emptySubtitle}>
                Configure your AI tools to use the TokenPulse proxy at{" "}
                <code style={{ color: "#7dd3fc", backgroundColor: "#0f1520", padding: "2px 6px", borderRadius: "4px" }}>
                  http://localhost:4100
                </code>
              </div>
              <button style={s.emptyBtn} onClick={() => navigate("/setup")}>
                Open Setup Guide →
              </button>
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
                  <tr
                    key={req.id || i}
                    style={{
                      backgroundColor: hoveredRow === i ? "#1a1f2e" : (i % 2 === 0 ? "transparent" : "#0d1117"),
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={() => setHoveredRow(i)}
                    onMouseLeave={() => setHoveredRow(null)}
                  >
                    <td style={{ ...s.td, color: "#64748b" }}>{formatRelativeTime(req.timestamp)}</td>
                    <td style={s.td}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>
                        <span style={providerDot(req.provider)} />
                        <span style={providerBadgeStyle(req.provider)}>{req.provider}</span>
                      </span>
                    </td>
                    <td style={{ ...s.td, fontFamily: "monospace", fontSize: "12px" }}>
                      {req.model}
                      {req.is_streaming && (
                        <span style={{ marginLeft: "6px", fontSize: "10px", color: "#6366f1", backgroundColor: "#6366f122", border: "1px solid #6366f144", padding: "1px 5px", borderRadius: "3px", fontFamily: "sans-serif" }}>
                          stream
                        </span>
                      )}
                    </td>
                    <td style={s.td}>{formatTokenCount(req.input_tokens)}</td>
                    <td style={s.td}>{formatTokenCount(req.output_tokens)}</td>
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
