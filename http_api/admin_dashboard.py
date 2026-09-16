"""Adaptador HTTP fino para o painel executivo administrativo da V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from application.administracao_proprietario import (
    AplicacaoAdministracaoProprietarioV1,
)
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(status.HTTP_401_UNAUTHORIZED, "credenciais_invalidas")
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(
            status.HTTP_403_FORBIDDEN,
            str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")),
        )
    if isinstance(exc, LookupError):
        return _erro(status.HTTP_404_NOT_FOUND, str(exc) or "admin.nao_encontrado")
    return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "admin.painel_indisponivel")


def _painel_out(painel: Any) -> dict[str, Any]:
    financeiro = painel.financeiro
    operacional = painel.operacional
    return {
        "tenant_id": painel.tenant_id,
        "unidades": list(painel.unidades),
        "financeiro": {
            "vendas_reconhecidas": str(financeiro.vendas_reconhecidas),
            "quantidade_vendas": financeiro.quantidade_vendas,
            "ticket_medio": str(financeiro.ticket_medio),
            "pagamentos_pagos": str(financeiro.pagamentos_pagos),
            "pagamentos_pendentes": str(financeiro.pagamentos_pendentes),
            "pagamentos_estornados": str(financeiro.pagamentos_estornados),
            "recebido_dinheiro": str(financeiro.recebido_dinheiro),
            "cmv_estimado_atual": (
                str(financeiro.cmv_estimado_atual)
                if financeiro.cmv_estimado_atual is not None
                else None
            ),
            "margem_estimada_atual": (
                str(financeiro.margem_estimada_atual)
                if financeiro.margem_estimada_atual is not None
                else None
            ),
            "cobertura_cmv_itens_pct": str(financeiro.cobertura_cmv_itens_pct),
        },
        "operacional": {
            "pedidos": operacional.pedidos,
            "estoque_fisico_total": str(operacional.estoque_fisico_total),
            "estoque_reservado_total": str(operacional.estoque_reservado_total),
            "entregas_por_status": [
                {"status": item_status, "quantidade": quantidade}
                for item_status, quantidade in operacional.entregas_por_status
            ],
            "integracoes_configuradas": operacional.integracoes_configuradas,
            "integracoes_homologadas": operacional.integracoes_homologadas,
            "usuarios_ativos": operacional.usuarios_ativos,
        },
    }


def build_admin_dashboard_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin-dashboard"])

    @router.get("/painel-executivo", response_model=None)
    def obter_painel_executivo(
        request: Request,
        unidade_id: Annotated[list[str] | None, Query()] = None,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = obter_identidade_operacional(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                ).identidade
            if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
                raise PermissionError("administracao_sem_acesso")
            if Permissao.FINANCEIRO_VISUALIZAR not in identidade.permissoes:
                raise PermissionError(
                    "administracao_sem_permissao:financeiro.visualizar"
                )
            unidades = tuple(unidade_id or (identidade.unidade_id,))
            painel = AplicacaoAdministracaoProprietarioV1(
                session_factory
            ).painel_executivo(
                contexto=identidade.contexto(
                    origem="admin_dashboard_http_v1.painel_executivo",
                    correlation_id=request.headers.get("x-correlation-id") or None,
                ),
                unidades=unidades,
            )
            return _painel_out(painel)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    return router
