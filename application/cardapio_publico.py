"""Autoridade publica configuravel e indexada do Cardapio Digital V1.

O navegador conhece somente um ``public_id`` opaco. A traducao para tenant/unidade
ocorre no servidor por lookup indexado e, a partir desse escopo confiavel, reutiliza
a projecao canonica de catalogo do Delivery. O slug e configuravel e apenas visual.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from application.checkout import (
    ComandoCheckoutV1,
    ResultadoCheckoutV1,
    executar_checkout_v1,
)
from core.delivery.modelos import ProdutoDelivery
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.ids import (
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
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.administracao.modelos_orm import EmpresaAdminORM, UnidadeAdminORM
from infra.cardapio_publico.repositorio_sqlalchemy import (
    PublicacaoCardapioPersistida,
    RepositorioCardapioPublicoSQLAlchemy,
)
from infra.delivery.catalogo_sqlalchemy import CatalogoDeliverySQLAlchemy

_SLUG_INVALIDO = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class CardapioPublicoV1:
    publicacao: PublicacaoCardapioPersistida
    nome_empresa: str
    nome_unidade: str
    tipo_unidade: str
    catalogo: tuple[ProdutoDelivery, ...]


@dataclass(frozen=True)
class ItemAutosservicoV1:
    produto_id: str
    quantidade: int


@dataclass(frozen=True)
class ResultadoAutosservicoV1:
    checkout: ResultadoCheckoutV1
    public_id: str


def normalizar_slug_publico(valor: str) -> str:
    bruto = unicodedata.normalize("NFKD", str(valor).strip())
    ascii_texto = bruto.encode("ascii", "ignore").decode("ascii").casefold()
    slug = _SLUG_INVALIDO.sub("-", ascii_texto).strip("-")
    if len(slug) < 3 or len(slug) > 80:
        raise ValueError("cardapio_publico.slug_invalido")
    return slug


def consultar_publicacao(
    *, session: Session, tenant_id: str, unidade_id: str
) -> PublicacaoCardapioPersistida | None:
    return RepositorioCardapioPublicoSQLAlchemy(session).obter_por_escopo(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )


def salvar_publicacao(
    *,
    session: Session,
    tenant_id: str,
    unidade_id: str,
    slug: str,
    publicada: bool,
    versao_esperada: int,
) -> PublicacaoCardapioPersistida:
    return RepositorioCardapioPublicoSQLAlchemy(session).salvar(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        slug=normalizar_slug_publico(slug),
        publicada=bool(publicada),
        versao_esperada=versao_esperada,
    )


def resolver_cardapio_publico(
    *, session: Session, public_id: str
) -> CardapioPublicoV1 | None:
    referencia = str(public_id).strip()
    if len(referencia) != 32 or not all(c in "0123456789abcdef" for c in referencia):
        return None

    publicacao = RepositorioCardapioPublicoSQLAlchemy(session).obter_por_public_id(
        public_id=referencia
    )
    if publicacao is None or not publicacao.publicada:
        return None

    unidade = session.get(
        UnidadeAdminORM,
        (publicacao.tenant_id, publicacao.unidade_id),
    )
    empresa = session.get(EmpresaAdminORM, publicacao.tenant_id)
    if unidade is None or empresa is None or not unidade.ativa or not empresa.ativa:
        return None

    catalogo = CatalogoDeliverySQLAlchemy(session).listar(
        tenant_id=publicacao.tenant_id,
        unidade_id=publicacao.unidade_id,
    )
    return CardapioPublicoV1(
        publicacao=publicacao,
        nome_empresa=empresa.nome_exibicao,
        nome_unidade=unidade.nome_fantasia,
        tipo_unidade=unidade.tipo,
        catalogo=tuple(produto for produto in catalogo if produto.ativo),
    )


def _id_deterministico(prefixo: str, raiz: str) -> str:
    digest = hashlib.sha256(raiz.encode("utf-8")).hexdigest()[:24]
    return f"{prefixo}-{digest}"


def executar_autosservico_publico(
    *,
    session_factory: Callable[[], Session],
    public_id: str,
    itens: tuple[ItemAutosservicoV1, ...],
    metodo_pagamento: MetodoPagamento,
    idempotency_key: str,
) -> ResultadoAutosservicoV1:
    """Cria pedido publico pela mesma fronteira transacional do Checkout V1.

    O cliente nunca informa tenant/unidade/preco. O escopo e os snapshots de preco
    sao reconstruidos exclusivamente do ``public_id`` publicado e do catalogo
    canonico da unidade.
    """

    chave = idempotency_key.strip()
    if len(chave) < 8 or len(chave) > 120:
        raise ValueError("cardapio_publico.idempotency_key_invalida")
    if not itens:
        raise ValueError("cardapio_publico.pedido_sem_itens")

    with session_factory() as session:
        cardapio = resolver_cardapio_publico(session=session, public_id=public_id)
        if cardapio is None:
            raise LookupError("cardapio_publico_indisponivel")
        produtos = {produto.produto_id: produto for produto in cardapio.catalogo}

    tenant_id = cardapio.publicacao.tenant_id
    unidade_id = cardapio.publicacao.unidade_id
    raiz = f"cardapio-publico:{public_id}:{chave}"
    agora = datetime.now(timezone.utc)
    itens_pedido: list[ItemPedido] = []
    subtotal = Decimal("0.00")
    vistos: set[str] = set()
    for indice, solicitado in enumerate(itens):
        if solicitado.produto_id in vistos:
            raise ValueError("cardapio_publico.produto_duplicado")
        vistos.add(solicitado.produto_id)
        produto = produtos.get(solicitado.produto_id)
        if produto is None:
            raise ValueError("cardapio_publico.produto_indisponivel")
        if solicitado.quantidade < 1 or solicitado.quantidade > 100:
            raise ValueError("cardapio_publico.quantidade_invalida")
        if Decimal(solicitado.quantidade) > produto.estoque_disponivel:
            raise ValueError("cardapio_publico.estoque_insuficiente")
        preco = Dinheiro(produto.preco)
        total_item = preco * solicitado.quantidade
        subtotal += total_item.valor
        itens_pedido.append(
            ItemPedido(
                id=PedidoItemId(_id_deterministico("item", f"{raiz}:{indice}")),
                tenant_id=TenantId(tenant_id),
                unidade_id=UnidadeId(unidade_id),
                produto_id=ProdutoId(produto.produto_id),
                nome_produto=produto.nome,
                quantidade=QuantidadeItem(solicitado.quantidade),
                preco_unitario=preco,
                subtotal=total_item,
                ficha_versao=str(produto.versao),
            )
        )

    total = Dinheiro(subtotal)
    pedido = Pedido.novo(
        id=PedidoId(_id_deterministico("ped", raiz)),
        tenant_id=TenantId(tenant_id),
        unidade_id=UnidadeId(unidade_id),
        origem=OrigemPedido.DELIVERY_PROPRIO,
        canal=CanalAtendimento.DELIVERY_PROPRIO,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=agora,
        atualizado_em=agora,
        versao=1,
        correlation_id=CorrelationId(_id_deterministico("cor", raiz)),
        idempotency_key=IdempotencyKey(raiz),
        subtotal=total,
        descontos=Dinheiro(0),
        taxas=Dinheiro(0),
        total=total,
        itens=tuple(itens_pedido),
    )
    contexto = ContextoExecucao(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id="cardapio-publico",
        papeis=frozenset(),
        permissoes=frozenset({Permissao.PEDIDO_CRIAR}),
        correlation_id=str(pedido.correlation_id),
        solicitado_em=agora,
        origem="cardapio_publico_autosservico_v1",
        unidades_permitidas=frozenset({unidade_id}),
    )
    comando = ComandoCheckoutV1(
        pedido=pedido,
        timestamp=agora,
        pagamento_id=_id_deterministico("pag", raiz) if total.valor > 0 else None,
        metodo_pagamento=metodo_pagamento if total.valor > 0 else None,
        recebimento_posterior=metodo_pagamento
        in {MetodoPagamento.PAGAMENTO_NA_ENTREGA, MetodoPagamento.RECEBIMENTO_POSTERIOR},
    )
    checkout = executar_checkout_v1(
        comando=comando,
        contexto=contexto,
        session_factory=session_factory,
    )
    return ResultadoAutosservicoV1(checkout=checkout, public_id=public_id)
