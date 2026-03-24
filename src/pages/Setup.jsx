import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import { writeText } from "@tauri-apps/plugin-clipboard-manager";

const PROXY_URL = "http://localhost:4100";

const TOOLS = [
  {
    id: "cursor",
    name: "Cursor",
    icon: "✦",
    summary: "Settings → Models → OpenAI Base URL",
    instructions: "Open Cursor Settings → Models → find the OpenAI Base URL field and paste the proxy URL. Cursor will route all OpenAI-compatible requests through TokenPulse.",
    copyLabel: "Copy URL",
    copyValue: PROXY_URL,
  },
  {
    id: "python-openai",
    name: "Python (openai SDK)",
    icon: "🐍",
    summary: "Set OPENAI_BASE_URL in your .env",
    instructions: 'Add to your .env or script:\nOPENAI_BASE_URL=http://localhost:4100\n\nOr in Python:\nimport openai\nclient = openai.OpenAI(base_url="http://localhost:4100/v1")',
    copyLabel: "Copy .env line",
    copyValue: "OPENAI_BASE_URL=http://localhost:4100",
  },
  {
    id: "python-anthropic",
    name: "Python (anthropic SDK)",
    icon: "🤖",
    summary: "Set ANTHROPIC_BASE_URL in your .env",
    instructions: 'Add to your .env or script:\nANTHROPIC_BASE_URL=http://localhost:4100/anthropic\n\nOr in Python:\nimport anthropic\nclient = anthropic.Anthropic(base_url="http://localhost:4100/anthropic")',
    copyLabel: "Copy .env line",
    copyValue: "ANTHROPIC_BASE_URL=http://localhost:4100/anthropic",
  },
  {
    id: "shell",
    name: "Shell / Terminal",
    icon: "⚡",
    summary: "Add export lines to .zshrc or .bashrc",
    instructions: "Add to your ~/.zshrc or ~/.bashrc:\nexport OPENAI_BASE_URL=http://localhost:4100\nexport ANTHROPIC_BASE_URL=http://localhost:4100/anthropic\n\nThen run: source ~/.zshrc",
    copyLabel: "Copy export",
    copyValue: "export OPENAI_BASE_URL=http://localhost:4100\nexport ANTHROPIC_BASE_URL=http://localhost:4100/anthropic",
  },
  {
    id: "ollama",
    name: "Ollama",
    icon: "🦙",
    summary: "Point Ollama-connected tools to TokenPulse",
    instructions: "Point any Ollama-connected tool to:\nhttp://localhost:4100/ollama\n\nThis is compatible with the Ollama REST API. Tools like Open WebUI can use this URL directly.",
    copyLabel: "Copy URL",
    copyValue: `${PROXY_URL}/ollama`,
  },
  {
    id: "lmstudio",
    name: "LM Studio",
    icon: "🏠",
    summary: "Change the base URL in your LM Studio client",
    instructions: "Point any LM Studio compatible tool to:\nhttp://localhost:4100/lmstudio\n\nUse this as the API base URL in place of http://localhost:1234.",
    copyLabel: "Copy URL",
    copyValue: `${PROXY_URL}/lmstudio`,
  },
  {
    id: "openwebui",
    name: "Open WebUI",
    icon: "🌐",
    summary: "Admin → Connections → OpenAI API Base URL",
    instructions: "In Open WebUI admin panel:\nAdmin → Settings → Connections → OpenAI API\nSet Base URL to: http://localhost:4100\n\nTokenPulse will track all requests routed through Open WebUI.",
    copyLabel: "Copy URL",
    copyValue: PROXY_URL,
  },
  {
    id: "generic",
    name: "Other / Generic",
    icon: "🔧",
    summary: "Any OpenAI-compatible tool",
    instructions: "Any tool that supports a custom OpenAI base URL can point to:\nhttp://localhost:4100\n\nThis includes LangChain, LlamaIndex, Continue.dev, and any other OpenAI-compatible client.",
    copyLabel: "Copy URL",
    copyValue: PROXY_URL,
  },
];

const s = {
  root: {
    backgroundColor: "#0a0d14",
    color: "#e2e8f0",
    minHeight: "100vh",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    padding: "40px 48px",
    maxWidth: "900px",
    margin: "0 auto",
  },
  header: {
    marginBottom: "8px",
  },
  title: {
    fontSize: "28px",
    fontWeight: "800",
    color: "#f8fafc",
    margin: "0 0 10px 0",
    letterSpacing: "-0.02em",
  },
  subtitle: {
    fontSize: "15px",
    color: "#94a3b8",
    lineHeight: 1.6,
    margin: "0 0 24px 0",
    maxWidth: "620px",
  },
  statusBadge: (running) => ({
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    backgroundColor: running ? "#14532d" : "#450a0a",
    border: `1px solid ${running ? "#16a34a" : "#991b1b"}`,
    borderRadius: "20px",
    padding: "6px 14px",
    fontSize: "13px",
    fontWeight: "600",
    color: running ? "#4ade80" : "#f87171",
    marginBottom: "36px",
  }),
  dot: (running) => ({
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    backgroundColor: running ? "#4ade80" : "#f87171",
    flexShrink: 0,
  }),
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
    gap: "12px",
    marginBottom: "40px",
  },
  toolCard: (active) => ({
    backgroundColor: active ? "#1a1f35" : "#13172200",
    border: `1px solid ${active ? "#4f46e5" : "#1e2636"}`,
    borderRadius: "12px",
    padding: "16px",
    cursor: "pointer",
    transition: "all 0.15s",
  }),
  toolHeader: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    marginBottom: "4px",
  },
  toolIcon: {
    fontSize: "20px",
  },
  toolName: {
    fontSize: "14px",
    fontWeight: "700",
    color: "#f1f5f9",
  },
  toolSummary: {
    fontSize: "12px",
    color: "#64748b",
    lineHeight: 1.4,
  },
  expandedPanel: {
    backgroundColor: "#0f1520",
    border: "1px solid #1e2d40",
    borderRadius: "12px",
    padding: "24px",
    marginTop: "-4px",
    marginBottom: "32px",
  },
  expandedTitle: {
    fontSize: "15px",
    fontWeight: "700",
    color: "#f1f5f9",
    marginBottom: "12px",
  },
  codeBlock: {
    backgroundColor: "#070a12",
    border: "1px solid #1e2636",
    borderRadius: "8px",
    padding: "16px",
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: "13px",
    color: "#7dd3fc",
    whiteSpace: "pre-wrap",
    marginBottom: "14px",
    lineHeight: 1.6,
  },
  copyBtn: {
    backgroundColor: "#1e293b",
    color: "#94a3b8",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "8px 18px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "all 0.15s",
  },
  copyBtnSuccess: {
    backgroundColor: "#14532d",
    color: "#4ade80",
    border: "1px solid #16a34a",
    borderRadius: "8px",
    padding: "8px 18px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
  },
  bottomBar: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
    flexWrap: "wrap",
  },
  testBtn: {
    backgroundColor: "#1e293b",
    color: "#94a3b8",
    border: "1px solid #334155",
    borderRadius: "10px",
    padding: "12px 24px",
    fontSize: "14px",
    fontWeight: "600",
    cursor: "pointer",
  },
  doneBtn: {
    backgroundColor: "#6366f1",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    padding: "12px 28px",
    fontSize: "14px",
    fontWeight: "700",
    cursor: "pointer",
  },
  testResult: (ok) => ({
    fontSize: "13px",
    fontWeight: "600",
    color: ok ? "#4ade80" : "#f87171",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  }),
};

export default function Setup() {
  const navigate = useNavigate();
  const [activeTool, setActiveTool] = useState(null);
  const [proxyRunning, setProxyRunning] = useState(false);
  const [copied, setCopied] = useState(false);
  const [testStatus, setTestStatus] = useState(null); // null | "testing" | "ok" | "fail"
  const [testError, setTestError] = useState("");

  useEffect(() => {
    invoke("get_proxy_status")
      .then((s) => setProxyRunning(s.running))
      .catch(() => setProxyRunning(false));
  }, []);

  const selectedTool = TOOLS.find((t) => t.id === activeTool);

  async function handleCopy(value) {
    try {
      await writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      // fallback
      navigator.clipboard?.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  async function handleTest() {
    setTestStatus("testing");
    setTestError("");
    try {
      await invoke("test_proxy");
      setTestStatus("ok");
    } catch (e) {
      setTestStatus("fail");
      setTestError(String(e));
    }
  }

  async function handleDone() {
    await invoke("set_setting", { key: "setup_complete", value: "true" }).catch(() => {});
    navigate("/");
  }

  return (
    <div style={s.root}>
      <div style={s.header}>
        <h1 style={s.title}>Point your AI tools at TokenPulse</h1>
        <p style={s.subtitle}>
          TokenPulse runs a local proxy at{" "}
          <code style={{ color: "#7dd3fc", backgroundColor: "#0f1520", padding: "2px 6px", borderRadius: "4px" }}>
            http://localhost:4100
          </code>
          . Configure your tools to send requests here — TokenPulse tracks everything and forwards to the real API automatically.
        </p>
        <div style={s.statusBadge(proxyRunning)}>
          <span style={s.dot(proxyRunning)} />
          {proxyRunning ? "Proxy running on port 4100" : "Proxy not detected"}
        </div>
      </div>

      <div style={s.grid}>
        {TOOLS.map((tool) => (
          <div
            key={tool.id}
            style={s.toolCard(activeTool === tool.id)}
            onClick={() => setActiveTool(activeTool === tool.id ? null : tool.id)}
          >
            <div style={s.toolHeader}>
              <span style={s.toolIcon}>{tool.icon}</span>
              <span style={s.toolName}>{tool.name}</span>
            </div>
            <div style={s.toolSummary}>{tool.summary}</div>
          </div>
        ))}
      </div>

      {selectedTool && (
        <div style={s.expandedPanel}>
          <div style={s.expandedTitle}>
            {selectedTool.icon} Setup: {selectedTool.name}
          </div>
          <div style={s.codeBlock}>{selectedTool.instructions}</div>
          <button
            style={copied ? s.copyBtnSuccess : s.copyBtn}
            onClick={() => handleCopy(selectedTool.copyValue)}
          >
            {copied ? "✅ Copied!" : `📋 ${selectedTool.copyLabel}`}
          </button>
        </div>
      )}

      <div style={s.bottomBar}>
        <button style={s.testBtn} onClick={handleTest} disabled={testStatus === "testing"}>
          {testStatus === "testing" ? "Testing..." : "🔌 Test Connection"}
        </button>

        {testStatus === "ok" && (
          <span style={s.testResult(true)}>✅ Proxy is running!</span>
        )}
        {testStatus === "fail" && (
          <span style={s.testResult(false)}>❌ {testError || "Proxy not responding"}</span>
        )}

        <button
          style={{ ...s.doneBtn, marginLeft: "auto" }}
          onClick={handleDone}
        >
          Done — Go to Dashboard →
        </button>
      </div>
    </div>
  );
}
