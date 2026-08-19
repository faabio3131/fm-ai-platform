"""App temporario de diagnostico sanitizado do HMAC de webhook Mercado Pago.

Executar somente em homologacao local/sandbox. O middleware compara, sem expor
secret nem assinatura, duas formas de manifesto: preservando o case de data.id e
forcando data.id para minusculas. O app real continua processando a requisicao.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import Request
from sqlalchemy import select

from core.runtime import build_engine, load_runtime_settings
from infra.integracoes.mercado_pago_webhook_app import (
    _CONFIG_ID,
    _finalidade,
    _segredo,
    create_app as create_real_app,
)
from infra.integracoes.repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from infra.seguranca.session_guard import build_session_factory

_LOGGER = logging.getLogger("kordena.mercado_pago.webhook.hmac_diagnostico")


def _parse_x_signature(x_signature: str) -> tuple[str, str]:
    partes: dict[str, str] = {}
    for item in x_signature.split(","):
        if "=" not in item:
            continue
        chave, valor = item.split("=", 1)
        partes[chave.strip()] = valor.strip()
    return partes.get("ts", ""), partes.get("v1", "").casefold()


def _match(secret: str, manifesto: str, recebido: str) -> bool:
    esperado = hmac.new(secret.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return bool(recebido) and hmac.compare_digest(esperado, recebido)


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
    async def diagnosticar_hmac(request: Request, call_next):
        if request.url.path != "/webhooks/mercado-pago":
            return await call_next(request)

        data_id = str(request.query_params.get("data.id") or "").strip()
        request_id = str(request.headers.get("x-request-id") or "").strip()
        x_signature = str(request.headers.get("x-signature") or "").strip()
        ts, recebido = _parse_x_signature(x_signature)

        exato = False
        lower = False
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
                    if data_id and request_id and ts and recebido:
                        manifesto_exato = f"id:{data_id};request-id:{request_id};ts:{ts};"
                        manifesto_lower = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
                        exato = _match(secret, manifesto_exato, recebido)
                        lower = _match(secret, manifesto_lower, recebido)
        except Exception:
            _LOGGER.exception("mercado_pago_hmac_diagnostico_falhou")

        _LOGGER.warning(
            "mercado_pago_hmac_diagnostico exact_match=%s lower_match=%s ts_presente=%s v1_presente=%s data_id_len=%d request_id_len=%d",
            exato,
            lower,
            bool(ts),
            bool(recebido),
            len(data_id),
            len(request_id),
        )
        return await call_next(request)

    return app
