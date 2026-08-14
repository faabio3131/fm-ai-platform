"""Rotação auditável de referências de credenciais externas.

O banco guarda somente a referência ao segredo (por exemplo ``env:IFOOD_SECRET``),
nunca o valor. Cada rotação cria uma nova versão e desativa a anterior, preservando
quem alterou e o correlation_id da ação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import PermissaoInsuficiente
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore

from .modelos_orm import CredencialReferenciaORM


@dataclass(frozen=True)
class CredencialReferencia:
    provedor: str
    finalidade: str
    referencia: str
    versao: int
    criada_em: datetime


class ServicoCredenciaisReferenciadas:
    def __init__(self, session: Session, secret_store: SecretStore) -> None:
        self._session = session
        self._secret_store = secret_store

    @staticmethod
    def _autorizar(contexto: ContextoExecucao) -> None:
        if Permissao.INTEGRACAO_GERENCIAR not in contexto.permissoes:
            raise PermissaoInsuficiente("integracao.gerenciar obrigatoria")

    def atual(
        self,
        *,
        contexto: ContextoExecucao,
        provedor: str,
        finalidade: str,
    ) -> CredencialReferencia | None:
        self._autorizar(contexto)
        registro = self._session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == contexto.tenant_id,
                CredencialReferenciaORM.unidade_id == contexto.unidade_id,
                CredencialReferenciaORM.provedor == provedor.strip().casefold(),
                CredencialReferenciaORM.finalidade == finalidade.strip().casefold(),
                CredencialReferenciaORM.ativa.is_(True),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
            .limit(1)
        )
        return self._to_domain(registro) if registro else None

    def rotacionar(
        self,
        *,
        contexto: ContextoExecucao,
        provedor: str,
        finalidade: str,
        nova_referencia: str,
    ) -> CredencialReferencia:
        self._autorizar(contexto)
        provider = provedor.strip().casefold()
        purpose = finalidade.strip().casefold()
        if not provider or not purpose:
            raise ValueError("provedor e finalidade sao obrigatorios")

        # Resolve antes de persistir para impedir apontar produção para segredo ausente.
        self._secret_store.resolve(nova_referencia)

        atual = self._session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == contexto.tenant_id,
                CredencialReferenciaORM.unidade_id == contexto.unidade_id,
                CredencialReferenciaORM.provedor == provider,
                CredencialReferenciaORM.finalidade == purpose,
                CredencialReferenciaORM.ativa.is_(True),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
            .limit(1)
        )
        now = datetime.now(timezone.utc)
        next_version = 1
        if atual is not None:
            atual.ativa = False
            atual.desativada_em = now
            next_version = atual.versao + 1

        registro = CredencialReferenciaORM(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            provedor=provider,
            finalidade=purpose,
            referencia=nova_referencia.strip(),
            versao=next_version,
            ativa=True,
            rotacionada_por=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            criada_em=now,
        )
        self._session.add(registro)
        self._session.flush()
        return self._to_domain(registro)

    def resolver_valor(
        self,
        *,
        contexto: ContextoExecucao,
        provedor: str,
        finalidade: str,
    ) -> str:
        atual = self.atual(
            contexto=contexto,
            provedor=provedor,
            finalidade=finalidade,
        )
        if atual is None:
            raise ValueError("credencial nao configurada")
        return self._secret_store.resolve(atual.referencia).reveal()

    def historico(
        self,
        *,
        contexto: ContextoExecucao,
        provedor: str,
        finalidade: str,
    ) -> tuple[CredencialReferencia, ...]:
        self._autorizar(contexto)
        registros = self._session.scalars(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == contexto.tenant_id,
                CredencialReferenciaORM.unidade_id == contexto.unidade_id,
                CredencialReferenciaORM.provedor == provedor.strip().casefold(),
                CredencialReferenciaORM.finalidade == finalidade.strip().casefold(),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
        ).all()
        return tuple(self._to_domain(registro) for registro in registros)

    @staticmethod
    def _to_domain(registro: CredencialReferenciaORM) -> CredencialReferencia:
        return CredencialReferencia(
            provedor=registro.provedor,
            finalidade=registro.finalidade,
            referencia=registro.referencia,
            versao=registro.versao,
            criada_em=registro.criada_em,
        )
