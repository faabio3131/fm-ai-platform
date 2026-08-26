"""App temporario de diagnostico sanitizado do HMAC de webhook Mercado Pago.

Executar somente em homologacao local/sandbox. O middleware testa variantes
estruturais do manifesto HMAC e registra fingerprints curtos/irreversiveis das
partes recebidas e calculadas, sem expor secret, assinatura, HMAC completo,
request-id, data.id ou timestamp. O app real continua processando a requisicao.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Mapping

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

_LOGGER = logging.getLogger("kordena.mercado_pago.webhook.hmac_diagnostico")


def _fp(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:12] if valor else "ausente"


def _hmac_hex(secret: str, manifesto: str) -> str:
    return hmac.new(secret.encode(), manifesto.encode(), hashlib.sha256).hexdigest()


def _parse_x_signature(x_signature: str) -> tuple[str, str, tuple[str, ...], int, int]:
    partes: dict[str, str] = {}
    chaves: list[str] = []
    ts_count = 0
    v1_count = 0
    for item in x_signature.split(","):
        if "=" not in item:
            continue
        chave, valor = item.split("=", 1)
        chave = chave.strip()
        valor = valor.strip()
        chaves.append(chave)
        if chave == "ts":
            ts_count += 1
        if chave == "v1":
            v1_count += 1
        partes[chave] = valor
    return (
        partes.get("ts", ""),
        partes.get("v1", "").casefold(),
        tuple(chaves),
        ts_count,
        v1_count,
    )


def _match(secret: str, manifesto: str, recebido: str) -> bool:
    return bool(recebido) and hmac.compare_digest(_hmac_hex(secret, manifesto), recebido)


def _variantes_manifesto(*, data_id: str, request_id: str, ts: str) -> Mapping[str, str]:
    """Variantes somente para diagnostico; nao altera a regra comercial do adapter."""
    ids = {
        "exact": data_id,
        "lower": data_id.lower(),
    }
    requests = {
        "exact": request_id,
        "lower": request_id.lower(),
        "upper": request_id.upper(),
    }
    variantes: dict[str, str] = {}
    for nome_id, valor_id in ids.items():
        for nome_req, valor_req in requests.items():
            variantes[f"full_{nome_id}_{nome_req}"] = (
                f"id:{valor_id};request-id:{valor_req};ts:{ts};"
            )
        variantes[f"id_ts_{nome_id}"] = f"id:{valor_id};ts:{ts};"
        variantes[f"id_request_{nome_id}"] = (
            f"id:{valor_id};request-id:{request_id};"
        )
        variantes[f"id_only_{nome_id}"] = f"id:{valor_id};"
    variantes["request_ts"] = f"request-id:{request_id};ts:{ts};"
    variantes["request_only"] = f"request-id:{request_id};"
    variantes["ts_only"] = f"ts:{ts};"
    variantes["space_lower_no_semicolon"] = (
        f"id:{data_id.lower()} request-id:{request_id} ts:{ts}"
    )
    variantes["space_exact_no_semicolon"] = (
        f"id:{data_id} request-id:{request_id} ts:{ts}"
    )
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


def _estrutura_hmac(
    *, secret: str, data_id: str, request_id: str, ts: str, recebido: str
) -> dict[str, object]:
    manifesto_exato = f"id:{data_id};request-id:{request_id};ts:{ts};"
    manifesto_lower = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
    manifesto_space_lower = f"id:{data_id.lower()} request-id:{request_id} ts:{ts}"
    esperado_exato = _hmac_hex(secret, manifesto_exato) if all((secret, data_id, request_id, ts)) else ""
    esperado_lower = _hmac_hex(secret, manifesto_lower) if all((secret, data_id, request_id, ts)) else ""
    esperado_space_lower = _hmac_hex(secret, manifesto_space_lower) if all((secret, data_id, request_id, ts)) else ""
    return {
        "data_id_fp": _fp(data_id),
        "request_id_fp": _fp(request_id),
        "ts_fp": _fp(ts),
        "v1_recebido_fp": _fp(recebido),
        "hmac_exato_fp": _fp(esperado_exato),
        "hmac_lower_fp": _fp(esperado_lower),
        "hmac_space_lower_fp": _fp(esperado_space_lower),
        "space_lower_match": bool(recebido) and hmac.compare_digest(esperado_space_lower, recebido),
        "manifesto_exato_fp": _fp(manifesto_exato) if all((data_id, request_id, ts)) else "ausente",
        "manifesto_space_lower_fp": _fp(manifesto_space_lower) if all((data_id, request_id, ts)) else "ausente",
        "ts_len": len(ts),
        "ts_so_digitos": ts.isdigit(),
        "v1_len": len(recebido),
        "v1_hex": bool(recebido) and all(c in "0123456789abcdef" for c in recebido),
    }


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

        data_id_raw = str(request.query_params.get("data.id") or "")
        request_id_raw = str(request.headers.get("x-request-id") or "")
        x_signature_raw = str(request.headers.get("x-signature") or "")
        data_id = data_id_raw.strip()
        request_id = request_id_raw.strip()
        x_signature = x_signature_raw.strip()
        ts, recebido, chaves, ts_count, v1_count = _parse_x_signature(x_signature)
        payload_bruto = await request.body()
        application_id, live_mode, body_query_match, tipo = _origem_payload(
            payload_bruto, data_id
        )

        matches: tuple[str, ...] = ()
        estrutura: dict[str, object] = {
            "data_id_fp": _fp(data_id),
            "request_id_fp": _fp(request_id),
            "ts_fp": _fp(ts),
            "v1_recebido_fp": _fp(recebido),
            "hmac_exato_fp": "indisponivel",
            "hmac_lower_fp": "indisponivel",
            "hmac_space_lower_fp": "indisponivel",
            "space_lower_match": False,
            "manifesto_exato_fp": "indisponivel",
            "manifesto_space_lower_fp": "indisponivel",
            "ts_len": len(ts),
            "ts_so_digitos": ts.isdigit(),
            "v1_len": len(recebido),
            "v1_hex": bool(recebido) and all(c in "0123456789abcdef" for c in recebido),
        }
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
                    estrutura = _estrutura_hmac(
                        secret=secret,
                        data_id=data_id,
                        request_id=request_id,
                        ts=ts,
                        recebido=recebido,
                    )
        except Exception:
            _LOGGER.exception("mercado_pago_hmac_diagnostico_falhou")

        _LOGGER.warning(
            "mercado_pago_hmac_diagnostico matches=%s application_id=%s live_mode=%s tipo=%s body_query_match=%s "
            "sig_keys=%s sig_parts=%d ts_count=%d v1_count=%d raw_sig_len=%d raw_sig_fp=%s "
            "data_id_trim=%s request_id_trim=%s data_id_fp=%s request_id_fp=%s ts_fp=%s "
            "v1_recebido_fp=%s hmac_exato_fp=%s hmac_lower_fp=%s hmac_space_lower_fp=%s space_lower_match=%s "
            "manifesto_exato_fp=%s manifesto_space_lower_fp=%s ts_len=%d ts_so_digitos=%s v1_len=%d v1_hex=%s",
            ",".join(matches) if matches else "nenhuma",
            application_id,
            live_mode,
            tipo,
            body_query_match,
            ",".join(chaves) if chaves else "nenhuma",
            len(chaves),
            ts_count,
            v1_count,
            len(x_signature_raw),
            _fp(x_signature_raw),
            data_id_raw != data_id,
            request_id_raw != request_id,
            estrutura["data_id_fp"],
            estrutura["request_id_fp"],
            estrutura["ts_fp"],
            estrutura["v1_recebido_fp"],
            estrutura["hmac_exato_fp"],
            estrutura["hmac_lower_fp"],
            estrutura["hmac_space_lower_fp"],
            estrutura["space_lower_match"],
            estrutura["manifesto_exato_fp"],
            estrutura["manifesto_space_lower_fp"],
            estrutura["ts_len"],
            estrutura["ts_so_digitos"],
            estrutura["v1_len"],
            estrutura["v1_hex"],
        )
        return await call_next(request)

    return app

