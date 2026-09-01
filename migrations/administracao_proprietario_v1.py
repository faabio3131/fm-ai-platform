"""Migration 0036 — cadastro administrativo da empresa e unidades."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection

from infra.administracao.modelos_orm import (
    AdminBase,
    ConfiguracaoEstabelecimentoORM,
    EmpresaAdminORM,
    UnidadeAdminORM,
)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _nome_unidade_legada(
    connection: Connection,
    *,
    tenant_id: str,
    unidade_id: str,
) -> str | None:
    tabelas = set(inspect(connection).get_table_names())
    if not {"fm_unidade_loja_legacy_v1", "lojas"} <= tabelas:
        return None
    row = connection.execute(
        text(
            """
            SELECT l.nome_fantasia
            FROM fm_unidade_loja_legacy_v1 AS m
            JOIN lojas AS l ON l.id = m.loja_id
            WHERE m.tenant_id = :tenant_id
              AND m.unidade_id = :unidade_id
              AND m.ativo = TRUE
            ORDER BY l.id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "unidade_id": unidade_id},
    ).first()
    if row is None:
        return None
    valor = str(row[0] or "").strip()
    return valor or None


def _escopos_existentes(connection: Connection) -> tuple[tuple[str, str], ...]:
    tabelas = set(inspect(connection).get_table_names())
    if "fm_usuarios_v1" not in tabelas:
        return ()

    pares: set[tuple[str, str]] = set()
    for tenant_id, unidade_id in connection.execute(
        text(
            """
            SELECT tenant_id, unidade_padrao_id
            FROM fm_usuarios_v1
            WHERE tenant_id IS NOT NULL
              AND unidade_padrao_id IS NOT NULL
            """
        )
    ):
        tenant = str(tenant_id or "").strip()
        unidade = str(unidade_id or "").strip()
        if tenant and unidade:
            pares.add((tenant, unidade))

    if "fm_usuario_unidades_v1" in tabelas:
        for tenant_id, unidade_id in connection.execute(
            text(
                """
                SELECT u.tenant_id, uu.unidade_id
                FROM fm_usuario_unidades_v1 AS uu
                JOIN fm_usuarios_v1 AS u ON u.usuario_id = uu.usuario_id
                WHERE u.tenant_id IS NOT NULL
                  AND uu.unidade_id IS NOT NULL
                """
            )
        ):
            tenant = str(tenant_id or "").strip()
            unidade = str(unidade_id or "").strip()
            if tenant and unidade:
                pares.add((tenant, unidade))

    if "fm_unidade_loja_legacy_v1" in tabelas:
        for tenant_id, unidade_id in connection.execute(
            text(
                """
                SELECT tenant_id, unidade_id
                FROM fm_unidade_loja_legacy_v1
                WHERE ativo = TRUE
                """
            )
        ):
            tenant = str(tenant_id or "").strip()
            unidade = str(unidade_id or "").strip()
            if tenant and unidade:
                pares.add((tenant, unidade))

    return tuple(sorted(pares))


def upgrade_administracao_proprietario_v1(connection: Connection) -> None:
    AdminBase.metadata.create_all(bind=connection)
    instante = _agora()

    for tenant_id, unidade_id in _escopos_existentes(connection):
        empresa = connection.scalar(
            select(EmpresaAdminORM).where(EmpresaAdminORM.tenant_id == tenant_id)
        )
        if empresa is None:
            connection.execute(
                EmpresaAdminORM.__table__.insert().values(
                    tenant_id=tenant_id,
                    nome_exibicao=tenant_id,
                    moeda="BRL",
                    timezone="America/Sao_Paulo",
                    ativa=True,
                    versao=1,
                    criado_em=instante,
                    atualizado_em=instante,
                )
            )

        unidade = connection.scalar(
            select(UnidadeAdminORM).where(
                UnidadeAdminORM.tenant_id == tenant_id,
                UnidadeAdminORM.unidade_id == unidade_id,
            )
        )
        if unidade is None:
            nome = _nome_unidade_legada(
                connection,
                tenant_id=tenant_id,
                unidade_id=unidade_id,
            ) or unidade_id
            connection.execute(
                UnidadeAdminORM.__table__.insert().values(
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    codigo=unidade_id,
                    nome_fantasia=nome,
                    tipo="unidade",
                    documento_fiscal=None,
                    telefone=None,
                    email=None,
                    endereco={},
                    horarios={},
                    ativa=True,
                    versao=1,
                    criado_em=instante,
                    atualizado_em=instante,
                )
            )

        configuracao = connection.scalar(
            select(ConfiguracaoEstabelecimentoORM).where(
                ConfiguracaoEstabelecimentoORM.tenant_id == tenant_id,
                ConfiguracaoEstabelecimentoORM.unidade_id == unidade_id,
            )
        )
        if configuracao is None:
            connection.execute(
                ConfiguracaoEstabelecimentoORM.__table__.insert().values(
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    formas_pagamento=[],
                    taxa_servico_percentual=Decimal("0"),
                    parametros_operacionais={},
                    politica_financeira={},
                    versao=1,
                    atualizado_em=instante,
                )
            )
