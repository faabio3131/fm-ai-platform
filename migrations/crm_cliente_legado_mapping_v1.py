"""Mapeamento governado entre Cliente legado e ClienteCRM canônico.

Não copia contatos, cashback, histórico, documento fiscal ou consentimento.
Não executa backfill automático.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.crm.cliente_legado_schema import crm_cliente_legado_v1


def upgrade_crm_cliente_legado_mapping_v1(
    connection: Connection,
) -> None:
    """Cria a ponte sem inferir ou migrar vínculos existentes."""
    crm_cliente_legado_v1.create(
        bind=connection,
        checkfirst=True,
    )
