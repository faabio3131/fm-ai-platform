"""Endpoint HTTP do webhook Mercado Pago Orders para Pix da V1.

Executar como sidecar HTTP, separado do Streamlit:

    python -m uvicorn infra.integracoes.mercado_pago_webhook_app:create_app \
        --factory --host 127.0.0.1 --port 8766

Em homologacao local, publique a porta 8766 por um tunel HTTPS confiavel e use
``/webhooks/mercado-pago`` como URL de teste no painel do Mercado Pago.

O endpoint nunca recebe tenant/unidade pela internet: o escopo vem do runtime do
servidor. A notificacao so e aceita depois da assinatura HMAC ser validada com a
secret armazenada no cofre. Uma Order assinada sem vinculo local e reconhecida e
ignorada com seguranca; somente Orders vinculadas a uma cobranca Pix local sao
consultadas autenticadamente antes de qualquer liquidacao financeira.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.provedores import (
    ConfiguracaoMercadoPago,
    ErroProvedorExterno,
    MercadoPagoAdapter,
)
from core.pagamentos.modelos import MetodoPagamento, TipoTransacao
from core.pagamentos.modelos_orm import TransacaoPagamentoORM
from core.runtime import build_engine, load_runtime_settings
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes.pix_durabilidade import confirmar_cobranca_pix_consultada
from infra.integracoes.pix_runtime import CobrancaPixRuntime
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.integracoes.transportes import RequestsProviderTransport
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.seguranca.session_guard import build_session_factory

_CONFIG_ID = "pagamentos.pix--mercado_pago"
_LOGGER = logging.getLogger("kordena.mercado_pago.webhook")


def _finalidade(config, papel: str) -> str:
    finalidade = str(config.credenciais.get(papel) or "").strip()
    if not finalidade:
        raise RuntimeError("credencial Mercado Pago incompleta")
    return finalidade


def _segredo(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    finalidade: str,
) -> str:
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
        raise RuntimeError("credencial Mercado Pago indisponivel")
    store = EncryptedSQLAlchemySecretStore(session)
    return store.resolve(row.referencia).reveal()


def _adapter_pre_homologacao(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
) -> MercadoPagoAdapter:
    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        configuracao_id=_CONFIG_ID,
    )
    if config is None or not config.habilitada:
        raise RuntimeError("integracao Mercado Pago indisponivel")
    if (config.servico, config.provedor) != ("pagamentos.pix", "mercado_pago"):
        raise RuntimeError("integracao Mercado Pago incompativel")
    notification_url = str(config.parametros.get("notification_url") or "").strip()
    if not notification_url.startswith("https://"):
        raise RuntimeError("URL HTTPS Mercado Pago ainda nao configurada")
    access_token = _segredo(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        finalidade=_finalidade(config, "access_token"),
    )
    webhook_secret = _segredo(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        finalidade=_finalidade(config, "webhook_secret"),
    )
    return MercadoPagoAdapter(
        configuracao=ConfiguracaoMercadoPago(
            access_token=access_token,
            webhook_secret=webhook_secret,
            notification_url=notification_url,
        ),
        http=RequestsProviderTransport(),
    )


def _vinculo_por_order(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    order_id: str,
) -> TransacaoPagamentoORM | None:
    return session.scalar(
        select(TransacaoPagamentoORM)
        .where(
            TransacaoPagamentoORM.tenant_id == tenant_id,
            TransacaoPagamentoORM.unidade_id == unidade_id,
            TransacaoPagamentoORM.provedor == "mercado_pago",
            TransacaoPagamentoORM.metodo == MetodoPagamento.PIX.value,
            TransacaoPagamentoORM.tipo == TipoTransacao.INICIACAO.value,
            TransacaoPagamentoORM.id_externo == order_id,
        )
        .order_by(TransacaoPagamentoORM.occurred_at.desc())
        .limit(1)
    )


def _contexto_sistema(*, tenant_id: str, unidade_id: str, request_id: str) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="mercado-pago-webhook",
        motivo="reconciliar notificacao assinada de order Pix",
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        correlation_id=request_id or uuid4().hex,
        solicitado_em=datetime.now(timezone.utc),
    )


def _json_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HTTPException(status_code=400, detail="notificacao invalida")
    return value


def create_app(
    *,
    session_factory: Callable[[], Session] | None = None,
    tenant_id: str | None = None,
    unidade_id: str | None = None,
) -> FastAPI:
    """Cria app HTTP. Dependencias opcionais permitem testes sem I/O real."""

    resolved_session_factory: Callable[[], Session]
    if session_factory is None:
        settings = load_runtime_settings()
        engine = build_engine(settings)
        resolved_session_factory = build_session_factory(
            engine=engine,
            commercial=settings.commercial,
        )
        tenant_id = settings.tenant_id
        unidade_id = settings.unidade_id
    else:
        resolved_session_factory = session_factory
    tenant = str(tenant_id or "").strip()
    unidade = str(unidade_id or "").strip()
    if not tenant or not unidade:
        raise RuntimeError("escopo tenant/unidade ausente para webhook Mercado Pago")

    app = FastAPI(title="Kordena Mercado Pago Webhook", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/mercado-pago")
    async def webhook(request: Request) -> dict[str, object]:
        data_id = str(request.query_params.get("data.id") or "").strip()
        request_id = str(request.headers.get("x-request-id") or "").strip()
        assinatura = str(request.headers.get("x-signature") or "").strip()
        if not data_id or not request_id or not assinatura:
            _LOGGER.warning(
                "mercado_pago_webhook_incompleto data_id=%s request_id_presente=%s assinatura_presente=%s",
                bool(data_id),
                bool(request_id),
                bool(assinatura),
            )
            raise HTTPException(status_code=400, detail="notificacao incompleta")
        try:
            payload = _json_mapping(await request.json())
        except HTTPException:
            raise
        except Exception as exc:
            _LOGGER.warning("mercado_pago_webhook_payload_invalido")
            raise HTTPException(status_code=400, detail="notificacao invalida") from exc

        with resolved_session_factory() as session:
            try:
                adapter = _adapter_pre_homologacao(
                    session,
                    tenant_id=tenant,
                    unidade_id=unidade,
                )
                evento = adapter.normalizar_webhook(
                    payload=payload,
                    data_id=data_id,
                    request_id=request_id,
                    x_signature=assinatura,
                )
                vinculo = _vinculo_por_order(
                    session,
                    tenant_id=tenant,
                    unidade_id=unidade,
                    order_id=evento.recurso_id,
                )
                if vinculo is None:
                    return {
                        "accepted": True,
                        "resource": "order",
                        "reconciled": False,
                    }

                order = adapter.consultar_pagamento(evento.recurso_id)
                contexto = _contexto_sistema(
                    tenant_id=tenant,
                    unidade_id=unidade,
                    request_id=request_id,
                )
                resultado = confirmar_cobranca_pix_consultada(
                    session=session,
                    contexto=contexto,
                    pagamento_id=vinculo.pagamento_id,
                    cobranca=CobrancaPixRuntime(
                        provedor="mercado_pago",
                        id_externo=order.pagamento_id,
                        status=order.status,
                        valor=order.valor,
                        pix_copia_cola=order.pix_copia_cola,
                        qr_code_url=order.ticket_url,
                        qr_code_base64=order.qr_code_base64,
                    ),
                )
                return {
                    "accepted": True,
                    "resource": "order",
                    "reconciled": resultado is not None,
                }
            except ErroProvedorExterno as exc:
                session.rollback()
                _LOGGER.warning(
                    "mercado_pago_webhook_rejeitado motivo=%s data_id_len=%d request_id_len=%d",
                    str(exc),
                    len(data_id),
                    len(request_id),
                )
                raise HTTPException(status_code=400, detail="notificacao rejeitada") from exc
            except RuntimeError as exc:
                session.rollback()
                _LOGGER.warning("mercado_pago_webhook_configuracao_incompleta motivo=%s", str(exc))
                raise HTTPException(status_code=503, detail="webhook ainda nao configurado") from exc
            except Exception:
                session.rollback()
                _LOGGER.exception("mercado_pago_webhook_falha_segura")
                raise HTTPException(status_code=500, detail="falha segura no webhook")

    return app
