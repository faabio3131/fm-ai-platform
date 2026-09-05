"""Leitura comercial dos clientes CRM persistidos por tenant/unidade."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, select
from sqlalchemy.orm import Session

from core.crm.modelos import (
    CanalMarketing,
    ClienteCRM,
    ContatoCRM,
    OrigemClienteCRM,
)
from core.marketplaces.modelos import PlataformaMarketplace


class LeitorClientesCRMSQLAlchemy:
    """Read boundary canônico; nunca cria transação nem faz commit."""

    def __init__(self, session: Session) -> None:
        self._session = session
        bind = session.connection()
        metadata = MetaData()
        self._clientes = Table("crm_clientes_v1", metadata, autoload_with=bind)
        self._contatos = Table(
            "crm_cliente_contatos_v1", metadata, autoload_with=bind
        )

    @staticmethod
    def _instante(valor: object) -> datetime:
        if not isinstance(valor, datetime):
            raise TypeError("crm_cliente_criado_em_invalido")
        if valor.tzinfo is None or valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)

    def obter(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> ClienteCRM | None:
        row = self._session.execute(
            select(self._clientes).where(
                self._clientes.c.tenant_id == tenant_id,
                self._clientes.c.unidade_id == unidade_id,
                self._clientes.c.cliente_id == cliente_id,
            )
        ).mappings().one_or_none()
        if row is None:
            return None

        contatos_rows = self._session.execute(
            select(self._contatos)
            .where(
                self._contatos.c.tenant_id == tenant_id,
                self._contatos.c.unidade_id == unidade_id,
                self._contatos.c.cliente_id == cliente_id,
            )
            .order_by(self._contatos.c.canal)
        ).mappings().all()
        contatos = tuple(
            ContatoCRM(
                canal=CanalMarketing(str(contato["canal"])),
                referencia=str(contato["referencia"]),
            )
            for contato in contatos_rows
        )

        marketplace_raw = row.get("marketplace_origem")
        marketplace = (
            None
            if marketplace_raw in (None, "")
            else PlataformaMarketplace(str(marketplace_raw))
        )
        return ClienteCRM(
            cliente_id=str(row["cliente_id"]),
            tenant_id=str(row["tenant_id"]),
            unidade_id=str(row["unidade_id"]),
            origem=OrigemClienteCRM(str(row["origem"])),
            contatos=contatos,
            criado_em=self._instante(row["criado_em"]),
            marketplace_origem=marketplace,
            versao=int(row["versao"]),
        )

    def listar(self, *, tenant_id: str, unidade_id: str) -> tuple[ClienteCRM, ...]:
        """Lista somente clientes do Active Scope recebido, sem fallback global."""

        cliente_ids = self._session.scalars(
            select(self._clientes.c.cliente_id)
            .where(
                self._clientes.c.tenant_id == tenant_id,
                self._clientes.c.unidade_id == unidade_id,
            )
            .order_by(self._clientes.c.criado_em, self._clientes.c.cliente_id)
        ).all()
        clientes: list[ClienteCRM] = []
        for cliente_id in cliente_ids:
            cliente = self.obter(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                cliente_id=str(cliente_id),
            )
            if cliente is not None:
                clientes.append(cliente)
        return tuple(clientes)
