"""Read boundary da autoridade append-only de consentimento para marketing CRM."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from core.crm.modelos import (
    BaseLegalMarketing,
    CanalMarketing,
    ConsentimentoMarketing,
    FinalidadeMarketing,
    StatusConsentimento,
)
from infra.crm.consentimentos_schema import crm_consentimentos_v1


def _utc(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    if valor.tzinfo is None or valor.utcoffset() is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def _modelo(row: RowMapping) -> ConsentimentoMarketing:
    ocorrido_em = _utc(row["ocorrido_em"])
    if ocorrido_em is None:
        raise RuntimeError("consentimento_sem_timestamp")
    return ConsentimentoMarketing(
        consentimento_id=str(row["consentimento_id"]),
        tenant_id=str(row["tenant_id"]),
        unidade_id=str(row["unidade_id"]),
        cliente_id=str(row["cliente_id"]),
        canal=CanalMarketing(str(row["canal"])),
        finalidade=FinalidadeMarketing(str(row["finalidade"])),
        status=StatusConsentimento(str(row["status"])),
        base_legal=BaseLegalMarketing(str(row["base_legal"])),
        texto_versao=str(row["texto_versao"]),
        origem=str(row["origem"]),
        prova_hash=str(row["prova_hash"]),
        ocorrido_em=ocorrido_em,
        idempotency_key=str(row["idempotency_key"]),
        correlation_id=str(row["correlation_id"]),
        concedido_em=_utc(row["concedido_em"]),
        revogado_em=_utc(row["revogado_em"]),
    )


class LeitorConsentimentosMarketingSQLAlchemy:
    """Consulta somente o estado vigente; não possui escrita nem fallback legado."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def atual(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
    ) -> ConsentimentoMarketing | None:
        row = self._session.execute(
            select(crm_consentimentos_v1)
            .where(
                crm_consentimentos_v1.c.tenant_id == tenant_id,
                crm_consentimentos_v1.c.unidade_id == unidade_id,
                crm_consentimentos_v1.c.cliente_id == cliente_id,
                crm_consentimentos_v1.c.canal == canal.value,
                crm_consentimentos_v1.c.finalidade == finalidade.value,
            )
            .order_by(
                crm_consentimentos_v1.c.ocorrido_em.desc(),
                crm_consentimentos_v1.c.registro_seq.desc(),
            )
            .limit(1)
        ).mappings().one_or_none()
        return None if row is None else _modelo(row)

    def historico(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> tuple[ConsentimentoMarketing, ...]:
        rows = self._session.execute(
            select(crm_consentimentos_v1)
            .where(
                crm_consentimentos_v1.c.tenant_id == tenant_id,
                crm_consentimentos_v1.c.unidade_id == unidade_id,
                crm_consentimentos_v1.c.cliente_id == cliente_id,
            )
            .order_by(
                crm_consentimentos_v1.c.ocorrido_em,
                crm_consentimentos_v1.c.registro_seq,
            )
        ).mappings().all()
        return tuple(_modelo(row) for row in rows)

    def listar_atuais(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        status: StatusConsentimento,
    ) -> tuple[ConsentimentoMarketing, ...]:
        rows = self._session.execute(
            select(crm_consentimentos_v1)
            .where(
                crm_consentimentos_v1.c.tenant_id == tenant_id,
                crm_consentimentos_v1.c.unidade_id == unidade_id,
                crm_consentimentos_v1.c.canal == canal.value,
                crm_consentimentos_v1.c.finalidade == finalidade.value,
            )
            .order_by(
                crm_consentimentos_v1.c.cliente_id,
                crm_consentimentos_v1.c.ocorrido_em.desc(),
                crm_consentimentos_v1.c.registro_seq.desc(),
            )
        ).mappings().all()

        vistos: set[str] = set()
        atuais: list[ConsentimentoMarketing] = []
        for row in rows:
            cliente_id = str(row["cliente_id"])
            if cliente_id in vistos:
                continue
            vistos.add(cliente_id)
            item = _modelo(row)
            if item.status is status:
                atuais.append(item)
        return tuple(atuais)
