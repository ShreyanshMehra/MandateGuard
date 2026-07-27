import { useState } from "react";
import { adminGet, adminPost, ApiError, ReplayResult } from "../api";

const SAMPLE_CONFIG = `{
  "schema_version": "1.0",
  "policy_version": "candidate-v1",
  "supported_action": "refund_payment",
  "supported_currency": "USD",
  "approval_role": "REFUND_APPROVER",
  "fleet_budget_scope": "refund-fleet",
  "risk_modes": {
    "NORMAL": { "approval_threshold_minor": 50000, "hard_max_minor": 150000 },
    "ELEVATED": { "approval_threshold_minor": 10000, "hard_max_minor": 50000 }
  },
  "agents": {
    "refund-agent-v1": {
      "enabled": true,
      "allowed_actions": ["refund_payment"],
      "customer_scopes": ["customer-demo-001", "customer-demo-002"]
    }
  }
}`;

export default function PolicyReplay({ token }: { token: string }) {
  const [configText, setConfigText] = useState(SAMPLE_CONFIG);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<{ evaluated: number; changed: number; unchanged: number } | null>(null);
  const [results, setResults] = useState<ReplayResult[]>([]);

  const run = async () => {
    setBusy(true);
    setError(null);
    setResults([]);
    try {
      const candidate_config = JSON.parse(configText);
      const run = await adminPost<{ run_id: string; status: string; summary: typeof summary }>(
        "/api/v1/admin/policy/replay",
        token,
        { candidate_config }
      );
      if (run.status !== "COMPLETED") {
        setError("Replay run failed -- the policy service may be unreachable.");
        return;
      }
      setSummary(run.summary);
      const detail = await adminGet<{ results: ReplayResult[] }>(`/api/v1/admin/policy/replay/${run.run_id}`, token);
      setResults(detail.results);
    } catch (e) {
      setError(e instanceof SyntaxError ? `Invalid JSON: ${e.message}` : (e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Policy replay comparison</h2>
      <p className="muted">
        Read-only: re-evaluates every historical decision against the candidate config below using the real Rego
        rules. Never mutates live actions, budgets, permits or audit events.
      </p>
      <div className="field">
        <label>Candidate policy config (JSON)</label>
        <textarea rows={12} style={{ width: "100%", fontFamily: "monospace" }} value={configText} onChange={(e) => setConfigText(e.target.value)} />
      </div>
      <button disabled={busy} onClick={run}>
        {busy ? "Running…" : "Run replay"}
      </button>
      {error && <div className="error-banner">{error}</div>}
      {summary && (
        <p style={{ marginTop: "0.75rem" }}>
          Evaluated {summary.evaluated} · changed {summary.changed} · unchanged {summary.unchanged}
        </p>
      )}
      {results.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Action</th>
              <th>Baseline</th>
              <th>Candidate</th>
              <th>Changed</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.action_id}>
                <td className="muted">{r.action_id.slice(0, 8)}…</td>
                <td>
                  {r.baseline_decision} <span className="muted">({r.baseline_reason_code})</span>
                </td>
                <td>
                  {r.candidate_decision} <span className="muted">({r.candidate_reason_code})</span>
                </td>
                <td>
                  <span className={`pill ${r.changed ? "warn" : "neutral"}`}>{r.changed ? "changed" : "same"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
