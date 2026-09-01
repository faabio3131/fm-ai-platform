"""Leitura produtiva da autoridade append-only de consentimentos CRM."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.assistente_atendimento.customer_context import (
    ConsentimentoContextoAtendimento,
)
from infra.crm.consentimentos_schema import crm_consentimentos_v1


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


class RepositorioConsentimentosContextoSQLAlchemy:
    """Projeta somente o consentimento vigente por canal/finalidade."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def atuais_cliente(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
    ) -> tuple[ConsentimentoContextoAtendimento, ...]:
        rows = self._session.execute(
            select(crm_consentimentos_v1)
            .where(
                crm_consentimentos_v1.c.tenant_id == tenant_id,
                crm_consentimentos_v1.c.unidade_id == unidade_id,
                crm_consentimentos_v1.c.cliente_id == cliente_id,
            )
            .order_by(
                crm_consentimentos_v1.c.ocorrido_em.desc(),
                crm_consentimentos_v1.c.registro_seq.desc(),
            )
        ).mappings().all()

        vistos: set[tuple[str, str]] = set()
        atuais: list[ConsentimentoContextoAtendimento] = []
        for row in rows:
            chave = (str(row["canal"]), str(row["finalidade"]))
            if chave in vistos:
                continue
            vistos.add(chave)
            atuais.append(
                ConsentimentoContextoAtendimento(
                    canal=chave[0],
                    finalidade=chave[1],
                    status=str(row["status"]),
                    ocorrido_em=_utc(row["ocorrido_em"]),
                )
            )
        atuais.sort(key=lambda item: (item.canal, item.finalidade))
        return tuple(atuais)
