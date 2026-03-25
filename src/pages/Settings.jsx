import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";

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
  content: {
    padding: "40px 48px",
    maxWidth: "680px",
  },
  pageTitle: {
    fontSize: "24px",
    fontWeight: "800",
    color: "#f8fafc",
    margin: "0 0 32px 0",
    letterSpacing: "-0.02em",
  },
  section: {
    backgroundColor: "#131720",
    border: "1px solid #1e2636",
    borderRadius: "12px",
    padding: "24px",
    marginBottom: "20px",
  },
  sectionTitle: {
    fontSize: "13px",
    fontWeight: "700",
    color: "#94a3b8",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    marginBottom: "20px",
  },
  row: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "16px",
  },
  label: {
    fontSize: "14px",
    color: "#cbd5e1",
    fontWeight: "500",
  },
  subLabel: {
    fontSize: "12px",
    color: "#64748b",
    marginTop: "2px",
  },
  input: {
    backgroundColor: "#0a0d14",
    border: "1px solid #2d3748",
    borderRadius: "8px",
    padding: "8px 12px",
    color: "#e2e8f0",
    fontSize: "14px",
    width: "100px",
    outline: "none",
  },
  select: {
    backgroundColor: "#0a0d14",
    border: "1px solid #2d3748",
    borderRadius: "8px",
    padding: "8px 12px",
    color: "#e2e8f0",
    fontSize: "14px",
    outline: "none",
    cursor: "pointer",
  },
  toggle: (on) => ({
    width: "44px",
    height: "24px",
    borderRadius: "12px",
    backgroundColor: on ? "#6366f1" : "#1e293b",
    border: `1px solid ${on ? "#4f46e5" : "#334155"}`,
    cursor: "pointer",
    position: "relative",
    transition: "background 0.2s",
    flexShrink: 0,
  }),
  toggleKnob: (on) => ({
    position: "absolute",
    top: "3px",
    left: on ? "22px" : "3px",
    width: "16px",
    height: "16px",
    borderRadius: "50%",
    backgroundColor: "#fff",
    transition: "left 0.2s",
  }),
  btn: {
    backgroundColor: "#1e293b",
    color: "#94a3b8",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "8px 16px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "all 0.15s",
  },
  meta: {
    fontSize: "12px",
    color: "#475569",
    marginTop: "4px",
  },
  successMsg: {
    fontSize: "13px",
    color: "#4ade80",
    fontWeight: "600",
  },
  errorMsg: {
    fontSize: "13px",
    color: "#f87171",
  },
};

export default function Settings() {
  const navigate = useNavigate();
  const [launchAtLogin, setLaunchAtLogin] = useState(false);
  const [dataRetention, setDataRetention] = useState("90d");
  const [pricingLastUpdated, setPricingLastUpdated] = useState(null);
  const [pricingStatus, setPricingStatus] = useState(null);
  const [exportStatus, setExportStatus] = useState(null);
  const [autolaunchStatus, setAutolaunchStatus] = useState(null);
  const [proxyStatus, setProxyStatus] = useState({ running: false, port: 4100, paused: false });

  useEffect(() => {
    invoke("get_setting", { key: "launch_at_login" }).then((v) => v && setLaunchAtLogin(v === "true")).catch(() => {});
    invoke("get_setting", { key: "data_retention" }).then((v) => v && setDataRetention(v)).catch(() => {});
    invoke("get_setting", { key: "pricing_last_updated" }).then((v) => setPricingLastUpdated(v)).catch(() => {});
    invoke("get_proxy_status").then(setProxyStatus).catch(() => {});
  }, []);

  function saveSetting(key, value) {
    invoke("set_setting", { key, value }).catch(() => {});
  }

  async function handleLaunchAtLoginToggle() {
    const next = !launchAtLogin;
    setLaunchAtLogin(next);
    saveSetting("launch_at_login", next ? "true" : "false");
    setAutolaunchStatus("saving");
    try {
      await invoke("set_autostart", { enabled: next });
      setAutolaunchStatus("ok");
      setTimeout(() => setAutolaunchStatus(null), 2000);
    } catch (e) {
      setAutolaunchStatus("error");
      setTimeout(() => setAutolaunchStatus(null), 3000);
    }
  }

  async function handleUpdatePricing() {
    setPricingStatus("updating");
    try {
      await invoke("update_pricing_now");
      setPricingStatus("ok");
      setTimeout(() => {
        invoke("get_setting", { key: "pricing_last_updated" }).then((v) => setPricingLastUpdated(v)).catch(() => {});
        setPricingStatus(null);
      }, 3000);
    } catch (e) {
      setPricingStatus("error");
    }
  }

  async function handleExportCsv() {
    setExportStatus("exporting");
    try {
      const path = await invoke("export_csv");
      if (path === "cancelled") {
        setExportStatus(null);
      } else {
        setExportStatus("ok");
        setTimeout(() => setExportStatus(null), 3000);
      }
    } catch (e) {
      if (String(e).includes("cancelled")) {
        setExportStatus(null);
      } else {
        setExportStatus("error");
      }
    }
  }

  function formatDate(isoStr) {
    if (!isoStr) return "Never";
    try {
      return new Date(isoStr).toLocaleString();
    } catch {
      return isoStr;
    }
  }

  const proxyBadgeLabel = proxyStatus.paused
    ? "● Proxy paused"
    : proxyStatus.running
    ? `● Proxy :${proxyStatus.port}`
    : "● Proxy offline";

  return (
    <div style={s.root}>
      <nav style={s.nav}>
        <span style={s.navWordmark} onClick={() => navigate("/")}>TokenPulse</span>
        <button style={s.navLink(false)} onClick={() => navigate("/")}>Dashboard</button>
        <button style={s.navLink(false)} onClick={() => navigate("/setup")}>Setup</button>
        <button style={s.navLink(true)}>Settings</button>
        <span style={s.proxyBadge(proxyStatus.running && !proxyStatus.paused)}>
          {proxyBadgeLabel}
        </span>
      </nav>

      <div style={s.content}>
        <h1 style={s.pageTitle}>Settings</h1>

        <div style={s.section}>
          <div style={s.sectionTitle}>Proxy</div>
          {/* Proxy port is always 4100 — configuration not supported yet */}
          <div style={s.row}>
            <div>
              <div style={s.label}>Launch at Login</div>
              <div style={s.subLabel}>Start TokenPulse automatically when you log in</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              {autolaunchStatus === "ok" && <span style={s.successMsg}>✓</span>}
              {autolaunchStatus === "error" && <span style={s.errorMsg}>Failed</span>}
              <div
                style={s.toggle(launchAtLogin)}
                onClick={handleLaunchAtLoginToggle}
              >
                <div style={s.toggleKnob(launchAtLogin)} />
              </div>
            </div>
          </div>
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>Data</div>
          <div style={s.row}>
            <div>
              <div style={s.label}>Keep data for</div>
            </div>
            <select
              style={s.select}
              value={dataRetention}
              onChange={(e) => {
                setDataRetention(e.target.value);
                saveSetting("data_retention", e.target.value);
              }}
            >
              <option value="30d">30 days</option>
              <option value="90d">90 days</option>
              <option value="1y">1 year</option>
              <option value="forever">Forever</option>
            </select>
          </div>
          <div style={s.row}>
            <div>
              <div style={s.label}>Export to CSV</div>
              <div style={s.subLabel}>All request history</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              {exportStatus === "ok" && <span style={s.successMsg}>✅ Saved!</span>}
              {exportStatus === "error" && <span style={s.errorMsg}>Export failed</span>}
              <button
                style={s.btn}
                onClick={handleExportCsv}
                disabled={exportStatus === "exporting"}
              >
                {exportStatus === "exporting" ? "Exporting..." : "⬇ Export CSV"}
              </button>
            </div>
          </div>
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>Pricing Database</div>
          <div style={s.row}>
            <div>
              <div style={s.label}>Update pricing data</div>
              <div style={s.meta}>Last updated: {formatDate(pricingLastUpdated)}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              {pricingStatus === "ok" && <span style={s.successMsg}>✅ Updated!</span>}
              {pricingStatus === "error" && <span style={s.errorMsg}>Update failed</span>}
              <button
                style={s.btn}
                onClick={handleUpdatePricing}
                disabled={pricingStatus === "updating"}
              >
                {pricingStatus === "updating" ? "Updating..." : "↻ Update Now"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
