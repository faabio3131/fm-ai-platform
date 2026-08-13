"""Composição operacional do PagBank sem expor segredos ao usuário do caixa."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.pagamentos.pagbank import AdapterPagBank, ConfiguracaoPagBank
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM


class CredencialPagBankNaoConfigurada(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class PagBankRuntimeConfig:
    ambiente: str = "sandbox"
    notification_url: str | None = None
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> PagBankRuntimeConfig:
        ambiente = os.getenv("FM_AI_PAGBANK_ENV", "sandbox").strip().lower()
        notification_url = os.getenv("FM_AI_PAGBANK_NOTIFICATION_URL", "").strip() or None
        timeout_raw = os.getenv("FM_AI_PAGBANK_TIMEOUT_SECONDS", "10").strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise RuntimeError("FM_AI_PAGBANK_TIMEOUT_SECONDS invalido") from exc
        return cls(
            ambiente=ambiente,
            notification_url=notification_url,
            timeout_seconds=timeout_seconds,
        )


class PagBankAdapterFactory:
    """Resolve referência ativa por tenant/unidade e devolve adapter já pronto.

    A referência é persistida; o token real só existe em memória durante a criação
    do adapter e nunca é devolvido ao chamador.
    """

    PROVEDOR = "pagbank"
    FINALIDADE = "api_token"

    def __init__(
        self,
        *,
        secret_store: SecretStore | None = None,
        config: PagBankRuntimeConfig | None = None,
    ) -> None:
        self._secret_store = secret_store or ReferenceSecretStore()
        self._config = config or PagBankRuntimeConfig.from_env()

    def construir(
        self,
        *,
        session: Session,
        tenant_id: str,
        unidade_id: str,
    ) -> AdapterPagBank:
        registro = session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == tenant_id,
                CredencialReferenciaORM.unidade_id == unidade_id,
                CredencialReferenciaORM.provedor == self.PROVEDOR,
                CredencialReferenciaORM.finalidade == self.FINALIDADE,
                CredencialReferenciaORM.ativa.is_(True),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
            .limit(1)
        )
        if registro is None:
            raise CredencialPagBankNaoConfigurada(
                "referencia PagBank ativa nao configurada para tenant/unidade"
            )

        token = self._secret_store.resolve(registro.referencia).reveal()
        return AdapterPagBank(
            ConfiguracaoPagBank(
                token=token,
                ambiente=self._config.ambiente,
                notification_url=self._config.notification_url,
                timeout_seconds=self._config.timeout_seconds,
            )
        )
