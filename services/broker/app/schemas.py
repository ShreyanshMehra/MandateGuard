from datetime import datetime

from pydantic import BaseModel, Field


class RefundRequest(BaseModel):
    payment_id: str = Field(min_length=1)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reason_code: str | None = None


class ActionResponse(BaseModel):
    action_id: str
    status: str
    decision: str | None
    reason_code: str | None
    public_explanation: str | None


class ControlRequest(BaseModel):
    reason: str = Field(min_length=1)


class RiskModeRequest(BaseModel):
    mode: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    reason: str | None = None


class ReplayRequest(BaseModel):
    candidate_config: dict
    from_time: datetime | None = None
    to_time: datetime | None = None
