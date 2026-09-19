"""DTOs HTTP do cadastro administrativo original, sem autoridade paralela."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.administracao import EmpresaAdministrativa, UnidadeAdministrativa
from core.seguranca.erros import ErroSeguranca
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime


class EmpresaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome_exibicao: str
    moeda: str
    timezone: str
    ativa: bool
    versao: int


class NovaUnidadeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unidade_id: str
    codigo: str
    nome_fantasia: str
    tipo: str
    endereco: str
    horarios: str


class UnidadeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str
    nome_fantasia: str
    tipo: str
    documento_fiscal: str
    telefone: str
    email: str
    endereco: str
    horarios: str
    ativa: bool
    versao: int


def _empresa_out(empresa: EmpresaAdministrativa) -> dict[str, Any]:
    return {
        "tenant_id": empresa.tenant_id,
        "nome_exibicao": empresa.nome_exibicao,
        "moeda": empresa.moeda,
        "timezone": empresa.timezone,
        "ativa": empresa.ativa,
        "versao": empresa.versao,
    }


def _unidade_out(unidade: UnidadeAdministrativa) -> dict[str, Any]:
    return {
        "unidade_id": unidade.unidade_id,
        "codigo": unidade.codigo,
        "nome_fantasia": unidade.nome_fantasia,
        "tipo": unidade.tipo,
        "documento_fiscal": unidade.documento_fiscal or "",
        "telefone": unidade.telefone or "",
        "email": unidade.email or "",
        "endereco": str(unidade.endereco.get("descricao", "")),
        "horarios": str(unidade.horarios.get("descricao", "")),
        "ativa": unidade.ativa,
        "versao": unidade.versao,
    }


def _descricao(valor: str) -> dict[str, object]:
    # Mesma adaptação dos textareas do formulário Streamlit original.
    return {"descricao": valor.strip()} if valor.strip() else {}


def _erro_cadastro(exc: Exception) -> JSONResponse:
    if isinstance(exc, ErroSeguranca):
        return _tratar_erro(exc)
    if isinstance(exc, RuntimeError) and str(exc) in {
        "empresa_admin_concorrente",
        "unidade_admin_concorrente",
    }:
        return JSONResponse(status_code=409, content={"erro": str(exc)})
    if isinstance(exc, (ValueError, TypeError)):
        return JSONResponse(
            status_code=400, content={"erro": "admin.cadastro_invalido"}
        )
    return _tratar_erro(exc)


def build_admin_empresa_router(
    *, session_factory: Callable[[], Session], auth_runtime: AuthSessionRuntime
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin-empresa"])
    app = AplicacaoAdministracaoProprietarioV1(session_factory)

    @router.get("/empresa", response_model=None)
    def consultar(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_empresa_http_v1.consultar",
            )
            empresa = app.obter_empresa(contexto=contexto)
            unidades = app.listar_unidades(contexto=contexto)
            return {
                "empresa": _empresa_out(empresa),
                "unidades": [_unidade_out(u) for u in unidades],
            }
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_cadastro(exc)

    @router.put("/empresa", response_model=None)
    def atualizar_empresa(
        payload: EmpresaIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_empresa_http_v1.atualizar",
            )
            empresa = app.atualizar_empresa(
                contexto=contexto,
                empresa=EmpresaAdministrativa(
                    tenant_id=contexto.tenant_id, **payload.model_dump()
                ),
                versao_esperada=payload.versao,
            )
            return _empresa_out(empresa)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_cadastro(exc)

    @router.post("/unidades", status_code=201, response_model=None)
    def criar_unidade(
        payload: NovaUnidadeIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_empresa_http_v1.criar_unidade",
            )
            unidade = app.criar_unidade(
                contexto=contexto,
                unidade=UnidadeAdministrativa(
                    tenant_id=contexto.tenant_id,
                    **payload.model_dump(exclude={"endereco", "horarios"}),
                    endereco=_descricao(payload.endereco),
                    horarios=_descricao(payload.horarios),
                ),
            )
            return _unidade_out(unidade)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_cadastro(exc)

    @router.put("/unidades/{unidade_id}", response_model=None)
    def atualizar_unidade(
        unidade_id: str, payload: UnidadeIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_empresa_http_v1.atualizar_unidade",
            )
            unidade = app.atualizar_unidade(
                contexto=contexto,
                unidade=UnidadeAdministrativa(
                    tenant_id=contexto.tenant_id,
                    unidade_id=unidade_id,
                    **payload.model_dump(exclude={"endereco", "horarios"}),
                    endereco=_descricao(payload.endereco),
                    horarios=_descricao(payload.horarios),
                ),
                versao_esperada=payload.versao,
            )
            return _unidade_out(unidade)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_cadastro(exc)

    return router
