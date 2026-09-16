"""Adaptador HTTP session-aware do Gerente IA V1 para a Web."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from application.gerente_ia_web import AplicacaoGerenteIAWebV1
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from http_api.auth import AuthSessionRuntime


class PerguntaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pergunta: str = Field(min_length=1, max_length=4000)


class ToolIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(min_length=1, max_length=80)
    argumentos: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, max_length=192)


class ConfirmacaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=1, max_length=192)
    fingerprint: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=192)


def _jsonavel(valor: Any) -> Any:
    if is_dataclass(valor) and not isinstance(valor, type):
        return _jsonavel(asdict(valor))
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, Mapping):
        return {str(chave): _jsonavel(item) for chave, item in valor.items()}
    if isinstance(valor, (tuple, list, set, frozenset)):
        return [_jsonavel(item) for item in valor]
    if isinstance(valor, (str, int, float, bool, type(None))):
        return valor
    return str(valor)


def _erro(status_code: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"erro": codigo})


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(401, "credenciais_invalidas")
    if isinstance(exc, ErroGerenteIA):
        codigo = exc.codigo
        if codigo in {
            "fingerprint_divergente",
            "conflito_idempotencia",
            "preview_ja_consumido",
            "preview_expirado",
        }:
            return _erro(409, codigo)
        if "permiss" in codigo or "confirmacao_humana" in codigo:
            return _erro(403, codigo)
        if codigo == "recurso_indisponivel":
            return _erro(404, codigo)
        return _erro(400, codigo)
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(403, str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")))
    if isinstance(exc, (ValueError, TypeError)):
        return _erro(400, "gerente_ia.requisicao_invalida")
    return _erro(503, "gerente_ia.indisponivel")


def _contexto(
    request: Request,
    *,
    auth_runtime: AuthSessionRuntime,
    permissao: Permissao,
) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if permissao not in identidade.permissoes:
        raise PermissionError("seguranca.gerente_ia_permissao_exigida")
    return identidade.contexto(
        origem="gerente_ia_web_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _resultado(tipo: str, valor: Any, **extras: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"tipo": tipo, "resultado": _jsonavel(valor)}
    payload.update({chave: _jsonavel(item) for chave, item in extras.items()})
    return payload


def build_gerente_ia_web_router(
    *,
    session_factory: Callable[[], Session],
    auth_runtime: AuthSessionRuntime,
    secret_store: SecretStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/gerente-ia", tags=["gerente-ia-web"])
    app = AplicacaoGerenteIAWebV1(session_factory, secret_store=secret_store)

    @router.post("/perguntar", response_model=None)
    def perguntar(payload: PerguntaIn, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(
                request,
                auth_runtime=auth_runtime,
                permissao=Permissao.GERENTE_IA_CONSULTAR,
            )
            identidade, chamada, resultado = app.perguntar(
                contexto=contexto,
                pergunta=payload.pergunta,
            )
            return _resultado(
                type(resultado).__name__,
                resultado,
                nome_assistente=identidade.nome_publico,
                chamada=chamada,
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/tools", response_model=None)
    def executar_tool(payload: ToolIn, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(
                request,
                auth_runtime=auth_runtime,
                permissao=Permissao.GERENTE_IA_CONSULTAR,
            )
            chamada = ChamadaTool.de_dict(
                payload.tool,
                payload.argumentos,
                request_id=payload.request_id,
            )
            resultado = app.executar_tool(contexto=contexto, chamada=chamada)
            return _resultado(type(resultado).__name__, resultado, chamada=chamada)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/confirmar", response_model=None)
    def confirmar(payload: ConfirmacaoIn, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(
                request,
                auth_runtime=auth_runtime,
                permissao=Permissao.GERENTE_IA_EXECUTAR_ACAO,
            )
            resultado = app.confirmar_acao(
                contexto=contexto,
                preview_id=payload.preview_id,
                fingerprint=payload.fingerprint,
                idempotency_key=payload.idempotency_key,
            )
            return _resultado(type(resultado).__name__, resultado)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    return router
