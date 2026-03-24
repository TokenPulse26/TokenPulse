import { useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";

const s = {
  root: {
    backgroundColor: "#0a0d14",
    color: "#e2e8f0",
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    padding: "48px 24px",
  },
  wordmark: {
    fontSize: "52px",
    fontWeight: "800",
    letterSpacing: "-0.03em",
    background: "linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #a78bfa 100%)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
    backgroundClip: "text",
    marginBottom: "16px",
    lineHeight: 1,
  },
  tagline: {
    fontSize: "18px",
    color: "#94a3b8",
    textAlign: "center",
    maxWidth: "480px",
    lineHeight: 1.6,
    marginBottom: "64px",
  },
  features: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "20px",
    marginBottom: "64px",
    maxWidth: "720px",
    width: "100%",
  },
  featureCard: {
    backgroundColor: "#161b27",
    border: "1px solid #1e2d40",
    borderRadius: "16px",
    padding: "28px 24px",
    textAlign: "center",
  },
  featureIcon: {
    fontSize: "36px",
    marginBottom: "12px",
    display: "block",
  },
  featureTitle: {
    fontSize: "14px",
    fontWeight: "700",
    color: "#f1f5f9",
    marginBottom: "6px",
  },
  featureDesc: {
    fontSize: "12px",
    color: "#64748b",
    lineHeight: 1.5,
  },
  btnPrimary: {
    backgroundColor: "#6366f1",
    color: "#fff",
    border: "none",
    borderRadius: "12px",
    padding: "16px 40px",
    fontSize: "16px",
    fontWeight: "700",
    cursor: "pointer",
    marginBottom: "20px",
    transition: "background 0.15s",
    letterSpacing: "0.01em",
  },
  skipLink: {
    fontSize: "13px",
    color: "#475569",
    background: "none",
    border: "none",
    cursor: "pointer",
    textDecoration: "underline",
    padding: 0,
  },
};

export default function Welcome() {
  const navigate = useNavigate();

  async function handleSkip() {
    await invoke("set_setting", { key: "setup_complete", value: "true" }).catch(() => {});
    navigate("/");
  }

  return (
    <div style={s.root}>
      <div style={s.wordmark}>TokenPulse</div>
      <p style={s.tagline}>
        See exactly what every AI call costs you, across every model, in one place.
      </p>

      <div style={s.features}>
        <div style={s.featureCard}>
          <span style={s.featureIcon}>☁️</span>
          <div style={s.featureTitle}>Cloud APIs</div>
          <div style={s.featureDesc}>OpenAI, Anthropic, Google, Mistral, Groq</div>
        </div>
        <div style={s.featureCard}>
          <span style={s.featureIcon}>🖥️</span>
          <div style={s.featureTitle}>Local Models</div>
          <div style={s.featureDesc}>Ollama, LM Studio, vLLM, llama.cpp</div>
        </div>
        <div style={s.featureCard}>
          <span style={s.featureIcon}>📊</span>
          <div style={s.featureTitle}>Live Dashboard</div>
          <div style={s.featureDesc}>Real-time cost tracking and analytics</div>
        </div>
      </div>

      <button
        style={s.btnPrimary}
        onMouseEnter={(e) => (e.target.style.backgroundColor = "#4f46e5")}
        onMouseLeave={(e) => (e.target.style.backgroundColor = "#6366f1")}
        onClick={() => navigate("/setup")}
      >
        Get Started →
      </button>
      <button style={s.skipLink} onClick={handleSkip}>
        Skip setup, show me the dashboard →
      </button>
    </div>
  );
}
