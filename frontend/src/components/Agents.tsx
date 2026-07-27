import { useEffect, useState } from "react";
import { adminGet, adminPost, AgentSummary, ApiError } from "../api";

export default function Agents({ token }: { token: string }) {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    adminGet<{ agents: AgentSummary[] }>("/api/v1/admin/agents", token)
      .then((r) => setAgents(r.agents))
      .catch((e: ApiError) => setError(e.message));

  useEffect(() => {
    if (!token) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const act = async (agentId: string, action: "revoke" | "restore") => {
    const reason = reasons[agentId];
    if (!reason?.trim()) {
      setError("A reason is required to revoke or restore an agent.");
      return;
    }
    setBusy(agentId);
    setError(null);
    try {
      await adminPost(`/api/v1/admin/agents/${agentId}/${action}`, token, { reason });
      load();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card">
      <h2>Agent details &amp; revocation</h2>
      {error && <div className="error-banner">{error}</div>}
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Status</th>
            <th>Epoch</th>
            <th>Reason</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.agent_id}>
              <td>
                {a.display_name} <span className="muted">({a.token_subject})</span>
              </td>
              <td>
                <span className={`pill ${a.status === "ACTIVE" ? "ok" : "bad"}`}>{a.status}</span>
                {a.status_reason && <div className="muted">{a.status_reason}</div>}
              </td>
              <td>{a.epoch}</td>
              <td>
                <input
                  placeholder="reason"
                  value={reasons[a.agent_id] ?? ""}
                  onChange={(e) => setReasons({ ...reasons, [a.agent_id]: e.target.value })}
                />
              </td>
              <td className="row-actions">
                <button
                  className="danger"
                  disabled={busy === a.agent_id || a.status === "REVOKED"}
                  onClick={() => act(a.agent_id, "revoke")}
                >
                  Revoke
                </button>
                <button disabled={busy === a.agent_id || a.status === "ACTIVE"} onClick={() => act(a.agent_id, "restore")}>
                  Restore
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
