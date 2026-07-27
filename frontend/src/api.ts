export const BROKER_URL = import.meta.env.VITE_BROKER_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BROKER_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Operator-Token": token,
      ...(init.headers ?? {}),
    },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error ?? body?.detail?.error;
    throw new ApiError(err?.code ?? "UNKNOWN_ERROR", err?.message ?? `Request failed with ${res.status}`);
  }
  return body as T;
}

export function adminGet<T>(path: string, token: string): Promise<T> {
  return request<T>(path, token, { method: "GET" });
}

export function adminPost<T>(path: string, token: string, body: unknown): Promise<T> {
  return request<T>(path, token, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(body ?? {}),
  });
}

export interface GovernanceState {
  run_state: "RUNNING" | "HALTED";
  risk_mode: "NORMAL" | "ELEVATED";
  epoch: number;
  policy_version_number: number;
  fleet_budget_scope: string;
}

export interface AgentSummary {
  agent_id: string;
  token_subject: string;
  display_name: string;
  status: "ACTIVE" | "REVOKED";
  status_reason: string | null;
  epoch: number;
}

export interface ActionSummary {
  action_id: string;
  agent: string;
  state: string;
  decision: string | null;
  payment_id: string;
  customer_id: string | null;
  amount_minor: number;
  currency: string;
  reason_code: string | null;
  created_at: string;
}

export interface ActionDetail extends ActionSummary {
  operator_explanation: string | null;
  risk_mode_snapshot: string | null;
  control_epoch_snapshot: number | null;
  agent_epoch_snapshot: number | null;
  reservation: { amount_minor: number; currency: string; state: string; resolution_reason: string | null } | null;
  permit: { jti: string; status: string; attempt_number: number; expires_at: string } | null;
  receipt: { bank_transaction_id: string; document_hash: string; key_id: string } | null;
  audit_events: { sequence: number; event_type: string; actor: string; payload: unknown; created_at: string }[];
}

export interface ExposureScope {
  usage_minor: number;
  cap_minor: number;
}

export interface Exposure {
  fleet: ExposureScope;
  agents: ({ agent: string } & ExposureScope)[];
  top_customers: ({ customer_id: string } & ExposureScope)[];
}

export interface Receipt {
  action_id: string;
  bank_transaction_id: string;
  amount_minor: number;
  currency: string;
  document_hash: string;
  key_id: string;
  created_at: string;
}

export interface ReplayResult {
  action_id: string;
  baseline_decision: string;
  candidate_decision: string;
  baseline_reason_code: string | null;
  candidate_reason_code: string | null;
  changed: boolean;
}
