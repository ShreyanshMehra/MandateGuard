import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


AgentStatus = ENUM("ACTIVE", "REVOKED", name="agent_status", schema="broker", create_type=False)
ActionState = ENUM(
    "RECEIVED", "DENIED", "HELD", "BUDGET_RESERVED", "PERMIT_ISSUED",
    "EXECUTING", "SUCCEEDED", "FAILED", "UNKNOWN",
    "RECONCILED_SUCCEEDED", "RECONCILED_FAILED",
    name="action_state", schema="broker", create_type=False,
)
PolicyDecision = ENUM("ALLOW", "DENY", "HOLD", name="policy_decision", schema="broker", create_type=False)
RiskMode = ENUM("NORMAL", "ELEVATED", name="risk_mode", schema="broker", create_type=False)
EvaluationPhase = ENUM("INITIAL", "APPROVAL_RECHECK", name="evaluation_phase", schema="broker", create_type=False)
BudgetReservationState = ENUM(
    "RESERVED", "COMMITTED", "RELEASED", "UNKNOWN",
    name="budget_reservation_state", schema="broker", create_type=False,
)
PermitStatus = ENUM("ISSUED", "CONSUMED", "CANCELLED", "EXPIRED", name="permit_status", schema="broker", create_type=False)
ControlActionType = ENUM(
    "REVOKE_AGENT", "RESTORE_AGENT", "HALT", "RESUME", "SET_RISK_MODE",
    name="control_action_type", schema="broker", create_type=False,
)
ApprovalDecision = ENUM("APPROVED", "DENIED", name="approval_decision", schema="broker", create_type=False)
ReplayRunStatus = ENUM("COMPLETED", "FAILED", name="replay_run_status", schema="broker", create_type=False)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    token_subject: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(AgentStatus)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    epoch: Mapped[int] = mapped_column(BigInteger)


class AgentCredential(Base):
    __tablename__ = "agent_credentials"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.agents.id"))
    key_id: Mapped[str] = mapped_column(Text, unique=True)
    public_key_b64: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer)


class ActionRequest(Base):
    __tablename__ = "action_requests"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.agents.id"))
    idempotency_key: Mapped[str] = mapped_column(Text)
    canonical_request_hash: Mapped[str] = mapped_column(Text)
    payment_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(ActionState)
    decision: Mapped[str | None] = mapped_column(PolicyDecision, nullable=True)
    public_reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker.policy_versions.id"), nullable=True
    )
    risk_mode_snapshot: Mapped[str | None] = mapped_column(RiskMode, nullable=True)
    control_epoch_snapshot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agent_epoch_snapshot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class PolicyEvaluation(Base):
    __tablename__ = "policy_evaluations"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.action_requests.id"))
    phase: Mapped[str] = mapped_column(EvaluationPhase)
    input_snapshot: Mapped[dict] = mapped_column(JSONB)
    output_snapshot: Mapped[dict] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(PolicyDecision)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker.policy_versions.id"), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.action_requests.id"), unique=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(BudgetReservationState)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReservationAllocation(Base):
    __tablename__ = "reservation_allocations"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.budget_reservations.id"))
    scope: Mapped[str] = mapped_column(Text)
    scope_id: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    window_start: Mapped[date] = mapped_column(Date)


class ActionPermit(Base):
    __tablename__ = "action_permits"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    jti: Mapped[str] = mapped_column(Text, unique=True)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.action_requests.id"))
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.budget_reservations.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(PermitStatus)
    payload_hash: Mapped[str] = mapped_column(Text)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker.policy_versions.id"), nullable=True
    )
    control_epoch_snapshot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agent_epoch_snapshot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class ExecutionReceipt(Base):
    __tablename__ = "execution_receipts"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.action_requests.id"), unique=True)
    document: Mapped[dict] = mapped_column(JSONB)
    document_hash: Mapped[str] = mapped_column(Text)
    signature_b64: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)


class ControlAction(Base):
    __tablename__ = "control_actions"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    action_type: Mapped[str] = mapped_column(ControlActionType)
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    before_snapshot: Mapped[dict] = mapped_column(JSONB)
    after_snapshot: Mapped[dict] = mapped_column(JSONB)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.action_requests.id"), unique=True)
    approver: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(ApprovalDecision)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)


class AuditCheckpoint(Base):
    __tablename__ = "audit_checkpoints"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    manifest: Mapped[dict] = mapped_column(JSONB)
    manifest_hash: Mapped[str] = mapped_column(Text)
    signature_b64: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class AuditCheckpointItem(Base):
    __tablename__ = "audit_checkpoint_items"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.audit_checkpoints.id"))
    stream_id: Mapped[str] = mapped_column(Text)
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    last_event_hash: Mapped[str | None] = mapped_column(Text, nullable=True)


class PolicyReplayRun(Base):
    __tablename__ = "policy_replay_runs"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    candidate_config: Mapped[dict] = mapped_column(JSONB)
    baseline_policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker.policy_versions.id"), nullable=True
    )
    from_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    to_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(ReplayRunStatus)
    summary: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class PolicyReplayResult(Base):
    __tablename__ = "policy_replay_results"
    __table_args__ = {"schema": "broker"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.policy_replay_runs.id"))
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker.action_requests.id"))
    baseline_decision: Mapped[str] = mapped_column(Text)
    candidate_decision: Mapped[str] = mapped_column(Text)
    baseline_reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed: Mapped[bool] = mapped_column(Boolean)
