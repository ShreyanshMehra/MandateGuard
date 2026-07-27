import { useEffect, useState } from "react";
import "./App.css";
import { BROKER_URL } from "./api";
import FleetControls from "./components/FleetControls";
import LiveFeed from "./components/LiveFeed";
import Exposure from "./components/Exposure";
import HeldApprovals from "./components/HeldApprovals";
import Agents from "./components/Agents";
import PolicyReplay from "./components/PolicyReplay";
import Receipts from "./components/Receipts";

type ServiceStatus = "checking" | "up" | "down";
type Tab = "fleet" | "feed" | "exposure" | "approvals" | "agents" | "replay" | "receipts";

const TABS: { id: Tab; label: string }[] = [
  { id: "fleet", label: "Fleet & controls" },
  { id: "feed", label: "Live feed" },
  { id: "exposure", label: "Exposure" },
  { id: "approvals", label: "Held approvals" },
  { id: "agents", label: "Agents" },
  { id: "replay", label: "Policy replay" },
  { id: "receipts", label: "Receipts" },
];

export default function App() {
  const [brokerStatus, setBrokerStatus] = useState<ServiceStatus>("checking");
  const [token, setToken] = useState(() => localStorage.getItem("mandateguard_operator_token") ?? "");
  const [tab, setTab] = useState<Tab>("fleet");

  useEffect(() => {
    let cancelled = false;
    fetch(`${BROKER_URL}/health`)
      .then((res) => {
        if (!cancelled) setBrokerStatus(res.ok ? "up" : "down");
      })
      .catch(() => {
        if (!cancelled) setBrokerStatus("down");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("mandateguard_operator_token", token);
  }, [token]);

  return (
    <div className="app">
      <header className="top-bar">
        <h1>MandateGuard — Operator Dashboard</h1>
        <div className="token-input">
          <span className={`pill ${brokerStatus === "up" ? "ok" : brokerStatus === "down" ? "bad" : "neutral"}`}>
            broker {brokerStatus}
          </span>
          <label className="muted" htmlFor="operator-token">
            Operator token
          </label>
          <input
            id="operator-token"
            type="password"
            placeholder="X-Operator-Token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 220 }}
          />
        </div>
      </header>

      {!token && (
        <div className="error-banner">
          Enter the operator token to load governance data (dev default: <code>dev_operator_token_change_me</code>).
        </div>
      )}

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {token && (
        <>
          {tab === "fleet" && <FleetControls token={token} />}
          {tab === "feed" && <LiveFeed token={token} />}
          {tab === "exposure" && <Exposure token={token} />}
          {tab === "approvals" && <HeldApprovals token={token} />}
          {tab === "agents" && <Agents token={token} />}
          {tab === "replay" && <PolicyReplay token={token} />}
          {tab === "receipts" && <Receipts token={token} />}
        </>
      )}
    </div>
  );
}
