"""Migration 0055 — Trial Engine KCA-07."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from core.comercial.trial import TRIAL_DURATION_DAYS, TRIAL_POLICY_VERSION
from infra.comercial.trial_orm import FMCommercialTrialPolicyORM, TrialBase


def upgrade_commercial_trial_v1(connection: Connection) -> None:
    TrialBase.metadata.create_all(bind=connection, checkfirst=True)
    table = FMCommercialTrialPolicyORM.__table__
    existing = connection.execute(
        select(table.c.policy_version).where(
            table.c.policy_version == TRIAL_POLICY_VERSION
        )
    ).scalar_one_or_none()
    if existing is None:
        connection.execute(
            insert(table).values(
                policy_version=TRIAL_POLICY_VERSION,
                duration_days=TRIAL_DURATION_DAYS,
                active=True,
                effective_from=datetime(1970, 1, 1, tzinfo=timezone.utc),
                created_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
            )
        )
