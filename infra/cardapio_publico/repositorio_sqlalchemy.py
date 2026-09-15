"""Repositorio SQLAlchemy da publicacao configuravel do Cardapio Digital V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from infra.cardapio_publico.modelos_orm import PublicacaoCardapioORM


@dataclass(frozen=True)
class PublicacaoCardapioPersistida:
    public_id: str
    tenant_id: str
    unidade_id: str
    slug: str
    publicada: bool
    versao: int
    criado_em: datetime
    atualizado_em: datetime


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _to_domain(row: PublicacaoCardapioORM) -> PublicacaoCardapioPersistida:
    return PublicacaoCardapioPersistida(
        public_id=row.public_id,
        tenant_id=row.tenant_id,
        unidade_id=row.unidade_id,
        slug=row.slug,
        publicada=bool(row.publicada),
        versao=int(row.versao),
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class RepositorioCardapioPublicoSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter_por_escopo(
        self, *, tenant_id: str, unidade_id: str
    ) -> PublicacaoCardapioPersistida | None:
        row = self._session.scalar(
            select(PublicacaoCardapioORM).where(
                PublicacaoCardapioORM.tenant_id == tenant_id,
                PublicacaoCardapioORM.unidade_id == unidade_id,
            )
        )
        return None if row is None else _to_domain(row)

    def obter_por_public_id(
        self, *, public_id: str
    ) -> PublicacaoCardapioPersistida | None:
        row = self._session.get(PublicacaoCardapioORM, public_id)
        return None if row is None else _to_domain(row)

    def salvar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        slug: str,
        publicada: bool,
        versao_esperada: int,
    ) -> PublicacaoCardapioPersistida:
        atual = self.obter_por_escopo(tenant_id=tenant_id, unidade_id=unidade_id)
        instante = _agora()
        if atual is None:
            if versao_esperada != 0:
                raise RuntimeError("cardapio_publico_concorrente")
            row = PublicacaoCardapioORM(
                public_id=uuid4().hex,
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                slug=slug,
                publicada=publicada,
                versao=1,
                criado_em=instante,
                atualizado_em=instante,
            )
            self._session.add(row)
            self._session.flush()
            return _to_domain(row)

        if atual.versao != versao_esperada:
            raise RuntimeError("cardapio_publico_concorrente")

        resultado = self._session.execute(
            update(PublicacaoCardapioORM)
            .where(
                PublicacaoCardapioORM.public_id == atual.public_id,
                PublicacaoCardapioORM.versao == versao_esperada,
            )
            .values(
                slug=slug,
                publicada=publicada,
                versao=versao_esperada + 1,
                atualizado_em=instante,
            )
        )
        if resultado.rowcount != 1:
            raise RuntimeError("cardapio_publico_concorrente")
        self._session.flush()
        atualizado = self._session.get(PublicacaoCardapioORM, atual.public_id)
        if atualizado is None:  # pragma: no cover - defesa de integridade
            raise RuntimeError("cardapio_publico_nao_encontrado_apos_update")
        self._session.refresh(atualizado)
        return _to_domain(atualizado)
