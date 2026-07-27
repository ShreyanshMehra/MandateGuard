import { useEffect, useState } from "react";
import { ActionSummary, adminGet, ApiError } from "../api";

function money(minor: number, currency: string) {
  return `${(minor / 100).toFixed(2)} ${currency}`;
}

export default function LiveFeed({ token }: { token: string }) {
  const [actions, setActions] = useState<ActionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const load = () =>
      adminGet<{ actions: ActionSummary[] }>("/api/v1/admin/actions?limit=30", token)
        .then((r) => setActions(r.actions))
        .catch((e: ApiError) => setError(e.message));
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [token]);

  return (
    <div className="card">
      <h2>Live action feed</h2>
      {error && <div className="error-banner">{error}</div>}
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Agent</th>
            <th>Payment</th>
            <th>Amount</th>
            <th>State</th>
            <th>Decision</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((a) => (
            <tr key={a.action_id}>
              <td className="muted">{new Date(a.created_at).toLocaleTimeString()}</td>
              <td>{a.agent}</td>
              <td>{a.payment_id}</td>
              <td>{money(a.amount_minor, a.currency)}</td>
              <td>
                <span className="pill neutral">{a.state}</span>
              </td>
              <td>{a.decision}</td>
              <td className="muted">{a.reason_code}</td>
            </tr>
          ))}
          {actions.length === 0 && (
            <tr>
              <td colSpan={7} className="muted">
                No actions yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
