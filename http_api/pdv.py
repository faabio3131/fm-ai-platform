"""HTTP adapter fino para o PDV canônico V1."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.catalogo_estoque_cutover import (
    ErroCatalogoEstoqueCutover,
)
from application.checkout import (
    CheckoutInvalido,
    ComandoCheckoutV1,
    ResultadoCheckoutV1,
    executar_checkout_v1,
)
from application.pdv_asaas import (
    ErroPagamentoAsaas,
    iniciar_cobranca_asaas_pdv,
    verificar_cobranca_asaas_pdv,
)
from application.pdv_cartao_pagbank_checkout import (
    CheckoutCartaoInvalido,
    criar_checkout_cartao_pdv,
    verificar_checkout_cartao_pdv,
)
from application.pdv_cartao_terminal import (
    CartaoTerminalInvalido,
    confirmar_cartao_terminal_pdv,
)
from application.pdv_pix_pagbank import (
    PixPdvInvalido,
    iniciar_pix_pagbank_pdv,
    verificar_pix_pagbank_pdv,
)
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import (
    CanalAtendimento,
    OrigemPedido,
    PedidoStatus,
)
from core.dominio.erros import ConflitoIdempotencia, ErroDominio, PermissaoNegada
from core.dominio.ids import (
    ClienteId,
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.estoque.erros import SaldoInsuficiente
from core.pagamentos.asaas import ErroAsaas, PagadorAsaas
from core.pagamentos.erros import (
    ConcorrenciaPagamento,
    ConflitoIdempotenciaPagamento,
    OperacaoPagamentoNaoAutorizada,
)
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.pagbank import ClientePagBank, ErroPagBank
from core.seguranca import AutorizarAcao, ContextoExecucao, Permissao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.segredos import SecretStore
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional
from infra.legacy_product_scope import ErroEscopoLojaLegada, listar_produtos_legados
from infra.pagamentos.pagbank_runtime import CredencialPagBankNaoConfigurada

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 96
_METODOS_PDV = frozenset(
    {
        MetodoPagamento.PIX,
        MetodoPagamento.CARTAO_DEBITO,
        MetodoPagamento.CARTAO_CREDITO,
        MetodoPagamento.DINHEIRO,
    }
)


class PDVCartaoTerminalIn(BaseModel):
    referencia_terminal: str = Field(min_length=4, max_length=80)
    autorizado_no_terminal: bool


class PDVPixPagadorIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)
    documento: str = Field(min_length=11, max_length=18)


class PDVCheckoutItemIn(BaseModel):
    produto_id: str = Field(min_length=1, max_length=128)
    quantidade: int = Field(gt=0)
    observacoes: str | None = Field(default=None, max_length=500)


class PDVCheckoutIn(BaseModel):
    itens: list[PDVCheckoutItemIn] = Field(min_length=1, max_length=200)
    metodo_pagamento: MetodoPagamento
    provedor_pagamento: Literal["pagbank", "asaas"] | None = None
    desconto: Decimal = Field(default=Decimal("0.00"), ge=0)
    valor_recebido: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cliente_id: str | None = Field(default=None, max_length=128)


class PDVProdutoOut(BaseModel):
    id: str
    nome: str
    categoria: str | None
    preco: str
    disponivel: bool


class PDVCatalogoOut(BaseModel):
    produtos: list[PDVProdutoOut]


class PDVComandaItemOut(BaseModel):
    produto_id: str | None
    nome: str
    quantidade: int
    preco_unitario: str
    subtotal: str
    observacoes: str | None


class PDVComandaOut(BaseModel):
    pedido_id: str
    status: str
    itens: list[PDVComandaItemOut]
    subtotal: str
    descontos: str
    total: str


class PDVPagamentoOut(BaseModel):
    id: str
    status: str
    metodo: str
    valor_previsto: str
    valor_pago: str
    saldo: str


class PDVCheckoutOut(BaseModel):
    comanda: PDVComandaOut
    pagamento: PDVPagamentoOut | None
    idempotente: bool
    correlation_id: str


def _contexto_pdv(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> ContextoExecucao:
    resolvida = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    )
    identidade = resolvida.identidade
    contexto = identidade.contexto(
        origem="pdv_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=Permissao.PDV_OPERAR,
        recurso="pdv",
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise PermissaoNegada(decisao.codigo)
    return contexto


def _mapping(row: Any) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", None)
    if mapping is None:
        raise ErroEscopoLojaLegada("produto legado sem representação de leitura")
    return dict(mapping)


def _flag_ativo(produto: dict[str, Any]) -> bool:
    for chave in ("ativo", "disponivel", "ativo_cardapio"):
        if chave in produto and produto[chave] is not None:
            return bool(produto[chave])
    return True


def _preco(produto: dict[str, Any]) -> Dinheiro:
    bruto = produto.get("preco_venda")
    if bruto is None:
        raise ValueError("produto_sem_preco_venda")
    try:
        return Dinheiro(Decimal(str(bruto)))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("produto_com_preco_invalido") from exc


def _catalogo_ativo(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    produto_ids: tuple[int, ...] | None = None,
) -> list[dict[str, Any]]:
    produtos: list[dict[str, Any]] = []
    for row in listar_produtos_legados(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        produto_ids=produto_ids,
    ):
        produto = _mapping(row)
        if not _flag_ativo(produto):
            continue
        try:
            preco = _preco(produto)
        except (ErroDominio, ValueError):
            continue
        if preco.valor < 0:
            continue
        nome = str(produto.get("nome", "")).strip()
        if not nome:
            continue
        produtos.append(
            {
                "id": f"legacy:produto:{int(produto['id'])}",
                "nome": nome,
                "categoria": (
                    str(produto["categoria"]).strip()
                    if produto.get("categoria") is not None
                    else None
                ),
                "preco": str(preco.valor),
                "disponivel": True,
                "_preco": preco,
            }
        )
    return produtos


def _stable_id(prefixo: str, *, key: str, sufixo: str) -> str:
    valor = uuid5(NAMESPACE_URL, f"fm-ai-pdv-v1:{key}:{sufixo}")
    return f"{prefixo}-{valor}"


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise ValueError("idempotency_key_obrigatoria")
    if len(key) > _MAX_IDEMPOTENCY_KEY:
        raise ValueError("idempotency_key_excede_limite")
    return key


def _montar_pedido(
    *,
    payload: PDVCheckoutIn,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    idempotency_key: str,
) -> Pedido:
    if payload.metodo_pagamento not in _METODOS_PDV:
        raise ValueError("metodo_pagamento_nao_suportado_no_pdv")

    # Nunca varrer o cardápio inteiro para registrar uma venda com poucos
    # itens. IDs inválidos permanecem indisponíveis, como antes.
    product_ids: set[int] = set()
    for item in payload.itens:
        match = re.fullmatch(r"legacy:produto:(0|[1-9][0-9]*)", item.produto_id)
        if match is not None and len(match.group(1)) <= 19:
            numero = int(match.group(1))
            if numero <= 9223372036854775807:
                product_ids.add(numero)

    with session_factory() as session:
        catalogo = {
            str(item["id"]): item
            for item in _catalogo_ativo(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                produto_ids=tuple(sorted(product_ids)),
            )
        }

    tenant = TenantId(contexto.tenant_id)
    unidade = UnidadeId(contexto.unidade_id)
    pedido_id = PedidoId(_stable_id("pdv", key=idempotency_key, sufixo="pedido"))
    itens: list[ItemPedido] = []
    subtotal = Dinheiro(Decimal("0.00"))

    for indice, entrada in enumerate(payload.itens):
        produto = catalogo.get(entrada.produto_id)
        if produto is None:
            raise ValueError("produto_indisponivel_ou_fora_do_escopo")
        preco = produto["_preco"]
        if not isinstance(preco, Dinheiro):
            raise TypeError("produto_com_preco_invalido")
        quantidade = QuantidadeItem(entrada.quantidade)
        item_subtotal = preco * quantidade.valor
        subtotal = subtotal + item_subtotal
        itens.append(
            ItemPedido(
                id=PedidoItemId(
                    _stable_id(
                        "item",
                        key=idempotency_key,
                        sufixo=f"{indice}:{entrada.produto_id}",
                    )
                ),
                tenant_id=tenant,
                unidade_id=unidade,
                produto_id=ProdutoId(str(produto["id"])),
                nome_produto=str(produto["nome"]),
                quantidade=quantidade,
                preco_unitario=preco,
                subtotal=item_subtotal,
                observacao=(
                    entrada.observacoes.strip() if entrada.observacoes else None
                ),
            )
        )

    desconto = Dinheiro(payload.desconto)
    if desconto.valor > subtotal.valor:
        raise ValueError("desconto_maior_que_subtotal")
    if desconto.valor > 0:
        decisao = AutorizarAcao().executar(
            contexto=contexto,
            permissao=Permissao.DESCONTO_APLICAR,
            recurso="pedido.desconto",
            tenant_recurso=contexto.tenant_id,
            unidade_recurso=contexto.unidade_id,
        )
        if not decisao.autorizado:
            raise PermissaoNegada(decisao.codigo)

    agora = datetime.now(UTC)
    return Pedido.novo(
        id=pedido_id,
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.PDV,
        canal=CanalAtendimento.PDV,
        status=PedidoStatus.RASCUNHO,
        cliente_id=ClienteId(payload.cliente_id) if payload.cliente_id else None,
        criado_em=agora,
        atualizado_em=agora,
        versao=1,
        correlation_id=CorrelationId(contexto.correlation_id),
        idempotency_key=IdempotencyKey(idempotency_key),
        subtotal=subtotal,
        descontos=desconto,
        taxas=Dinheiro(Decimal("0.00")),
        total=subtotal - desconto,
        itens=tuple(itens),
        observacoes=(),
    )


def _resposta_checkout(resultado: ResultadoCheckoutV1) -> dict[str, Any]:
    persistido = resultado.aguardando_confirmacao.pedido
    pagamento = None
    if resultado.pagamento is not None:
        financeiro = resultado.pagamento.pagamento
        pagamento = {
            "id": financeiro.id,
            "status": financeiro.status.value,
            "metodo": financeiro.metodo.value,
            "provedor": financeiro.provedor,
            "valor_previsto": str(financeiro.valor_previsto.valor),
            "valor_pago": str(financeiro.valor_pago.valor),
            "saldo": str(financeiro.saldo.valor),
        }

    return {
        "comanda": {
            "pedido_id": str(persistido.id),
            "status": (resultado.status_final or persistido.status).value,
            "itens": [
                {
                    "produto_id": str(item.produto_id) if item.produto_id else None,
                    "nome": item.nome_produto,
                    "quantidade": item.quantidade.valor,
                    "preco_unitario": str(item.preco_unitario.valor),
                    "subtotal": str(item.subtotal.valor),
                    "observacoes": item.observacao,
                }
                for item in persistido.itens
            ],
            "subtotal": str(persistido.subtotal.valor),
            "descontos": str(persistido.descontos.valor),
            "total": str(persistido.total.valor),
        },
        "pagamento": pagamento,
        "idempotente": bool(resultado.pedido.idempotente),
        "correlation_id": str(persistido.correlation_id),
    }


def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(
        exc,
        (
            ConflitoIdempotencia,
            ConflitoIdempotenciaPagamento,
            ConcorrenciaPagamento,
        ),
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": "conflito_transacional"},
        )
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, (PermissaoNegada, ErroSeguranca, OperacaoPagamentoNaoAutorizada)):
        codigo = getattr(exc, "codigo", "permissao_negada")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": str(codigo)},
        )
    if isinstance(exc, ErroEscopoLojaLegada):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": "catalogo_indisponivel_no_escopo"},
        )
    if isinstance(exc, (SaldoInsuficiente, ErroCatalogoEstoqueCutover)):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": "estoque_indisponivel_para_checkout"},
        )
    if isinstance(exc, (CheckoutInvalido, ErroDominio, ValueError, TypeError)):
        codigo = getattr(exc, "codigo", str(exc) or "requisicao_invalida")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(codigo)},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "pdv_indisponivel"},
    )


def _erro_pix_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, PermissionError):
        return JSONResponse(status_code=403, content={"erro": "seguranca.pdv_pagamento_permissao_exigida"})
    if isinstance(exc, LookupError):
        return JSONResponse(status_code=404, content={"erro": "pagamento_nao_encontrado"})
    if isinstance(exc, PixPdvInvalido):
        return JSONResponse(status_code=409, content={"erro": str(exc)})
    if isinstance(exc, CredencialPagBankNaoConfigurada):
        return JSONResponse(status_code=503, content={"erro": "pagbank_nao_configurado"})
    if isinstance(exc, ErroPagBank):
        return JSONResponse(status_code=502, content={"erro": "pagbank_indisponivel"})
    return _erro_http(exc)


def build_pdv_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime | None = None,
    secret_store: SecretStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/pdv", tags=["pdv"])

    @router.get("/produtos", response_model=PDVCatalogoOut)
    def listar_produtos(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                catalogo = _catalogo_ativo(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                )
            return {
                "produtos": [
                    {
                        chave: valor
                        for chave, valor in produto.items()
                        if not chave.startswith("_")
                    }
                    for produto in catalogo
                ]
            }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post(
        "/checkout",
        response_model=PDVCheckoutOut,
        status_code=status.HTTP_201_CREATED,
    )
    def checkout(
        payload: PDVCheckoutIn,
        request: Request,
    ) -> JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            pedido = _montar_pedido(
                payload=payload,
                session_factory=session_factory,
                contexto=contexto,
                idempotency_key=key,
            )
            recebido = None
            if payload.valor_recebido is not None:
                if payload.metodo_pagamento is not MetodoPagamento.DINHEIRO:
                    raise CheckoutInvalido("valor_recebido_exige_dinheiro")
                recebido = Dinheiro(payload.valor_recebido)

            if (
                payload.provedor_pagamento is not None
                and payload.metodo_pagamento not in {
                    MetodoPagamento.PIX, MetodoPagamento.CARTAO_CREDITO
                }
            ):
                raise CheckoutInvalido("provedor_incompativel_com_metodo")
            comando = ComandoCheckoutV1(
                pedido=pedido,
                timestamp=datetime.now(UTC),
                pagamento_id=(
                    _stable_id("pay", key=key, sufixo="pagamento")
                    if pedido.total.valor > 0
                    else None
                ),
                metodo_pagamento=(
                    payload.metodo_pagamento if pedido.total.valor > 0 else None
                ),
                valor_recebido=recebido,
                provedor_pagamento=(
                    (payload.provedor_pagamento or "pagbank")
                    if payload.metodo_pagamento is MetodoPagamento.PIX
                    else (
                        "asaas"
                        if payload.metodo_pagamento is MetodoPagamento.CARTAO_CREDITO
                        and payload.provedor_pagamento == "asaas"
                        else None
                    )
                ),
            )
            resultado = executar_checkout_v1(
                comando=comando,
                contexto=contexto,
                session_factory=session_factory,
            )
            body = _resposta_checkout(resultado)
            http_status = (
                status.HTTP_200_OK
                if resultado.pedido.idempotente
                else status.HTTP_201_CREATED
            )
            return JSONResponse(status_code=http_status, content=body)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/pagamentos/{pagamento_id}/iniciar-asaas")
    def iniciar_asaas(
        pagamento_id: str, pagador: PDVPixPagadorIn, request: Request,
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request, session, auth_runtime=auth_runtime,
                )
            result = iniciar_cobranca_asaas_pdv(
                contexto=contexto, pagamento_id=pagamento_id,
                pagador=PagadorAsaas(
                    nome=pagador.nome, email=pagador.email,
                    documento=pagador.documento,
                ),
                session_factory=session_factory,
            )
            return JSONResponse(
                status_code=200 if result.idempotente else 201,
                content=asdict(result),
            )
        except (ErroAsaas, ErroPagamentoAsaas) as exc:
            return JSONResponse(status_code=503, content={"erro": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _erro_pix_http(exc)

    @router.post("/pagamentos/{pagamento_id}/verificar-asaas")
    def verificar_asaas(pagamento_id: str, request: Request) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request, session, auth_runtime=auth_runtime,
                )
            result = verificar_cobranca_asaas_pdv(
                contexto=contexto, pagamento_id=pagamento_id,
                session_factory=session_factory,
            )
            return JSONResponse(status_code=200, content=asdict(result))
        except (ErroAsaas, ErroPagamentoAsaas) as exc:
            return JSONResponse(status_code=503, content={"erro": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _erro_pix_http(exc)

    @router.post("/pagamentos/{pagamento_id}/iniciar-pix-pagbank")
    def iniciar_pix(
        pagamento_id: str,
        pagador: PDVPixPagadorIn,
        request: Request,
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = iniciar_pix_pagbank_pdv(
                contexto=contexto,
                pagamento_id=pagamento_id,
                cliente=ClientePagBank(
                    nome=pagador.nome,
                    email=pagador.email,
                    tax_id=pagador.documento,
                ),
                session_factory=session_factory,
                secret_store=secret_store,
            )
            return JSONResponse(
                status_code=200 if resultado.idempotente else 201,
                content=asdict(resultado),
            )
        except Exception as exc:  # noqa: BLE001 - fronteira fail-closed
            return _erro_pix_http(exc)

    @router.post("/pagamentos/{pagamento_id}/verificar-pix-pagbank")
    def verificar_pix(pagamento_id: str, request: Request) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = verificar_pix_pagbank_pdv(
                contexto=contexto,
                pagamento_id=pagamento_id,
                session_factory=session_factory,
                secret_store=secret_store,
            )
            return JSONResponse(status_code=200, content=resultado)
        except Exception as exc:  # noqa: BLE001 - fronteira fail-closed
            return _erro_pix_http(exc)

    @router.post("/pagamentos/{pagamento_id}/confirmar-cartao-terminal")
    def confirmar_cartao_terminal(
        pagamento_id: str,
        payload: PDVCartaoTerminalIn,
        request: Request,
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = confirmar_cartao_terminal_pdv(
                contexto=contexto,
                pagamento_id=pagamento_id,
                referencia_terminal=payload.referencia_terminal,
                autorizado_no_terminal=payload.autorizado_no_terminal,
                session_factory=session_factory,
            )
            return JSONResponse(
                status_code=200,
                content=asdict(resultado),
            )
        except CartaoTerminalInvalido as exc:
            return JSONResponse(
                status_code=409,
                content={"erro": str(exc)},
            )
        except LookupError:
            return JSONResponse(
                status_code=404,
                content={"erro": "pagamento_nao_encontrado"},
            )
        except Exception as exc:  # noqa: BLE001 - boundary autenticada
            return _erro_http(exc)

    @router.post("/pagamentos/{pagamento_id}/criar-checkout-cartao-pagbank")
    def criar_checkout_cartao(
        pagamento_id: str,
        request: Request,
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = criar_checkout_cartao_pdv(
                contexto=contexto,
                pagamento_id=pagamento_id,
                session_factory=session_factory,
                secret_store=secret_store,
            )
            return JSONResponse(
                status_code=200 if resultado.idempotente else 201,
                content=asdict(resultado),
            )
        except CheckoutCartaoInvalido as exc:
            return JSONResponse(status_code=409, content={"erro": str(exc)})
        except Exception as exc:  # noqa: BLE001 - boundary sanitizado
            return _erro_pix_http(exc)

    @router.post("/pagamentos/{pagamento_id}/verificar-checkout-cartao-pagbank")
    def verificar_checkout_cartao(
        pagamento_id: str,
        request: Request,
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            resultado = verificar_checkout_cartao_pdv(
                contexto=contexto,
                pagamento_id=pagamento_id,
                session_factory=session_factory,
                secret_store=secret_store,
            )
            return JSONResponse(status_code=200, content=asdict(resultado))
        except CheckoutCartaoInvalido as exc:
            return JSONResponse(status_code=409, content={"erro": str(exc)})
        except Exception as exc:  # noqa: BLE001 - boundary sanitizado
            return _erro_pix_http(exc)

    return router
