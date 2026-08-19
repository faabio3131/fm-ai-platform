"""Healthcheck externo real e somente leitura para Mercado Pago PIX.

Valida a credencial salva no cofre consultando os meios de pagamento disponiveis
na API oficial. Nao cria pagamento, nao movimenta dinheiro e nao homologa
automaticamente.
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
    pix_disponivel: bool
    quantidade_meios: int
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
    quantidade_meios: int,
    agora: datetime,
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = "|".join(
        (
            contexto.tenant_id,
            contexto.unidade_id,
            configuracao_id,
            str(quantidade_meios),
            instante,
            "mercado-pago-payment-methods-readonly",
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
    """Confirma acesso real e disponibilidade de PIX sem criar transacao."""

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
            "https://api.mercadopago.com/v1/payment_methods",
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
    if not 200 <= status_code < 300:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_rejeitado")
    try:
        payload = resposta.json()
    except (ValueError, TypeError) as exc:
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_payload_invalido") from exc
    if not isinstance(payload, list):
        raise ErroConfiguracaoServico("healthcheck_mercado_pago_payload_invalido")

    meios = [item for item in payload if isinstance(item, dict)]
    pix_disponivel = any(
        str(item.get("id") or "").strip().casefold() == "pix"
        or (
            str(item.get("payment_type_id") or "").strip().casefold() == "bank_transfer"
            and "pix" in str(item.get("name") or "").casefold()
        )
        for item in meios
    )
    if not pix_disponivel:
        raise ErroConfiguracaoServico("pix_mercado_pago_indisponivel")

    evidencia = _evidencia(
        contexto=contexto,
        configuracao_id=configuracao_id,
        quantidade_meios=len(meios),
        agora=agora or datetime.now(timezone.utc),
    )
    return ResultadoHealthcheckMercadoPago(
        pix_disponivel=True,
        quantidade_meios=len(meios),
        evidencia_ref=evidencia,
    )
