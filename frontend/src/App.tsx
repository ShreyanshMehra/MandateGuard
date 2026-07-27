import { useEffect, useState } from "react";

const BROKER_URL = import.meta.env.VITE_BROKER_URL ?? "http://localhost:8000";

type ServiceStatus = "checking" | "up" | "down";

export default function App() {
  const [brokerStatus, setBrokerStatus] = useState<ServiceStatus>("checking");

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

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>MandateGuard</h1>
      <p>Milestone 2 scaffold. Dashboard screens are added in Milestone 6.</p>
      <p>Broker status: {brokerStatus}</p>
    </main>
  );
}
