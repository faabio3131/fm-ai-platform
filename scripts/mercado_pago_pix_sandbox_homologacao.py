"""Prova transacional controlada do Mercado Pago Pix em sandbox.

Cria uma Order Pix de TESTE usando os valores predefinidos documentados pelo
Mercado Pago para Checkout Transparente via Orders. Nunca aceita ambiente de
producao e nunca imprime Access Token, webhook secret ou QR Code completo.

Execucao local:

    python -m scripts.mercado_pago_pix_sandbox_homologacao

O processo carrega .env, resolve a credencial salva no cofre do tenant/unidade
do runtime, cria a Order sandbox, faz uma consulta GET da mesma Order e imprime
somente um resumo sanitizado e uma referencia de evidencia.

Importante: a Orders API nao recebe ``notification_url`` no body desta prova.
A entrega de notificacoes de Order deve estar configurada na aplicacao do
Mercado Pago/Webhooks para o topico de Orders. A URL publica mantida no cadastro
local da Kordena continua sendo usada pelo receptor/integracao, mas nao e enviada
como campo do POST /v1/orders.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

import requests
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from core.runtime import build_engine, load_runtime_settings
from infra.integracoes.repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.seguranca.session_guard import build_session_factory

_CONFIG_ID = "pagamentos.pix--mercado_pago"
_BASE_URL = "https://api.mercadopago.com"


class PortaHTTPMercadoPagoSandbox(Protocol):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any: ...
    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> Any: ...


@dataclass(frozen=True, kw_only=True)
class ResultadoPixSandbox:
    order_id: str
    status_criacao: str
    status_consulta: str
    qr_code_presente: bool
    ticket_url_presente: bool
    evidencia_ref: str


def _segredo_access_token(session: Session, *, tenant_id: str, unidade_id: str, finalidade: str) -> str:
    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == tenant_id,
            CredencialReferenciaORM.unidade_id == unidade_id,
            CredencialReferenciaORM.provedor == "mercado_pago",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_mercado_pago_indisponivel")
    return EncryptedSQLAlchemySecretStore(session).resolve(row.referencia).reveal()


def _primeiro_pagamento(payload: dict[str, Any]) -> dict[str, Any]:
    transacoes = payload.get("transactions")
    if not isinstance(transacoes, dict):
        return {}
    pagamentos = transacoes.get("payments")
    if not isinstance(pagamentos, list) or not pagamentos or not isinstance(pagamentos[0], dict):
        return {}
    return pagamentos[0]


def _evidencia(*, tenant_id: str, unidade_id: str, order_id: str, status: str, agora: datetime) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = "|".join((tenant_id, unidade_id, order_id, status, instante, "mercado-pago-pix-orders-sandbox"))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://mercado-pago-pix-sandbox/{instante}/{digest}"


def executar_teste_pix_sandbox(
    *,
    session: Session,
    tenant_id: str,
    unidade_id: str,
    http: PortaHTTPMercadoPagoSandbox | None = None,
    agora: datetime | None = None,
) -> ResultadoPixSandbox:
    """Cria e consulta uma Order Pix oficial de teste, exclusivamente em sandbox."""

    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        configuracao_id=_CONFIG_ID,
    )
    if config is None or not config.habilitada:
        raise ErroConfiguracaoServico("configuracao_mercado_pago_indisponivel")
    if config.ambiente is not AmbienteIntegracao.SANDBOX:
        raise ErroConfiguracaoServico("teste_pix_sandbox_bloqueado_fora_de_sandbox")
    if (config.servico, config.provedor) != ("pagamentos.pix", "mercado_pago"):
        raise ErroConfiguracaoServico("adapter_mercado_pago_incompativel")

    finalidade = str(config.credenciais.get("access_token") or "").strip()
    if not finalidade:
        raise ErroConfiguracaoServico("access_token_mercado_pago_indisponivel")
    access_token = _segredo_access_token(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        finalidade=finalidade,
    )

    cliente = http or requests.Session()
    idempotency_key = f"kordena-sandbox-{uuid4().hex}"
    external_reference = f"kordena-sandbox-{uuid4().hex[:16]}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Idempotency-Key": idempotency_key,
    }
    body = {
        "type": "online",
        "external_reference": external_reference,
        "total_amount": "50.00",
        "processing_mode": "automatic",
        "payer": {
            "email": "test_user_br@testuser.com",
            "first_name": "APRO",
        },
        "transactions": {
            "payments": [
                {
                    "amount": "50.00",
                    "payment_method": {"id": "pix", "type": "bank_transfer"},
                }
            ]
        },
    }

    try:
        resposta = cliente.post(f"{_BASE_URL}/v1/orders", headers=headers, json=body, timeout=12.0)
    except requests.RequestException as exc:
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_transporte") from exc
    status_code = int(getattr(resposta, "status_code", 0) or 0)
    if not 200 <= status_code < 300:
        raise ErroConfiguracaoServico(f"mercado_pago_pix_sandbox_http_{status_code or 'desconhecido'}")
    try:
        criado = resposta.json()
    except (ValueError, TypeError) as exc:
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_payload_invalido") from exc
    if not isinstance(criado, dict):
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_payload_invalido")

    order_id = str(criado.get("id") or "").strip()
    status_criacao = str(criado.get("status") or "").strip()
    pagamento = _primeiro_pagamento(criado)
    metodo = pagamento.get("payment_method") if isinstance(pagamento, dict) else None
    metodo = metodo if isinstance(metodo, dict) else {}
    qr_code_presente = bool(str(metodo.get("qr_code") or "").strip())
    ticket_url_presente = bool(str(metodo.get("ticket_url") or "").strip())
    if not order_id or not qr_code_presente:
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_order_incompleta")

    headers_get = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    try:
        consulta = cliente.get(f"{_BASE_URL}/v1/orders/{order_id}", headers=headers_get, timeout=12.0)
    except requests.RequestException as exc:
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_consulta_transporte") from exc
    consulta_status = int(getattr(consulta, "status_code", 0) or 0)
    if not 200 <= consulta_status < 300:
        raise ErroConfiguracaoServico(f"mercado_pago_pix_sandbox_consulta_http_{consulta_status or 'desconhecido'}")
    try:
        consultado = consulta.json()
    except (ValueError, TypeError) as exc:
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_consulta_payload_invalido") from exc
    if not isinstance(consultado, dict) or str(consultado.get("id") or "").strip() != order_id:
        raise ErroConfiguracaoServico("mercado_pago_pix_sandbox_consulta_divergente")
    status_consulta = str(consultado.get("status") or "").strip()

    evidencia = _evidencia(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        order_id=order_id,
        status=status_consulta or status_criacao,
        agora=agora or datetime.now(timezone.utc),
    )
    return ResultadoPixSandbox(
        order_id=order_id,
        status_criacao=status_criacao,
        status_consulta=status_consulta,
        qr_code_presente=qr_code_presente,
        ticket_url_presente=ticket_url_presente,
        evidencia_ref=evidencia,
    )


def main() -> None:
    load_dotenv()
    settings = load_runtime_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine=engine, commercial=settings.commercial)
    with session_factory() as session:
        resultado = executar_teste_pix_sandbox(
            session=session,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )
    print(
        json.dumps(
            {
                "sandbox": True,
                "order_id": resultado.order_id,
                "status_criacao": resultado.status_criacao,
                "status_consulta": resultado.status_consulta,
                "qr_code_presente": resultado.qr_code_presente,
                "ticket_url_presente": resultado.ticket_url_presente,
                "evidencia_ref": resultado.evidencia_ref,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
