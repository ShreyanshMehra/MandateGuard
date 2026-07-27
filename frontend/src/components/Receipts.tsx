import { useEffect, useState } from "react";
import { adminGet, ApiError, Receipt } from "../api";

export default function Receipts({ token }: { token: string }) {
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [filter, setFilter] = useState("");
  const [verifyResult, setVerifyResult] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    adminGet<{ receipts: Receipt[] }>("/api/v1/admin/receipts?limit=100", token)
      .then((r) => setReceipts(r.receipts))
      .catch((e: ApiError) => setError(e.message));

  useEffect(() => {
    if (!token) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const verify = async (actionId: string) => {
    try {
      const result = await adminGet<{ signature_valid: boolean }>(`/api/v1/admin/receipts/${actionId}/verify`, token);
      setVerifyResult({ ...verifyResult, [actionId]: result.signature_valid });
    } catch (e) {
      setError((e as ApiError).message);
    }
  };

  const filtered = receipts.filter(
    (r) => !filter || r.action_id.includes(filter) || r.bank_transaction_id.includes(filter)
  );

  return (
    <div className="card">
      <h2>Receipt search, export &amp; verification</h2>
      {error && <div className="error-banner">{error}</div>}
      <div className="field">
        <label>Search by action ID or bank transaction ID</label>
        <input value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      <table>
        <thead>
          <tr>
            <th>Action</th>
            <th>Bank txn</th>
            <th>Amount</th>
            <th>Document hash</th>
            <th>Signature</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((r) => (
            <tr key={r.action_id}>
              <td className="muted">{r.action_id}</td>
              <td>{r.bank_transaction_id}</td>
              <td>
                {r.amount_minor} {r.currency}
              </td>
              <td className="muted" style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>
                {r.document_hash}
              </td>
              <td>
                {r.action_id in verifyResult ? (
                  <span className={`pill ${verifyResult[r.action_id] ? "ok" : "bad"}`}>
                    {verifyResult[r.action_id] ? "valid" : "INVALID"}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td>
                <button className="secondary" onClick={() => verify(r.action_id)}>
                  Verify
                </button>
              </td>
            </tr>
          ))}
          {filtered.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No receipts yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
