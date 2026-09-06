"""HTTP adapter fino para o PDV canônico V1."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.checkout import (
    CheckoutInvalido,
    ComandoCheckoutV1,
    ResultadoCheckoutV1,
    executar_checkout_v1,
)
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
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
from core.pagamentos.erros import ConcorrenciaPagamento, ConflitoIdempotenciaPagamento
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca import (
    AutorizarAcao,
    ContextoExecucao,
    Permissao,
    ServicoAutenticacao,
)
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from infra.legacy_product_scope import ErroEscopoLojaLegada, listar_produtos_legados
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

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


class PDVCheckoutItemIn(BaseModel):
    produto_id: str = Field(min_length=1, max_length=128)
    quantidade: int = Field(gt=0)
    observacoes: str | None = Field(default=None, max_length=500)


class PDVCheckoutIn(BaseModel):
    itens: list[PDVCheckoutItemIn] = Field(min_length=1, max_length=200)
    metodo_pagamento: MetodoPagamento
    desconto: Decimal = Field(default=Decimal("0.00"), ge=0)
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


def _credenciais_basic(request: Request) -> tuple[str, str]:
    cabecalho = request.headers.get("authorization", "")
    esquema, _, valor = cabecalho.partition(" ")
    if esquema.casefold() != "basic" or not valor:
        raise CredenciaisInvalidas("credenciais invalidas")
    try:
        decodificado = base64.b64decode(valor, validate=True).decode("utf-8")
        email, password = decodificado.split(":", 1)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CredenciaisInvalidas("credenciais invalidas") from exc
    return email, password


def _contexto_pdv(request: Request, session: Session) -> ContextoExecucao:
    tenant_id = request.headers.get("x-tenant-id", "").strip()
    unidade_id = request.headers.get("x-unit-id", "").strip()
    if not tenant_id or not unidade_id:
        raise ValueError("x_tenant_id_e_x_unit_id_obrigatorios")

    email, password = _credenciais_basic(request)
    identidade = ServicoAutenticacao(
        RepositorioIdentidadesSQLAlchemy(session)
    ).autenticar(email=email, password=password)
    identidade = identidade.no_escopo_ativo(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )
    contexto = identidade.contexto(
        origem="pdv_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=Permissao.PDV_OPERAR,
        recurso="pdv",
        tenant_recurso=tenant_id,
        unidade_recurso=unidade_id,
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
) -> list[dict[str, Any]]:
    produtos: list[dict[str, Any]] = []
    for row in listar_produtos_legados(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
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

    with session_factory() as session:
        catalogo = {
            str(item["id"]): item
            for item in _catalogo_ativo(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
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

    agora = datetime.now(timezone.utc)
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


def _semantica_pedido(pedido: Pedido) -> tuple[Any, ...]:
    return (
        str(pedido.tenant_id),
        str(pedido.unidade_id),
        str(pedido.idempotency_key),
        str(pedido.cliente_id) if pedido.cliente_id else None,
        str(pedido.subtotal.valor),
        str(pedido.descontos.valor),
        str(pedido.taxas.valor),
        str(pedido.total.valor),
        tuple(
            (
                str(item.produto_id) if item.produto_id else None,
                item.nome_produto,
                item.quantidade.valor,
                str(item.preco_unitario.valor),
                str(item.subtotal.valor),
                item.observacao,
            )
            for item in pedido.itens
        ),
    )


def _resposta_checkout(
    resultado: ResultadoCheckoutV1,
    *,
    pedido_solicitado: Pedido,
) -> dict[str, Any]:
    persistido = resultado.aguardando_confirmacao.pedido
    if (
        resultado.pedido.idempotente
        and _semantica_pedido(resultado.pedido.pedido)
        != _semantica_pedido(pedido_solicitado)
    ):
        raise ConflitoIdempotencia(
            "payload divergente para a mesma idempotency_key"
        )

    pagamento = None
    if resultado.pagamento is not None:
        financeiro = resultado.pagamento.pagamento
        pagamento = {
            "id": financeiro.id,
            "status": financeiro.status.value,
            "metodo": financeiro.metodo.value,
            "valor_previsto": str(financeiro.valor_previsto.valor),
            "valor_pago": str(financeiro.valor_pago.valor),
            "saldo": str(financeiro.saldo.valor),
        }

    return {
        "comanda": {
            "pedido_id": str(persistido.id),
            "status": persistido.status.value,
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
    if isinstance(exc, (PermissaoNegada, ErroSeguranca)):
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


def build_pdv_router(*, session_factory: SessionFactory) -> APIRouter:
    router = APIRouter(prefix="/v1/pdv", tags=["pdv"])

    @router.get("/produtos", response_model=PDVCatalogoOut)
    def listar_produtos(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_pdv(request, session)
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
                contexto = _contexto_pdv(request, session)
            pedido = _montar_pedido(
                payload=payload,
                session_factory=session_factory,
                contexto=contexto,
                idempotency_key=key,
            )
            comando = ComandoCheckoutV1(
                pedido=pedido,
                timestamp=datetime.now(timezone.utc),
                pagamento_id=(
                    _stable_id("pay", key=key, sufixo="pagamento")
                    if pedido.total.valor > 0
                    else None
                ),
                metodo_pagamento=(
                    payload.metodo_pagamento if pedido.total.valor > 0 else None
                ),
            )
            resultado = executar_checkout_v1(
                comando=comando,
                contexto=contexto,
                session_factory=session_factory,
            )
            body = _resposta_checkout(resultado, pedido_solicitado=pedido)
            http_status = (
                status.HTTP_200_OK
                if resultado.pedido.idempotente
                else status.HTTP_201_CREATED
            )
            return JSONResponse(status_code=http_status, content=body)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
