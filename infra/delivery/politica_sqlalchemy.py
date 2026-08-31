"""Repositório SQLAlchemy da política de entrega por tenant/unidade."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.delivery.modelos import AreaEntrega, OrigemEntrega
from core.delivery.modelos_orm import AreaEntregaORM, OrigemEntregaORM


class RepositorioPoliticaEntregaSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter_origem(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> OrigemEntrega | None:
        row = self._session.get(OrigemEntregaORM, (tenant_id, unidade_id))
        if row is None or not row.ativa:
            return None
        return OrigemEntrega(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            endereco_texto=row.endereco_texto,
            versao=row.versao,
            ativa=row.ativa,
        )

    def listar_areas(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> tuple[AreaEntrega, ...]:
        rows = self._session.scalars(
            select(AreaEntregaORM)
            .where(
                AreaEntregaORM.tenant_id == tenant_id,
                AreaEntregaORM.unidade_id == unidade_id,
                AreaEntregaORM.ativa.is_(True),
            )
            .order_by(AreaEntregaORM.nome, AreaEntregaORM.area_id)
        ).all()
        return tuple(
            AreaEntrega(
                area_id=row.area_id,
                tenant_id=row.tenant_id,
                unidade_id=row.unidade_id,
                nome=row.nome,
                prefixos_cep=tuple(str(item) for item in row.prefixos_cep),
                taxa=Decimal(row.taxa),
                sla_minutos=row.sla_minutos,
                sla_maxutos=row.sla_maxutos,
                versao=row.versao,
                ativa=row.ativa,
            )
            for row in rows
        )

    def configurar_origem(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        endereco_texto: str,
    ) -> OrigemEntrega:
        endereco = " ".join(endereco_texto.split())
        if not endereco:
            raise ValueError("endereco de origem obrigatorio")

        row = self._session.get(OrigemEntregaORM, (tenant_id, unidade_id))
        agora = datetime.now(timezone.utc)
        if row is None:
            row = OrigemEntregaORM(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                endereco_texto=endereco,
                versao=1,
                ativa=True,
                atualizado_em=agora,
            )
            self._session.add(row)
        else:
            row.endereco_texto = endereco
            row.versao += 1
            row.ativa = True
            row.atualizado_em = agora
        self._session.flush()
        return OrigemEntrega(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            endereco_texto=row.endereco_texto,
            versao=row.versao,
            ativa=row.ativa,
        )

    def configurar_area(
        self,
        *,
        area: AreaEntrega,
    ) -> AreaEntrega:
        chave = (area.tenant_id, area.unidade_id, area.area_id)
        row = self._session.get(AreaEntregaORM, chave)
        agora = datetime.now(timezone.utc)
        if row is None:
            row = AreaEntregaORM(
                tenant_id=area.tenant_id,
                unidade_id=area.unidade_id,
                area_id=area.area_id,
                nome=area.nome,
                prefixos_cep=list(area.prefixos_cep),
                taxa=area.taxa,
                sla_minutos=area.sla_minutos,
                sla_maxutos=area.sla_maxutos,
                versao=area.versao,
                ativa=area.ativa,
                atualizado_em=agora,
            )
            self._session.add(row)
        else:
            row.nome = area.nome
            row.prefixos_cep = list(area.prefixos_cep)
            row.taxa = area.taxa
            row.sla_minutos = area.sla_minutos
            row.sla_maxutos = area.sla_maxutos
            row.versao += 1
            row.ativa = area.ativa
            row.atualizado_em = agora
        self._session.flush()
        return AreaEntrega(
            area_id=row.area_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            nome=row.nome,
            prefixos_cep=tuple(str(item) for item in row.prefixos_cep),
            taxa=Decimal(row.taxa),
            sla_minutos=row.sla_minutos,
            sla_maxutos=row.sla_maxutos,
            versao=row.versao,
            ativa=row.ativa,
        )
