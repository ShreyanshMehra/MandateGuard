from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class GovernanceSnapshot:
    run_state: str
    risk_mode: str
    epoch: int
    policy_version_id: UUID
    policy_version_number: int


def fetch_governance_snapshot(session: Session) -> GovernanceSnapshot:
    row = session.execute(
        text(
            """
            SELECT gs.run_state, gs.risk_mode, gs.epoch, pv.id AS policy_version_id, pv.version_number
            FROM broker.governance_state gs
            JOIN broker.policy_versions pv ON pv.id = gs.active_policy_version_id
            WHERE gs.id = true
            """
        )
    ).one()
    return GovernanceSnapshot(
        run_state=row.run_state,
        risk_mode=row.risk_mode,
        epoch=row.epoch,
        policy_version_id=row.policy_version_id,
        policy_version_number=row.version_number,
    )
