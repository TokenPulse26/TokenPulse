import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import Welcome from "./pages/Welcome";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";

export default function App() {
  const [ready, setReady] = useState(false);
  const [setupComplete, setSetupComplete] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    invoke("get_setting", { key: "setup_complete" })
      .then((val) => {
        setSetupComplete(val === "true");
        setReady(true);
      })
      .catch(() => {
        setSetupComplete(false);
        setReady(true);
      });
  }, []);

  if (!ready) {
    return (
      <div style={{ backgroundColor: "#0f1117", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "#64748b", fontSize: "14px" }}>Loading...</div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/welcome" element={<Welcome />} />
      <Route path="/setup" element={<Setup />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/" element={<Dashboard />} />
      <Route path="*" element={<Navigate to={setupComplete ? "/" : "/welcome"} replace />} />
    </Routes>
  );
}
