"""Adaptador HTTP fino para o Delivery Próprio comercial V1.

A fronteira Web nunca aceita tenant/unidade livres. O escopo vem da sessão
assinada (ou do Basic legado quando a sessão inexiste) e toda regra de negócio
permanece em ``application.delivery_operacao_comercial`` e no Core canônico.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.delivery_operacao_comercial import (
    ErroDeliveryComercial,
    abrir_carrinho_delivery_comercial,
    acompanhar_delivery_comercial,
    adicionar_item_delivery_comercial,
    cancelar_delivery_comercial,
    confirmar_delivery_comercial,
    cotar_endereco_delivery_comercial,
    listar_clientes_delivery_comercial,
    obter_carrinho_delivery_comercial,
    resolver_contexto_jornada_delivery,
)
from core.delivery.erros import ErroDelivery
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 96


class DeliveryAbrirCarrinhoIn(BaseModel):
    cliente_id: str = Field(min_length=1, max_length=120)
    carrinho_id: str = Field(min_length=1, max_length=120)


class DeliveryAdicionarItemIn(BaseModel):
    produto_id: str = Field(min_length=1, max_length=120)
    quantidade: int = Field(ge=1, le=100)
    versao_esperada: int = Field(ge=1)


class DeliveryCotacaoIn(BaseModel):
    versao_esperada: int = Field(ge=1)


class DeliveryConfirmarIn(BaseModel):
    metodo_pagamento: MetodoPagamento


class DeliveryCancelarIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)


def _identidade(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> IdentidadeUsuario:
    return obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    ).identidade


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
            content={"erro": "credenciais_invalidas"},
        )
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        codigo = getattr(exc, "codigo", str(exc) or "permissao_negada")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": str(codigo)},
        )
    if isinstance(exc, (ErroDelivery, ErroDeliveryComercial, ValueError)):
        codigo = str(getattr(exc, "codigo", str(exc) or "delivery_invalido"))
        if "indisponivel" in codigo or "nao_encontr" in codigo:
            http_status = status.HTTP_404_NOT_FOUND
        elif any(
            termo in codigo
            for termo in (
                "compare_and_swap",
                "confirmado_por_outro",
                "nao_confirmavel",
                "nao_cancelavel",
                "liquidado_exige",
            )
        ):
            http_status = status.HTTP_409_CONFLICT
        else:
            http_status = status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "delivery_indisponivel"},
    )


def _cliente_out(cliente: Any) -> dict[str, Any]:
    return {
        "cliente_id": cliente.cliente_id,
        "origem": cliente.origem.value,
        "canais": [contato.canal.value for contato in cliente.contatos],
        "criado_em": cliente.criado_em,
        "versao": cliente.versao,
    }


def _contexto_out(contexto: Any) -> dict[str, Any]:
    return {
        "cliente": _cliente_out(contexto.cliente),
        "endereco": {
            "referencia": contexto.endereco.referencia,
            "endereco_formatado": contexto.endereco.endereco_formatado,
            "cep": contexto.endereco.cep,
        },
        "catalogo": [
            {
                "produto_id": produto.produto_id,
                "nome": produto.nome,
                "preco": str(produto.preco),
                "estoque_disponivel": str(produto.estoque_disponivel),
                "ativo": produto.ativo,
                "versao": produto.versao,
            }
            for produto in contexto.catalogo
        ],
        "origem_entrega": {
            "endereco_texto": contexto.origem_entrega.endereco_texto,
            "versao": contexto.origem_entrega.versao,
        },
        "areas_entrega": [
            {
                "area_id": area.area_id,
                "nome": area.nome,
                "taxa": str(area.taxa),
                "sla_minutos": area.sla_minutos,
                "sla_maxutos": area.sla_maxutos,
                "versao": area.versao,
                "ativa": area.ativa,
            }
            for area in contexto.areas_entrega
        ],
    }


def _carrinho_out(carrinho: Any) -> dict[str, Any]:
    endereco = None
    if carrinho.endereco is not None:
        endereco = {
            "endereco_id": carrinho.endereco.endereco_id,
            "cep": carrinho.endereco.cep,
            "logradouro": carrinho.endereco.logradouro,
            "numero": carrinho.endereco.numero,
            "bairro": carrinho.endereco.bairro,
            "cidade": carrinho.endereco.cidade,
            "uf": carrinho.endereco.uf,
        }
    cotacao = None
    if carrinho.cotacao is not None:
        cotacao = {
            "area_id": carrinho.cotacao.area_id,
            "nome_area": carrinho.cotacao.nome_area,
            "taxa": str(carrinho.cotacao.taxa),
            "sla_minutos": carrinho.cotacao.sla_minutos,
            "sla_maxutos": carrinho.cotacao.sla_maxutos,
            "versao_area": carrinho.cotacao.versao_area,
        }
    return {
        "carrinho_id": carrinho.carrinho_id,
        "cliente_id": carrinho.cliente_ref,
        "versao": carrinho.versao,
        "status": carrinho.status.value,
        "itens": [
            {
                "produto_id": item.produto_id,
                "nome": item.nome,
                "quantidade": item.quantidade,
                "preco_unitario": str(item.preco_unitario),
                "subtotal": str(item.subtotal),
                "produto_versao": item.produto_versao,
            }
            for item in carrinho.itens
        ],
        "endereco": endereco,
        "cotacao": cotacao,
        "subtotal": str(carrinho.subtotal),
        "taxa_entrega": str(carrinho.taxa_entrega),
        "desconto_cupom": str(carrinho.desconto_cupom),
        "cashback_reservado": str(carrinho.cashback_reservado),
        "total": str(carrinho.total),
        "pedido_id": carrinho.pedido_id,
    }


def _tracking_out(tracking: Any) -> dict[str, Any]:
    return {
        "pedido_id": tracking.pedido_id,
        "status_pedido": tracking.status_pedido.value,
        "entrega_id": tracking.entrega_id,
        "status_entrega": tracking.status_entrega.value,
        "total": str(tracking.total),
        "eventos": [
            {
                "tipo": evento.tipo,
                "ocorrido_em": evento.ocorrido_em,
                "status_entrega": evento.status_entrega,
            }
            for evento in tracking.eventos
        ],
    }


def build_delivery_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/delivery", tags=["delivery"])

    @router.get("/clientes", response_model=dict[str, Any])
    def listar_clientes(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            clientes = listar_clientes_delivery_comercial(
                identidade=identidade,
                session_factory=session_factory,
            )
            return {"itens": [_cliente_out(cliente) for cliente in clientes]}
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/clientes/{cliente_id}/contexto", response_model=dict[str, Any])
    def obter_contexto(
        cliente_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            contexto = resolver_contexto_jornada_delivery(
                identidade=identidade,
                cliente_id=cliente_id,
                session_factory=session_factory,
            )
            return _contexto_out(contexto)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/carrinhos", response_model=dict[str, Any])
    def abrir_carrinho(
        payload: DeliveryAbrirCarrinhoIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            carrinho = abrir_carrinho_delivery_comercial(
                identidade=identidade,
                cliente_id=payload.cliente_id,
                carrinho_id=payload.carrinho_id,
                session_factory=session_factory,
            )
            return _carrinho_out(carrinho)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/clientes/{cliente_id}/carrinhos/{carrinho_id}", response_model=dict[str, Any])
    def obter_carrinho(
        cliente_id: str,
        carrinho_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            carrinho = obter_carrinho_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                carrinho_id=carrinho_id,
                session_factory=session_factory,
            )
            if carrinho is None:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"erro": "carrinho_delivery_indisponivel"},
                )
            return _carrinho_out(carrinho)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/clientes/{cliente_id}/carrinhos/{carrinho_id}/itens", response_model=dict[str, Any])
    def adicionar_item(
        cliente_id: str,
        carrinho_id: str,
        payload: DeliveryAdicionarItemIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            carrinho = adicionar_item_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                carrinho_id=carrinho_id,
                produto_id=payload.produto_id,
                quantidade=payload.quantidade,
                expected_version=payload.versao_esperada,
                session_factory=session_factory,
            )
            return _carrinho_out(carrinho)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/clientes/{cliente_id}/carrinhos/{carrinho_id}/cotacao", response_model=dict[str, Any])
    def cotar_endereco(
        cliente_id: str,
        carrinho_id: str,
        payload: DeliveryCotacaoIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            carrinho = cotar_endereco_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                carrinho_id=carrinho_id,
                expected_version=payload.versao_esperada,
                session_factory=session_factory,
            )
            return _carrinho_out(carrinho)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/clientes/{cliente_id}/carrinhos/{carrinho_id}/confirmar", response_model=dict[str, Any])
    def confirmar_pedido(
        cliente_id: str,
        carrinho_id: str,
        payload: DeliveryConfirmarIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = confirmar_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                carrinho_id=carrinho_id,
                metodo_pagamento=payload.metodo_pagamento,
                idempotency_key=key,
                session_factory=session_factory,
            )
            return {
                "pedido_id": resultado.pedido_id,
                "entrega_id": resultado.entrega_id,
                "status_pedido": resultado.status_pedido.value,
                "status_entrega": resultado.status_entrega.value,
            }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/clientes/{cliente_id}/pedidos/{pedido_id}", response_model=dict[str, Any])
    def acompanhar_pedido(
        cliente_id: str,
        pedido_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            tracking = acompanhar_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                pedido_id=pedido_id,
                session_factory=session_factory,
            )
            return _tracking_out(tracking)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/clientes/{cliente_id}/pedidos/{pedido_id}/cancelar", response_model=dict[str, Any])
    def cancelar_pedido(
        cliente_id: str,
        pedido_id: str,
        payload: DeliveryCancelarIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            tracking = cancelar_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                pedido_id=pedido_id,
                motivo=payload.motivo,
                idempotency_key=key,
                session_factory=session_factory,
            )
            return _tracking_out(tracking)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
