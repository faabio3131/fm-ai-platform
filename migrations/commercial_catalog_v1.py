"""Migration 0051 — catálogo, pricing e promoções KCA-03."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Table, select
from sqlalchemy.engine import Connection

from infra.comercial.catalogo_orm import CatalogBase, FMCommercialPlanORM


def upgrade_commercial_catalog_v1(connection: Connection) -> None:
    CatalogBase.metadata.create_all(bind=connection, checkfirst=True)

    plan_codes = (
        "KORDENA_PLAN_A",
        "KORDENA_PLAN_B",
        "KORDENA_PLAN_C",
        "KORDENA_PLAN_D",
    )
    instante = datetime.now(timezone.utc)
    for rank, plan_code in enumerate(plan_codes, start=1):
        existente = connection.scalar(
            select(FMCommercialPlanORM.plan_id).where(
                FMCommercialPlanORM.product_code == "KORDENA",
                FMCommercialPlanORM.plan_code == plan_code,
            )
        )
        if existente is not None:
            continue
        plan_id = str(
            uuid5(
                NAMESPACE_URL,
                f"nova-fm:commercial-plan:KORDENA:{plan_code}",
            )
        )
        connection.execute(
            cast(Table, FMCommercialPlanORM.__table__).insert().values(
                plan_id=plan_id,
                product_code="KORDENA",
                plan_code=plan_code,
                rank=rank,
                status="configuration_pending",
                created_by="system:migration:0051",
                updated_by="system:migration:0051",
                version=1,
                created_at=instante,
                updated_at=instante,
            )
        )
