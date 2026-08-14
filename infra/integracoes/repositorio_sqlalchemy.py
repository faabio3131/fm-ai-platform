"""Adapters SQLAlchemy com isolamento de tenant e concorrência otimista."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from core.integracoes.modelos import AmbienteIntegracao, ConfiguracaoServicoExterno
from core.integracoes.repositorios import ConflitoVersaoConfiguracao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .modelos_orm import ServicoExternoConfigORM


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RepositorioConfiguracoesExternasSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(
        self, *, tenant_id: str, unidade_id: str, configuracao_id: str
    ) -> ConfiguracaoServicoExterno | None:
        row = self._session.scalar(
            select(ServicoExternoConfigORM).where(
                ServicoExternoConfigORM.configuracao_id == configuracao_id,
                ServicoExternoConfigORM.tenant_id == tenant_id,
                ServicoExternoConfigORM.unidade_id == unidade_id,
            )
        )
        return self._dominio(row) if row else None

    def listar(
        self, *, tenant_id: str, unidade_id: str
    ) -> tuple[ConfiguracaoServicoExterno, ...]:
        rows = self._session.scalars(
            select(ServicoExternoConfigORM)
            .where(
                ServicoExternoConfigORM.tenant_id == tenant_id,
                ServicoExternoConfigORM.unidade_id == unidade_id,
            )
            .order_by(
                ServicoExternoConfigORM.servico,
                ServicoExternoConfigORM.provedor,
                ServicoExternoConfigORM.conta_externa,
            )
        ).all()
        return tuple(self._dominio(row) for row in rows)

    def salvar(
        self,
        configuracao: ConfiguracaoServicoExterno,
        *,
        versao_esperada: int,
    ) -> ConfiguracaoServicoExterno:
        dados = self._dados(configuracao)
        if versao_esperada == 0:
            existente = self._session.get(
                ServicoExternoConfigORM,
                (
                    configuracao.tenant_id,
                    configuracao.unidade_id,
                    configuracao.configuracao_id,
                ),
            )
            if existente is not None:
                raise ConflitoVersaoConfiguracao("versao_configuracao_divergente")
            self._session.add(ServicoExternoConfigORM(**dados))
            self._session.flush()
            return configuracao

        resultado = cast(
            CursorResult[Any],
            self._session.execute(
                update(ServicoExternoConfigORM)
                .where(
                    ServicoExternoConfigORM.configuracao_id
                    == configuracao.configuracao_id,
                    ServicoExternoConfigORM.tenant_id == configuracao.tenant_id,
                    ServicoExternoConfigORM.unidade_id == configuracao.unidade_id,
                    ServicoExternoConfigORM.versao == versao_esperada,
                )
                .values(**dados)
            ),
        )
        if resultado.rowcount != 1:
            raise ConflitoVersaoConfiguracao("versao_configuracao_divergente")
        self._session.flush()
        return configuracao

    @staticmethod
    def _dados(configuracao: ConfiguracaoServicoExterno) -> dict:
        return {
            "configuracao_id": configuracao.configuracao_id,
            "tenant_id": configuracao.tenant_id,
            "unidade_id": configuracao.unidade_id,
            "servico": configuracao.servico,
            "provedor": configuracao.provedor,
            "conta_externa": configuracao.conta_externa,
            "ambiente": configuracao.ambiente.value,
            "parametros_publicos": configuracao.parametros,
            "finalidades_credenciais": configuracao.credenciais,
            "habilitada": configuracao.habilitada,
            "homologada": configuracao.homologada,
            "evidencia_homologacao_ref": configuracao.evidencia_homologacao_ref,
            "versao": configuracao.versao,
            "atualizado_por": configuracao.atualizado_por,
            "correlation_id": configuracao.correlation_id,
            "atualizado_em": configuracao.atualizado_em,
        }

    @staticmethod
    def _dominio(row: ServicoExternoConfigORM) -> ConfiguracaoServicoExterno:
        return ConfiguracaoServicoExterno(
            configuracao_id=row.configuracao_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            servico=row.servico,
            provedor=row.provedor,
            conta_externa=row.conta_externa,
            ambiente=AmbienteIntegracao(row.ambiente),
            parametros_publicos=tuple(sorted(dict(row.parametros_publicos).items())),
            finalidades_credenciais=tuple(
                sorted(dict(row.finalidades_credenciais).items())
            ),
            habilitada=row.habilitada,
            homologada=row.homologada,
            evidencia_homologacao_ref=row.evidencia_homologacao_ref,
            versao=row.versao,
            atualizado_por=row.atualizado_por,
            correlation_id=row.correlation_id,
            atualizado_em=_utc(row.atualizado_em),
        )


class ProntidaoCredenciaisSQLAlchemy:
    def __init__(self, session: Session, secret_store: SecretStore) -> None:
        self._session = session
        self._secret_store = secret_store

    def faltantes(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        provedor: str,
        finalidades: tuple[str, ...],
    ) -> tuple[str, ...]:
        faltantes: list[str] = []
        for finalidade in finalidades:
            row = self._session.scalar(
                select(CredencialReferenciaORM)
                .where(
                    CredencialReferenciaORM.tenant_id == tenant_id,
                    CredencialReferenciaORM.unidade_id == unidade_id,
                    CredencialReferenciaORM.provedor == provedor,
                    CredencialReferenciaORM.finalidade == finalidade,
                    CredencialReferenciaORM.ativa.is_(True),
                )
                .order_by(CredencialReferenciaORM.versao.desc())
                .limit(1)
            )
            if row is None:
                faltantes.append(finalidade)
                continue
            try:
                self._secret_store.resolve(row.referencia)
            except ValueError:
                faltantes.append(finalidade)
        return tuple(sorted(set(faltantes)))
