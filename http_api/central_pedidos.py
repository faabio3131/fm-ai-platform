"""Adaptador HTTP fino para a Central de Pedidos canônica V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.central_pedidos_transacoes import AplicacaoCentralPedidosTransacoesV1
from core.central_pedidos import CentralPedidosSQLAlchemy, FiltroCentralPedidos
from core.dominio.erros import (
    ConflitoIdempotencia,
    PermissaoNegada,
    RecursoNaoEncontrado,
)
from core.estados.maquinas import ErroTransicao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 96


class CentralFinanceiroOut(BaseModel):
    situacao: str
    valor_previsto: str
    valor_pago: str
    pagamento_ids: list[str]
    venda_financeira_id: str | None
    venda_legada_id: str | None
    reconciliacao_id: str | None
    reconciliacao_status: str | None


class CentralPedidoResumoOut(BaseModel):
    pedido_id: str
    canal: str
    status: str
    criado_em: datetime
    atualizado_em: datetime
    total: str
    quantidade_itens: int
    cliente_id: str | None
    financeiro: CentralFinanceiroOut
    possui_alerta: bool
    origem: str
    versao: int


class CentralPedidosPaginaOut(BaseModel):
    itens: list[CentralPedidoResumoOut]
    pagina: int
    tamanho_pagina: int
    total: int


class CentralItemOut(BaseModel):
    item_id: str
    nome: str
    quantidade: int
    preco_unitario: str
    subtotal: str
    observacao: str | None
    adicionais: list[tuple[str, int, str, str]]


class CentralEventoOut(BaseModel):
    evento_id: str
    tipo: str
    ocorrido_em: datetime
    versao: int
    correlation_id: str


class CentralAlertaOut(BaseModel):
    tipo: str
    severidade: str
    mensagem: str


class CentralPedidoDetalheOut(BaseModel):
    resumo: CentralPedidoResumoOut
    subtotal: str
    descontos: str
    taxas: str
    itens: list[CentralItemOut]
    observacoes: list[str]
    timeline: list[CentralEventoOut]
    financeiro: CentralFinanceiroOut
    alertas: list[CentralAlertaOut]


class CentralEnviarConfirmacaoIn(BaseModel):
    versao_esperada: int = Field(ge=1)


class CentralCancelarIn(BaseModel):
    versao_esperada: int = Field(ge=1)
    motivo: str = Field(min_length=1, max_length=500)


class CentralTransicaoOut(BaseModel):
    pedido_id: str
    status: str
    versao: int
    idempotente: bool
    correlation_id: str


def _contexto_central(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> ContextoExecucao:
    identidade = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    ).identidade
    return identidade.contexto(
        origem="central_pedidos_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _financeiro_out(financeiro: Any) -> dict[str, Any]:
    return {
        "situacao": financeiro.situacao,
        "valor_previsto": str(financeiro.valor_previsto),
        "valor_pago": str(financeiro.valor_pago),
        "pagamento_ids": list(financeiro.pagamento_ids),
        "venda_financeira_id": financeiro.venda_financeira_id,
        "venda_legada_id": financeiro.venda_legada_id,
        "reconciliacao_id": financeiro.reconciliacao_id,
        "reconciliacao_status": financeiro.reconciliacao_status,
    }


def _resumo_out(resumo: Any) -> dict[str, Any]:
    return {
        "pedido_id": resumo.pedido_id,
        "canal": resumo.canal,
        "status": resumo.status,
        "criado_em": resumo.criado_em,
        "atualizado_em": resumo.atualizado_em,
        "total": str(resumo.total),
        "quantidade_itens": resumo.quantidade_itens,
        "cliente_id": resumo.cliente_id,
        "financeiro": _financeiro_out(resumo.financeiro),
        "possui_alerta": resumo.possui_alerta,
        "origem": resumo.origem,
        "versao": resumo.versao,
    }


def _detalhe_out(detalhe: Any) -> dict[str, Any]:
    return {
        "resumo": _resumo_out(detalhe.resumo),
        "subtotal": str(detalhe.subtotal),
        "descontos": str(detalhe.descontos),
        "taxas": str(detalhe.taxas),
        "itens": [
            {
                "item_id": item.item_id,
                "nome": item.nome,
                "quantidade": item.quantidade,
                "preco_unitario": str(item.preco_unitario),
                "subtotal": str(item.subtotal),
                "observacao": item.observacao,
                "adicionais": [
                    (nome, quantidade, str(preco), str(subtotal))
                    for nome, quantidade, preco, subtotal in item.adicionais
                ],
            }
            for item in detalhe.itens
        ],
        "observacoes": list(detalhe.observacoes),
        "timeline": [
            {
                "evento_id": evento.evento_id,
                "tipo": evento.tipo,
                "ocorrido_em": evento.ocorrido_em,
                "versao": evento.versao,
                "correlation_id": evento.correlation_id,
            }
            for evento in detalhe.timeline
        ],
        "financeiro": _financeiro_out(detalhe.financeiro),
        "alertas": [
            {
                "tipo": alerta.tipo,
                "severidade": alerta.severidade,
                "mensagem": alerta.mensagem,
            }
            for alerta in detalhe.alertas
        ],
    }


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise ValueError("idempotency_key_obrigatoria")
    if len(key) > _MAX_IDEMPOTENCY_KEY:
        raise ValueError("idempotency_key_excede_limite")
    return key


def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, (ErroSeguranca, PermissaoNegada, PermissionError)):
        codigo = getattr(exc, "codigo", str(exc) or "permissao_negada")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": str(codigo)},
        )
    if isinstance(exc, RecursoNaoEncontrado):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"erro": "pedido_nao_encontrado"},
        )
    if isinstance(exc, (ConflitoIdempotencia, ErroTransicao)):
        codigo = getattr(exc, "codigo", "conflito_transacional")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": str(codigo)},
        )
    if isinstance(exc, ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc) or "requisicao_invalida"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "central_pedidos_indisponivel"},
    )


def _transicao_out(resultado: Any) -> dict[str, Any]:
    pedido = resultado.pedido
    return {
        "pedido_id": str(pedido.id),
        "status": pedido.status.value,
        "versao": pedido.versao,
        "idempotente": resultado.idempotente,
        "correlation_id": str(pedido.correlation_id),
    }


def build_central_pedidos_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/pedidos", tags=["central-pedidos"])

    @router.get("", response_model=CentralPedidosPaginaOut)
    def listar_pedidos(
        request: Request,
        busca: Annotated[str | None, Query(max_length=100)] = None,
        status_filtro: Annotated[list[str] | None, Query(alias="status")] = None,
        canal: Annotated[list[str] | None, Query()] = None,
        somente_com_alertas: bool = False,
        situacao_financeira: str | None = None,
        pagina: Annotated[int, Query(ge=1)] = 1,
        tamanho_pagina: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_central(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                resultado = CentralPedidosSQLAlchemy(session).listar(
                    contexto,
                    FiltroCentralPedidos(
                        busca=busca,
                        status=tuple(status_filtro or ()),
                        canal=tuple(canal or ()),
                        somente_com_alertas=somente_com_alertas,
                        situacao_financeira=situacao_financeira,
                        pagina=pagina,
                        tamanho_pagina=tamanho_pagina,
                    ),
                )
                return {
                    "itens": [_resumo_out(item) for item in resultado.itens],
                    "pagina": resultado.pagina,
                    "tamanho_pagina": resultado.tamanho_pagina,
                    "total": resultado.total,
                }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/{pedido_id}", response_model=CentralPedidoDetalheOut)
    def detalhar_pedido(
        pedido_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_central(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                detalhe = CentralPedidosSQLAlchemy(session).detalhar(contexto, pedido_id)
                if detalhe is None:
                    return JSONResponse(
                        status_code=status.HTTP_404_NOT_FOUND,
                        content={"erro": "pedido_nao_encontrado"},
                    )
                return _detalhe_out(detalhe)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post(
        "/{pedido_id}/enviar-confirmacao",
        response_model=CentralTransicaoOut,
    )
    def enviar_confirmacao(
        pedido_id: str,
        payload: CentralEnviarConfirmacaoIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                contexto = _contexto_central(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = AplicacaoCentralPedidosTransacoesV1(session_factory).transicionar(
                contexto=contexto,
                pedido_id=pedido_id,
                destino="aguardando_confirmacao",
                versao_esperada=payload.versao_esperada,
                idempotency_key=key,
                precondicoes={"itens_validos": True, "precos_calculados": True},
                metadata={"origem_ui": "central_pedidos_web"},
            )
            return _transicao_out(resultado)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post(
        "/{pedido_id}/cancelar",
        response_model=CentralTransicaoOut,
    )
    def cancelar_pedido(
        pedido_id: str,
        payload: CentralCancelarIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            motivo = payload.motivo.strip()
            if not motivo:
                raise ValueError("motivo_cancelamento_obrigatorio")
            with session_factory() as session:
                contexto = _contexto_central(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = AplicacaoCentralPedidosTransacoesV1(session_factory).transicionar(
                contexto=contexto,
                pedido_id=pedido_id,
                destino="cancelado",
                versao_esperada=payload.versao_esperada,
                idempotency_key=key,
                motivo=motivo,
                metadata={"origem_ui": "central_pedidos_web"},
            )
            return _transicao_out(resultado)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
