import { useEffect, useState } from "react";
import { adminGet, adminPost, ApiError, GovernanceState } from "../api";

export default function FleetControls({ token }: { token: string }) {
  const [state, setState] = useState<GovernanceState | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    adminGet<GovernanceState>("/api/v1/admin/governance", token)
      .then(setState)
      .catch((e: ApiError) => setError(e.message));
  };

  useEffect(() => {
    if (!token) return;
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const run = async (path: string, body: Record<string, unknown>) => {
    if (!reason.trim()) {
      setError("A reason is required for every control action.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminPost(path, token, { ...body, reason });
      setReason("");
      load();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Fleet status &amp; emergency controls</h2>
      {error && <div className="error-banner">{error}</div>}
      {state ? (
        <>
          <p>
            Run state:{" "}
            <span className={`pill ${state.run_state === "RUNNING" ? "ok" : "bad"}`}>{state.run_state}</span>{" "}
            Risk mode:{" "}
            <span className={`pill ${state.risk_mode === "NORMAL" ? "ok" : "warn"}`}>{state.risk_mode}</span>{" "}
            <span className="muted">control epoch {state.epoch} · policy v{state.policy_version_number}</span>
          </p>
          <div className="inline-form">
            <div className="field">
              <label>Reason (required for every control action)</label>
              <input value={reason} onChange={(e) => setReason(e.target.value)} style={{ minWidth: 320 }} />
            </div>
          </div>
          <div className="row-actions" style={{ marginTop: "0.5rem" }}>
            <button className="danger" disabled={busy || state.run_state === "HALTED"} onClick={() => run("/api/v1/admin/fleet/halt", {})}>
              Halt fleet
            </button>
            <button disabled={busy || state.run_state === "RUNNING"} onClick={() => run("/api/v1/admin/fleet/resume", {})}>
              Resume fleet
            </button>
            <button
              className="secondary"
              disabled={busy || state.risk_mode === "ELEVATED"}
              onClick={() => run("/api/v1/admin/fleet/risk-mode", { mode: "ELEVATED" })}
            >
              Set risk ELEVATED
            </button>
            <button
              className="secondary"
              disabled={busy || state.risk_mode === "NORMAL"}
              onClick={() => run("/api/v1/admin/fleet/risk-mode", { mode: "NORMAL" })}
            >
              Set risk NORMAL
            </button>
          </div>
        </>
      ) : (
        <p className="muted">Loading…</p>
      )}
    </div>
  );
}
