"""Healthcheck externo real e somente leitura para Mercado Pago.

Valida o Access Token salvo no cofre por uma chamada autenticada somente leitura.
Nao cria pagamento, nao movimenta dinheiro, nao infere suporte a Pix e nao homologa
automaticamente. A capacidade Pix e comprovada depois por uma Order sandbox real,
conforme o fluxo oficial do Checkout Transparente / Orders API.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy


class PortaHTTPMercadoPagoHealthcheck(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> Any: ...


@dataclass(frozen=True, kw_only=True)
class ResultadoHealthcheckMercadoPago:
    credencial_valida: bool
    evidencia_ref: str


def _segredo(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    finalidade: str,
) -> str:
    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == contexto.tenant_id,
            CredencialReferenciaORM.unidade_id == contexto.unidade_id,
            CredencialReferenciaORM.provedor == "mercado_pago",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_mercado_pago_indisponivel")
    return secret_store.resolve(row.referencia).reveal()


def _evidencia(
    *,
    contexto: ContextoExecucao,
    configuracao_id: str,
    usuario_id: str,
    agora: datetime,
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = "|".join(
        (
            contexto.tenant_id,
            contexto.unidade_id,
            configuracao_id,
            usuario_id,
            instante,
            "mercado-pago-users-me-readonly",
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://mercado-pago-access/{instante}/{digest}"


def executar_healthcheck_mercado_pago(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    configuracao_id: str = "pagamentos.pix--mercado_pago",
    http: PortaHTTPMercadoPagoHealthcheck | None = None,
    agora: datetime | None = None,
) -> ResultadoHealthcheckMercadoPago:
    """Confirma autenticacao real do Access Token sem criar transacao."""

    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        configuracao_id=configuracao_id,
    )
    if config is None:
        raise ErroConfiguracaoServico("configuracao_indisponivel")
    if (config.servico, config.provedor) != ("pagamentos.pix", "mercado_pago"):
        raise ErroConfiguracaoServico("adapter_incompativel")
    if not config.habilitada:
        raise ErroConfiguracaoServico("integracao_desabilitada")

    finalidade = str(config.credenciais.get("access_token") or "").strip()
    if not finalidade:
        raise ErroConfiguracaoServico("access_token_mercado_pago_indisponivel")

    access_token = _segredo(
        session=session,
        secret_store=secret_store,
        contexto=contexto,
        finalidade=finalidade,
    )

    cliente = http or requests.Session()
    try:
        resposta = cliente.get(
            "https://api.mercadolibre.com/users/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=8.0,
        )
    except requests.Timeout as exc:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_timeout") from exc
    except requests.RequestException as exc:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_transporte") from exc

    status_code = int(getattr(resposta, "status_code", 0) or 0)
    if status_code in {401, 403}:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_credencial_rejeitada")
    if not 200 <= status_code < 300:
        raise ErroConfiguracaoServico(
            f"healthcheck_mercado_pago_http_{status_code or 'desconhecido'}"
        )
    try:
        payload = resposta.json()
    except (ValueError, TypeError) as exc:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_payload_invalido") from exc
    if not isinstance(payload, dict):
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_payload_invalido")

    usuario_id = str(payload.get("id") or "").strip()
    if not usuario_id:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_identidade_ausente")

    evidencia = _evidencia(
        contexto=contexto,
        configuracao_id=configuracao_id,
        usuario_id=usuario_id,
        agora=agora or datetime.now(timezone.utc),
    )
    return ResultadoHealthcheckMercadoPago(
        credencial_valida=True,
        evidencia_ref=evidencia,
    )
