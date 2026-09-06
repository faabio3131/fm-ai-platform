"""HTTP ingress mínimo e fail-closed para webhooks financeiros da V1."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from application.assistente_channel_runtime import RuntimeCanalWhatsAppV1
from application.assistente_operational_notifications import (
    notificar_status_assistente_best_effort,
)
from application.finalizacao_pagamento import FinalizacaoPagamentoInvalida
from application.gerente_ia_runtime import PlanejadorLLM, compor_runtime_gerente_ia
from application.gerente_ia_transacoes import (
    configurar_identidade_assistente_v1,
    confirmar_acao_gerente_ia_v1,
    executar_tool_gerente_ia_v1,
    perguntar_gerente_ia_v1,
)
from application.pagbank import (
    PagBankAplicacaoInvalida,
    processar_webhook_pagbank,
)
from application.pdv_legacy_projection import ProjecaoLegadaInvalida
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool
from core.integracoes.modelos import ErroConfiguracaoServico
from core.integracoes.provedores import ErroProvedorExterno
from core.pagamentos.erros import ConflitoIdempotenciaPagamento
from core.pagamentos.pagbank import ErroPagBank
from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.runtime.config import RuntimeSettings
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import (
    ErroSeguranca,
    ReferenciaSegredoInvalida,
    SegredoAusente,
)
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from http_api.auth import build_auth_router
from http_api.kds import build_kds_router
from http_api.pdv import build_pdv_router
from http_api.salao import build_salao_router
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.pagamentos.pagbank_runtime import (
    CredencialPagBankNaoConfigurada,
    PagBankAdapterFactory,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.seguranca.session_guard import build_session_factory

_MAX_WEBHOOK_BYTES = 1024 * 1024


def _json_seguro(valor: Any) -> Any:
    if is_dataclass(valor):
        return _json_seguro(asdict(cast(Any, valor)))
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(chave): _json_seguro(item) for chave, item in valor.items()}
    if isinstance(valor, (tuple, list, frozenset, set)):
        return [_json_seguro(item) for item in valor]
    return valor


def _credenciais_basic(request: Request) -> tuple[str, str]:
    cabecalho = request.headers.get("authorization", "")
    esquema, _, valor = cabecalho.partition(" ")
    if esquema.casefold() != "basic" or not valor:
        raise ValueError("autenticacao_obrigatoria")
    try:
        decodificado = base64.b64decode(valor, validate=True).decode("utf-8")
        email, password = decodificado.split(":", 1)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("autenticacao_invalida") from exc
    return email, password


def _extrair_order_id_nao_confiavel(payload_bruto: bytes) -> str | None:
    """Extrai somente a chave de roteamento; não atribui confiança ao payload."""

    try:
        payload = json.loads(payload_bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    order_id = str(payload.get("id", "")).strip()
    return order_id if order_id.startswith("ORDE_") else None


def build_http_app(
    *,
    settings: RuntimeSettings | None = None,
    engine: Engine | None = None,
    session_factory: Callable[[], Session] | None = None,
    pagbank_factory: PagBankAdapterFactory | None = None,
    secret_store: SecretStore | None = None,
    planejador_llm_factory: Callable[[Session], PlanejadorLLM] | None = None,
    whatsapp_secret_store_factory: Callable[[Session], SecretStore] | None = None,
    whatsapp_runtime: RuntimeCanalWhatsAppV1 | None = None,
) -> FastAPI:
    settings = settings or load_runtime_settings()
    engine = engine or build_engine(settings)
    session_factory = session_factory or build_session_factory(
        engine=engine, commercial=settings.commercial
    )
    pagbank_factory = pagbank_factory or PagBankAdapterFactory()
    secret_store = secret_store or ReferenceSecretStore()
    whatsapp_secret_store_factory = (
        whatsapp_secret_store_factory
        or (lambda session: EncryptedSQLAlchemySecretStore(session))
    )
    canal_whatsapp = whatsapp_runtime or RuntimeCanalWhatsAppV1(session_factory)

    app = FastAPI(
        title="F&M Gerente AI — Integration API",
        version="1.0",
        docs_url=None if settings.commercial else "/docs",
        redoc_url=None,
        openapi_url=None if settings.commercial else "/openapi.json",
    )
    app.include_router(
        build_auth_router(
            session_factory=session_factory,
            settings=settings,
            secret_store=secret_store,
        )
    )
    app.include_router(build_kds_router(session_factory=session_factory))
    app.include_router(build_pdv_router(session_factory=session_factory))
    app.include_router(build_salao_router(session_factory=session_factory))

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> JSONResponse:
        health = check_database_health(engine)
        return JSONResponse(
            status_code=status.HTTP_200_OK if health.ok else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ok": health.ok, "backend": health.backend, "detail": health.detail},
        )

    def _contexto_whatsapp(
        *, tenant_id: str, unidade_id: str, correlation_id: str
    ) -> ContextoExecucao:
        if not tenant_id.strip() or not unidade_id.strip():
            raise ValueError("escopo_whatsapp_invalido")
        return ContextoExecucao.sistema(
            identidade="meta-whatsapp-webhook-v1",
            motivo="webhook Meta/WhatsApp escopado por tenant e unidade",
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            correlation_id=correlation_id,
            solicitado_em=datetime.now(timezone.utc),
        )

    @app.get(
        "/webhooks/meta/whatsapp/{tenant_id}/{unidade_id}",
        include_in_schema=False,
    )
    def verificar_whatsapp(
        tenant_id: str,
        unidade_id: str,
        request: Request,
    ) -> Response:
        mode = request.query_params.get("hub.mode", "")
        verify_token = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")
        if mode != "subscribe" or not verify_token or not challenge:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        try:
            contexto = _contexto_whatsapp(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                correlation_id=request.headers.get("x-correlation-id")
                or f"wa-verify:{tenant_id}:{unidade_id}",
            )
            with session_factory() as session:
                adapter = FabricaAdaptersExternos(
                    session=session,
                    secret_store=whatsapp_secret_store_factory(session),
                ).meta(
                    contexto=contexto,
                    configuracao_id="mensageria.whatsapp--meta",
                    exigir_homologacao=False,
                )
                validado = adapter.validar_desafio(
                    verify_token=verify_token,
                    challenge=challenge,
                )
            return Response(
                content=validado,
                media_type="text/plain",
                status_code=status.HTTP_200_OK,
            )
        except (ErroConfiguracaoServico, ErroProvedorExterno, RuntimeError):
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    @app.post(
        "/webhooks/meta/whatsapp/{tenant_id}/{unidade_id}",
        include_in_schema=False,
    )
    async def webhook_whatsapp(
        tenant_id: str,
        unidade_id: str,
        request: Request,
    ) -> Response:
        payload_bruto = await request.body()
        if len(payload_bruto) > _MAX_WEBHOOK_BYTES:
            return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        assinatura = request.headers.get("x-hub-signature-256", "").strip()
        if not assinatura:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        try:
            contexto = _contexto_whatsapp(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                correlation_id=request.headers.get("x-correlation-id")
                or f"wa:{tenant_id}:{unidade_id}",
            )
            with session_factory() as session:
                adapter = FabricaAdaptersExternos(
                    session=session,
                    secret_store=whatsapp_secret_store_factory(session),
                ).meta(
                    contexto=contexto,
                    configuracao_id="mensageria.whatsapp--meta",
                )
                mensagens = adapter.extrair_mensagens_whatsapp(
                    payload_bruto=payload_bruto,
                    assinatura=assinatura,
                )
                for mensagem in mensagens:
                    canal_whatsapp.processar_mensagem(
                        tenant_id=tenant_id,
                        unidade_id=unidade_id,
                        mensagem=mensagem,
                        adapter=adapter,
                    )
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except ErroProvedorExterno:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        except ErroConfiguracaoServico:
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception:  # noqa: BLE001 - fronteira externa fail-closed
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    @app.post("/webhooks/pagbank", include_in_schema=False)
    async def webhook_pagbank(request: Request) -> Response:
        payload_bruto = await request.body()
        if len(payload_bruto) > _MAX_WEBHOOK_BYTES:
            return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        assinatura = request.headers.get("x-authenticity-token", "").strip()
        if not assinatura:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        order_id = _extrair_order_id_nao_confiavel(payload_bruto)
        if order_id is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        try:
            resultado = processar_webhook_pagbank(
                session_factory=session_factory,
                adapter_factory=pagbank_factory.construir,
                order_id=order_id,
                payload_bruto=payload_bruto,
                assinatura=assinatura,
            )
        except ConflitoIdempotenciaPagamento:
            return Response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except (
            CredencialPagBankNaoConfigurada,
            ReferenciaSegredoInvalida,
            SegredoAusente,
        ):
            return Response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except ErroPagBank:
            return Response(
                status_code=status.HTTP_204_NO_CONTENT
            )
        except (
            PagBankAplicacaoInvalida,
            FinalizacaoPagamentoInvalida,
            ProjecaoLegadaInvalida,
        ):
            return Response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if resultado is None:
            return Response(
                status_code=status.HTTP_204_NO_CONTENT
            )

        contexto_status = ContextoExecucao.sistema(
            identidade="pagbank-status-assistente-v1",
            motivo="notificar mudança financeira já confirmada ao canal do Assistente",
            tenant_id=resultado.pagamento.tenant_id,
            unidade_id=resultado.pagamento.unidade_id,
            correlation_id=resultado.pagamento.correlation_id,
            solicitado_em=datetime.now(timezone.utc),
        )
        notificar_status_assistente_best_effort(
            session_factory=session_factory,
            contexto=contexto_status,
            pedido_id=resultado.pagamento.pedido_id,
        )
        return Response(
            status_code=status.HTTP_204_NO_CONTENT
        )

    def _contexto_autenticado(request: Request, session: Session):
        email, password = _credenciais_basic(request)
        identidade = ServicoAutenticacao(
            RepositorioIdentidadesSQLAlchemy(session)
        ).autenticar(email=email, password=password)
        return identidade.contexto(
            origem="core_http_v1",
            correlation_id=request.headers.get("x-correlation-id") or None,
        )

    async def _payload_json(request: Request) -> dict[str, Any]:
        if int(request.headers.get("content-length", "0") or 0) > _MAX_WEBHOOK_BYTES:
            raise ValueError("payload_excede_limite")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise TypeError("payload_invalido")
        return payload

    def _erro_core(exc: Exception) -> JSONResponse:
        if isinstance(exc, ErroGerenteIA):
            codigo = exc.codigo
            http_status = status.HTTP_403_FORBIDDEN if "permiss" in codigo or "confirmacao" in codigo else status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, (ErroSeguranca, PermissionError)):
            codigo = getattr(exc, "codigo", "seguranca.permissao_insuficiente")
            http_status = status.HTTP_401_UNAUTHORIZED if "credenciais" in str(codigo) else status.HTTP_403_FORBIDDEN
        else:
            codigo = (
                str(exc)
                if isinstance(exc, (TypeError, ValueError))
                else "core.indisponivel"
            )
            http_status = status.HTTP_401_UNAUTHORIZED if "autenticacao" in codigo else status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=http_status, content={"erro": codigo})

    @app.post("/v1/core/tools")
    async def core_tools(request: Request) -> JSONResponse:
        try:
            email, password = _credenciais_basic(request)
            payload = await _payload_json(request)
            argumentos = payload.get("argumentos", {})
            if not isinstance(argumentos, dict):
                raise TypeError("argumentos_invalidos")
            chamada = ChamadaTool.de_dict(
                str(payload.get("tool", "")),
                argumentos,
                request_id=str(payload["request_id"]) if payload.get("request_id") else None,
            )
            resultado = executar_tool_gerente_ia_v1(
                session_factory=session_factory,
                secret_store=secret_store,
                email=email,
                password=password,
                origem="core_http_v1",
                correlation_id=request.headers.get("x-correlation-id") or None,
                chamada=chamada,
                planejador_llm_factory=planejador_llm_factory,
            )
            return JSONResponse(content=_json_seguro(resultado))
        except Exception as exc:  # noqa: BLE001 - fronteira HTTP fail-closed
            return _erro_core(exc)

    @app.post("/v1/core/actions/{preview_id}/confirm")
    async def core_confirmar(preview_id: str, request: Request) -> JSONResponse:
        try:
            email, password = _credenciais_basic(request)
            payload = await _payload_json(request)
            resultado = confirmar_acao_gerente_ia_v1(
                session_factory=session_factory,
                secret_store=secret_store,
                email=email,
                password=password,
                origem="core_http_v1",
                correlation_id=request.headers.get("x-correlation-id") or None,
                preview_id=preview_id,
                fingerprint=str(payload.get("fingerprint", "")),
                idempotency_key=str(payload.get("idempotency_key", "")),
            )
            return JSONResponse(content=_json_seguro(resultado))
        except Exception as exc:  # noqa: BLE001
            return _erro_core(exc)

    @app.get("/v1/core/assistente-atendimento/identidade")
    def obter_identidade_assistente(request: Request) -> JSONResponse:
        with session_factory() as session:
            try:
                contexto = _contexto_autenticado(request, session)
                runtime = compor_runtime_gerente_ia(session=session, secret_store=secret_store)
                identidade = runtime.identidade_assistente.obter(contexto=contexto)
                return JSONResponse(content=_json_seguro(identidade))
            except Exception as exc:  # noqa: BLE001
                return _erro_core(exc)

    @app.put("/v1/core/assistente-atendimento/identidade")
    async def configurar_identidade_assistente(request: Request) -> JSONResponse:
        try:
            email, password = _credenciais_basic(request)
            payload = await _payload_json(request)
            atributos = payload.get("atributos", {})
            if not isinstance(atributos, dict):
                raise TypeError("atributos_assistente_invalidos")
            identidade = configurar_identidade_assistente_v1(
                session_factory=session_factory,
                secret_store=secret_store,
                email=email,
                password=password,
                origem="core_http_v1",
                correlation_id=request.headers.get("x-correlation-id") or None,
                nome_publico=str(payload.get("nome_publico", "")),
                atributos=atributos,
                versao_esperada=(
                    int(payload["versao_esperada"])
                    if payload.get("versao_esperada") is not None
                    else None
                ),
            )
            return JSONResponse(content=_json_seguro(identidade))
        except Exception as exc:  # noqa: BLE001
            return _erro_core(exc)

    @app.post("/v1/core/perguntar")
    async def perguntar_core(request: Request) -> JSONResponse:
        try:
            email, password = _credenciais_basic(request)
            payload = await _payload_json(request)
            identidade, chamada, resultado = perguntar_gerente_ia_v1(
                session_factory=session_factory,
                secret_store=secret_store,
                email=email,
                password=password,
                origem="core_http_v1",
                correlation_id=request.headers.get("x-correlation-id") or None,
                pergunta=str(payload.get("pergunta", "")),
                planejador_llm_factory=planejador_llm_factory,
            )
            return JSONResponse(
                content={
                    "assistente": identidade.nome_publico,
                    "tool": chamada.tool.value,
                    "resultado": _json_seguro(resultado),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_core(exc)

    return app
