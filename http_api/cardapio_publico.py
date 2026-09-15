"""HTTP do Cardapio Digital publico e sua configuracao administrativa V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from application.cardapio_publico import (
    consultar_publicacao as consultar_publicacao_application,
)
from application.cardapio_publico import resolver_cardapio_publico, salvar_publicacao
from core.seguranca.erros import ErroSeguranca
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime
from infra.cardapio_publico.repositorio_sqlalchemy import PublicacaoCardapioPersistida


class PublicacaoCardapioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=3, max_length=120)
    publicada: bool
    versao: int = Field(ge=0)


def _publicacao_out(
    *, unidade_id: str, publicacao: PublicacaoCardapioPersistida | None
) -> dict[str, Any]:
    if publicacao is None:
        return {
            "unidade_id": unidade_id,
            "public_id": None,
            "slug": None,
            "publicada": False,
            "url_publica": None,
            "versao": 0,
        }
    return {
        "unidade_id": unidade_id,
        "public_id": publicacao.public_id,
        "slug": publicacao.slug,
        "publicada": publicacao.publicada,
        "url_publica": f"/cardapio/{publicacao.public_id}/{publicacao.slug}",
        "versao": publicacao.versao,
    }


def _erro_admin(exc: Exception) -> JSONResponse:
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _tratar_erro(exc)
    if isinstance(exc, LookupError):
        return JSONResponse(status_code=404, content={"erro": str(exc)})
    if isinstance(exc, RuntimeError) and "concorrente" in str(exc).casefold():
        return JSONResponse(status_code=409, content={"erro": str(exc)})
    if isinstance(exc, (ValueError, TypeError)):
        return JSONResponse(status_code=400, content={"erro": str(exc)})
    return _tratar_erro(exc)


def build_cardapio_publico_router(
    *, session_factory: Callable[[], Session], auth_runtime: AuthSessionRuntime
) -> APIRouter:
    router = APIRouter(tags=["cardapio-publico"])
    admin = AplicacaoAdministracaoProprietarioV1(session_factory)

    @router.get("/v1/admin/cardapio-publico/{unidade_id}", response_model=None)
    def consultar_publicacao(
        unidade_id: str, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="cardapio_publico_http_v1.consultar",
            )
            escopo = admin.obter_configuracao(
                contexto=contexto,
                unidade_id=unidade_id,
            )
            with session_factory() as session:
                publicacao = consultar_publicacao_application(
                    session=session,
                    tenant_id=escopo.tenant_id,
                    unidade_id=escopo.unidade_id,
                )
            return _publicacao_out(unidade_id=unidade_id, publicacao=publicacao)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_admin(exc)

    @router.put("/v1/admin/cardapio-publico/{unidade_id}", response_model=None)
    def configurar_publicacao(
        unidade_id: str,
        payload: PublicacaoCardapioIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="cardapio_publico_http_v1.configurar",
            )
            escopo = admin.obter_configuracao(
                contexto=contexto,
                unidade_id=unidade_id,
            )
            with session_factory() as session:
                publicacao = salvar_publicacao(
                    session=session,
                    tenant_id=escopo.tenant_id,
                    unidade_id=escopo.unidade_id,
                    slug=payload.slug,
                    publicada=payload.publicada,
                    versao_esperada=payload.versao,
                )
                session.commit()
            return _publicacao_out(unidade_id=unidade_id, publicacao=publicacao)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_admin(exc)

    @router.get("/v1/publico/cardapio/{public_id}", response_model=None)
    def consultar_cardapio(public_id: str) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                cardapio = resolver_cardapio_publico(
                    session=session,
                    public_id=public_id,
                )
            if cardapio is None:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"erro": "cardapio_publico_indisponivel"},
                )
            return {
                "public_id": cardapio.publicacao.public_id,
                "slug": cardapio.publicacao.slug,
                "empresa": cardapio.nome_empresa,
                "unidade": cardapio.nome_unidade,
                "tipo_unidade": cardapio.tipo_unidade,
                "itens": [
                    {
                        "produto_id": produto.produto_id,
                        "nome": produto.nome,
                        "preco": str(produto.preco),
                        "estoque_disponivel": str(produto.estoque_disponivel),
                        "versao": produto.versao,
                    }
                    for produto in cardapio.catalogo
                ],
            }
        except Exception:  # noqa: BLE001 - superficie publica nao vaza detalhes internos
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"erro": "cardapio_publico_indisponivel"},
            )

    return router
