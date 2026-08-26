"""Diagnostico sandbox: compara o HMAC da Kordena com o validador oficial Mercado Pago.

Uso temporario em homologacao local. Nao registra secret, assinatura, request-id,
data.id ou timestamp em claro. O SDK oficial e dependencia apenas deste
procedimento diagnostico; o runtime comercial permanece inalterado.
"""

from __future__ import annotations

import hmac
import logging
from importlib import metadata
from typing import Any

from core.runtime import build_engine, load_runtime_settings
from fastapi import Request
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.session_guard import build_session_factory

from infra.integracoes.mercado_pago_webhook_app import (
    _CONFIG_ID,
    _finalidade,
    _segredo,
)
from infra.integracoes.mercado_pago_webhook_app import (
    create_app as create_real_app,
)
from scripts.mercado_pago_webhook_hmac_diagnostico_app import (
    _hmac_hex,
    _origem_payload,
    _parse_x_signature,
)

_LOGGER = logging.getLogger("kordena.mercado_pago.webhook.sdk_diagnostico")


def _versao_sdk() -> str:
    try:
        return metadata.version("mercadopago")
    except metadata.PackageNotFoundError:
        return "nao-instalado"


def _validar_sdk_oficial(
    *,
    x_signature: str,
    x_request_id: str,
    data_id: str,
    secret: str,
    validator_cls: Any | None = None,
) -> tuple[bool | None, str]:
    """Retorna apenas resultado/motivo sanitizado; nunca propaga valores sensiveis."""
    if validator_cls is None:
        try:
            from mercadopago.webhook.validator import (  # type: ignore[import-not-found]
                InvalidWebhookSignatureError,
                WebhookSignatureValidator,
            )
        except ImportError:
            return None, "sdk_nao_instalado"
        validator_cls = WebhookSignatureValidator
        invalid_error_cls = InvalidWebhookSignatureError
    else:
        invalid_error_cls = getattr(validator_cls, "InvalidWebhookSignatureError", Exception)

    try:
        validator_cls.validate(
            x_signature,
            x_request_id,
            data_id,
            secret,
            tolerance_seconds=None,
        )
        return True, "ok"
    except invalid_error_cls as exc:
        reason = getattr(getattr(exc, "reason", None), "value", None)
        return False, str(reason or "assinatura_invalida")
    except Exception as exc:  # noqa: BLE001 - fronteira diagnostica sanitiza o erro
        return False, f"erro_{type(exc).__name__}"


def _validar_kordena(*, data_id: str, request_id: str, ts: str, recebido: str, secret: str) -> bool:
    if not all((data_id, request_id, ts, recebido, secret)):
        return False
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    return hmac.compare_digest(_hmac_hex(secret, manifesto), recebido)


def create_app():
    settings = load_runtime_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine=engine, commercial=settings.commercial)
    app = create_real_app(
        session_factory=session_factory,
        tenant_id=settings.tenant_id,
        unidade_id=settings.unidade_id,
    )

    @app.middleware("http")
    async def comparar_sdk(request: Request, call_next):
        if request.url.path != "/webhooks/mercado-pago":
            return await call_next(request)

        data_id = str(request.query_params.get("data.id") or "").strip()
        request_id = str(request.headers.get("x-request-id") or "").strip()
        x_signature = str(request.headers.get("x-signature") or "").strip()
        ts, recebido, _, _, _ = _parse_x_signature(x_signature)
        payload_bruto = await request.body()
        application_id, live_mode, body_query_match, tipo = _origem_payload(payload_bruto, data_id)

        sdk_valido: bool | None = None
        sdk_motivo = "configuracao_indisponivel"
        kordena_valido = False
        try:
            with session_factory() as session:
                config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
                    tenant_id=settings.tenant_id,
                    unidade_id=settings.unidade_id,
                    configuracao_id=_CONFIG_ID,
                )
                if config is not None:
                    secret = _segredo(
                        session,
                        tenant_id=settings.tenant_id,
                        unidade_id=settings.unidade_id,
                        finalidade=_finalidade(config, "webhook_secret"),
                    )
                    kordena_valido = _validar_kordena(
                        data_id=data_id,
                        request_id=request_id,
                        ts=ts,
                        recebido=recebido,
                        secret=secret,
                    )
                    sdk_valido, sdk_motivo = _validar_sdk_oficial(
                        x_signature=x_signature,
                        x_request_id=request_id,
                        data_id=data_id,
                        secret=secret,
                    )
        except Exception:
            _LOGGER.exception("mercado_pago_sdk_diagnostico_falhou")

        _LOGGER.warning(
            "mercado_pago_sdk_diagnostico sdk_versao=%s sdk_valido=%s sdk_motivo=%s kordena_valido=%s "
            "application_id=%s live_mode=%s tipo=%s body_query_match=%s",
            _versao_sdk(),
            sdk_valido,
            sdk_motivo,
            kordena_valido,
            application_id,
            live_mode,
            tipo,
            body_query_match,
        )
        return await call_next(request)

    return app
