import { useEffect, useState } from "react";
import { adminGet, ApiError, Exposure as ExposureData } from "../api";

function Bar({ usage, cap }: { usage: number; cap: number }) {
  const pct = cap > 0 ? Math.min(100, (usage / cap) * 100) : 0;
  return (
    <div className="bar">
      <div className={`bar-fill ${pct > 85 ? "hot" : ""}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function Exposure({ token }: { token: string }) {
  const [data, setData] = useState<ExposureData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const load = () =>
      adminGet<ExposureData>("/api/v1/admin/exposure", token)
        .then(setData)
        .catch((e: ApiError) => setError(e.message));
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [token]);

  if (error) return <div className="card error-banner">{error}</div>;
  if (!data) return <div className="card muted">Loading…</div>;

  return (
    <div className="card">
      <h2>Customer, agent and fleet exposure (today, USD)</h2>
      <p>
        Fleet: {data.fleet.usage_minor} / {data.fleet.cap_minor} minor
      </p>
      <Bar usage={data.fleet.usage_minor} cap={data.fleet.cap_minor} />

      <h3 style={{ marginTop: "1rem", fontSize: "0.85rem" }}>Agents</h3>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Usage</th>
            <th>Cap</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.agents.map((a) => (
            <tr key={a.agent}>
              <td>{a.agent}</td>
              <td>{a.usage_minor}</td>
              <td>{a.cap_minor}</td>
              <td style={{ width: "30%" }}>
                <Bar usage={a.usage_minor} cap={a.cap_minor} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: "1rem", fontSize: "0.85rem" }}>Top customers</h3>
      <table>
        <thead>
          <tr>
            <th>Customer</th>
            <th>Usage</th>
            <th>Cap</th>
          </tr>
        </thead>
        <tbody>
          {data.top_customers.map((c) => (
            <tr key={c.customer_id}>
              <td>{c.customer_id}</td>
              <td>{c.usage_minor}</td>
              <td>{c.cap_minor}</td>
            </tr>
          ))}
          {data.top_customers.length === 0 && (
            <tr>
              <td colSpan={3} className="muted">
                No customer exposure yet today.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
