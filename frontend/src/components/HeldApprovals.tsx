import { useEffect, useState } from "react";
import { ActionSummary, adminGet, adminPost, ApiError } from "../api";

export default function HeldApprovals({ token }: { token: string }) {
  const [held, setHeld] = useState<ActionSummary[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    adminGet<{ actions: ActionSummary[] }>("/api/v1/admin/actions?state=HELD&limit=50", token)
      .then((r) => setHeld(r.actions))
      .catch((e: ApiError) => setError(e.message));

  useEffect(() => {
    if (!token) return;
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const decide = async (actionId: string, decision: "approve" | "deny") => {
    setBusy(actionId);
    setError(null);
    try {
      await adminPost(`/api/v1/admin/actions/${actionId}/${decision}`, token, { reason: reasons[actionId] ?? "" });
      load();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card">
      <h2>Held approvals</h2>
      {error && <div className="error-banner">{error}</div>}
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Payment</th>
            <th>Amount</th>
            <th>Reason</th>
            <th>Approval reason</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {held.map((a) => (
            <tr key={a.action_id}>
              <td>{a.agent}</td>
              <td>{a.payment_id}</td>
              <td>
                {a.amount_minor} {a.currency}
              </td>
              <td className="muted">{a.reason_code}</td>
              <td>
                <input
                  placeholder="reason"
                  value={reasons[a.action_id] ?? ""}
                  onChange={(e) => setReasons({ ...reasons, [a.action_id]: e.target.value })}
                />
              </td>
              <td className="row-actions">
                <button disabled={busy === a.action_id} onClick={() => decide(a.action_id, "approve")}>
                  Approve
                </button>
                <button className="danger" disabled={busy === a.action_id} onClick={() => decide(a.action_id, "deny")}>
                  Deny
                </button>
              </td>
            </tr>
          ))}
          {held.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                Nothing awaiting approval.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
