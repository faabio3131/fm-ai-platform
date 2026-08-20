"""App temporario de diagnostico sanitizado do HMAC de webhook Mercado Pago.

Executar somente em homologacao local/sandbox. O middleware testa variantes
estruturais do manifesto HMAC e identifica a origem logica da notificacao sem
expor secret, assinatura, HMAC calculado, request-id ou timestamp. O app real
continua processando a requisicao.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Mapping

from fastapi import Request

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


def _variantes_manifesto(*, data_id: str, request_id: str, ts: str) -> Mapping[str, str]:
    """Variantes somente para diagnostico; nao altera a regra comercial do adapter."""
    ids = {
        "exact": data_id,
        "lower": data_id.lower(),
    }
    variantes: dict[str, str] = {}
    for nome_id, valor_id in ids.items():
        variantes[f"full_{nome_id}"] = (
            f"id:{valor_id};request-id:{request_id};ts:{ts};"
        )
        variantes[f"id_ts_{nome_id}"] = f"id:{valor_id};ts:{ts};"
        variantes[f"id_request_{nome_id}"] = (
            f"id:{valor_id};request-id:{request_id};"
        )
        variantes[f"id_only_{nome_id}"] = f"id:{valor_id};"
    variantes["request_ts"] = f"request-id:{request_id};ts:{ts};"
    variantes["request_only"] = f"request-id:{request_id};"
    variantes["ts_only"] = f"ts:{ts};"
    return variantes


def _diagnosticar_variantes(
    *, secret: str, data_id: str, request_id: str, ts: str, recebido: str
) -> tuple[str, ...]:
    if not all((secret, data_id, request_id, ts, recebido)):
        return ()
    return tuple(
        nome
        for nome, manifesto in _variantes_manifesto(
            data_id=data_id,
            request_id=request_id,
            ts=ts,
        ).items()
        if _match(secret, manifesto, recebido)
    )


def _origem_payload(payload_bruto: bytes, data_id_query: str) -> tuple[str, str, bool, str]:
    """Extrai apenas metadados nao secretos relevantes para identificar a origem."""
    try:
        payload = json.loads(payload_bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "ausente", "desconhecido", False, "desconhecido"
    if not isinstance(payload, Mapping):
        return "ausente", "desconhecido", False, "desconhecido"

    application_id = str(payload.get("application_id") or "ausente").strip() or "ausente"
    live_mode = str(payload.get("live_mode")).lower() if "live_mode" in payload else "desconhecido"
    tipo = str(payload.get("type") or "desconhecido").strip() or "desconhecido"
    data = payload.get("data")
    body_data_id = ""
    if isinstance(data, Mapping):
        body_data_id = str(data.get("id") or "").strip()
    body_query_match = bool(body_data_id) and body_data_id == data_id_query
    return application_id, live_mode, body_query_match, tipo


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
        payload_bruto = await request.body()
        application_id, live_mode, body_query_match, tipo = _origem_payload(
            payload_bruto, data_id
        )

        matches: tuple[str, ...] = ()
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
                    matches = _diagnosticar_variantes(
                        secret=secret,
                        data_id=data_id,
                        request_id=request_id,
                        ts=ts,
                        recebido=recebido,
                    )
        except Exception:
            _LOGGER.exception("mercado_pago_hmac_diagnostico_falhou")

        _LOGGER.warning(
            "mercado_pago_hmac_diagnostico matches=%s application_id=%s live_mode=%s tipo=%s body_query_match=%s ts_presente=%s v1_presente=%s data_id_len=%d request_id_len=%d",
            ",".join(matches) if matches else "nenhuma",
            application_id,
            live_mode,
            tipo,
            body_query_match,
            bool(ts),
            bool(recebido),
            len(data_id),
            len(request_id),
        )
        return await call_next(request)

    return app
