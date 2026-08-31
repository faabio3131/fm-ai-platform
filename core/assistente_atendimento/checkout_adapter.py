"""Adapter canônico do Agente de Atendimento para application.checkout."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from application.checkout import (
    ComandoCheckoutV1,
    ResultadoCheckoutV1,
    executar_checkout_v1,
)
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
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
from core.dominio.pedidos import ItemPedido, ObservacaoPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao

from .atendimento_modelos import (
    CarrinhoAtendimento,
    ModalidadePedidoAtendimento,
    ResultadoCheckoutAssistente,
)
from .erros import ErroAssistenteAtendimento

ExecutorCheckout = Callable[..., ResultadoCheckoutV1]


def _id_deterministico(chave: str) -> str:
    return str(uuid5(NAMESPACE_URL, chave))


def _mapear_origem_canal(canal: str) -> tuple[OrigemPedido, CanalAtendimento]:
    normalizado = " ".join(canal.casefold().strip().split())

    if normalizado in {"whatsapp", "whatsapp_business"}:
        return OrigemPedido.WHATSAPP, CanalAtendimento.WHATSAPP

    raise ErroAssistenteAtendimento(
        "canal_checkout_nao_suportado",
        canal,
    )


def _recebimento_posterior(metodo: MetodoPagamento) -> bool:
    return metodo in {
        MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        MetodoPagamento.RECEBIMENTO_POSTERIOR,
    }


class CheckoutAssistenteV1:
    """Converte carrinho confirmado em Pedido V1 e usa o checkout autoritativo."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        executor: ExecutorCheckout = executar_checkout_v1,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._executor = executor
        self._agora = agora or (lambda: datetime.now(timezone.utc))

    def executar(
        self,
        *,
        contexto: ContextoExecucao,
        carrinho: CarrinhoAtendimento,
        cliente_ref: str,
        canal: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> ResultadoCheckoutAssistente:
        if (
            carrinho.tenant_id != contexto.tenant_id
            or carrinho.unidade_id != contexto.unidade_id
        ):
            raise ErroAssistenteAtendimento("carrinho_fora_do_contexto")

        if not cliente_ref.strip() or not idempotency_key.strip():
            raise ErroAssistenteAtendimento("identificador_checkout_obrigatorio")
        if carrinho.modalidade is ModalidadePedidoAtendimento.INDEFINIDA:
            raise ErroAssistenteAtendimento("modalidade_atendimento_invalida")
        if (
            carrinho.modalidade is ModalidadePedidoAtendimento.ENTREGA
            and carrinho.entrega is None
        ):
            raise ErroAssistenteAtendimento("entrega_nao_cotada")

        origem, canal_dominio = _mapear_origem_canal(canal)
        instante = self._agora()

        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ErroAssistenteAtendimento("timestamp_checkout_sem_timezone")

        chave_raiz = f"assistente:{idempotency_key}"
        pedido_id = _id_deterministico(
            f"{contexto.tenant_id}:{contexto.unidade_id}:{chave_raiz}:pedido"
        )

        tenant_id = TenantId(contexto.tenant_id)
        unidade_id = UnidadeId(contexto.unidade_id)

        if (
            carrinho.pagamento is not None
            and carrinho.pagamento.metodo is not metodo
        ):
            raise ErroAssistenteAtendimento(
                "forma_pagamento_divergente_do_carrinho"
            )

        itens: list[ItemPedido] = []

        for indice, item in enumerate(carrinho.itens, start=1):
            preco = Dinheiro(item.preco_unitario)
            subtotal = Dinheiro(
                item.preco_unitario * Decimal(item.quantidade)
            )

            itens.append(
                ItemPedido(
                    id=PedidoItemId(
                        _id_deterministico(
                            f"{pedido_id}:item:{indice}:{item.produto_id}"
                        )
                    ),
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    produto_id=ProdutoId(item.produto_id),
                    nome_produto=item.nome_produto,
                    quantidade=QuantidadeItem(item.quantidade),
                    preco_unitario=preco,
                    subtotal=subtotal,
                )
            )

        subtotal_pedido = Dinheiro(carrinho.subtotal)
        taxas_pedido = Dinheiro(carrinho.taxa_entrega)
        total_pedido = Dinheiro(carrinho.total)

        observacoes: tuple[ObservacaoPedido, ...] = ()
        if (
            carrinho.pagamento is not None
            and carrinho.pagamento.metodo is MetodoPagamento.DINHEIRO
            and carrinho.pagamento.valor_para_troco is not None
        ):
            try:
                troco_estimado = carrinho.pagamento.troco_estimado(carrinho.total)
            except ValueError as exc:
                raise ErroAssistenteAtendimento(
                    "valor_para_troco_invalido"
                ) from exc
            observacoes = (
                ObservacaoPedido(
                    id=_id_deterministico(f"{pedido_id}:observacao:troco"),
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    texto=(
                        "Troco solicitado para "
                        f"R$ {carrinho.pagamento.valor_para_troco:.2f}; "
                        f"estimativa R$ {troco_estimado:.2f}. "
                        "Pagamento ainda não confirmado."
                    ),
                    criado_em=instante,
                ),
            )

        pedido = Pedido.novo(
            id=PedidoId(pedido_id),
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            origem=origem,
            canal=canal_dominio,
            status=PedidoStatus.RASCUNHO,
            cliente_id=ClienteId(cliente_ref),
            criado_em=instante,
            atualizado_em=instante,
            versao=1,
            correlation_id=CorrelationId(contexto.correlation_id),
            idempotency_key=IdempotencyKey(f"{chave_raiz}:pedido"),
            subtotal=subtotal_pedido,
            descontos=Dinheiro(Decimal(0)),
            taxas=taxas_pedido,
            total=total_pedido,
            itens=tuple(itens),
            observacoes=observacoes,
        )

        pagamento_id = (
            _id_deterministico(
                f"{contexto.tenant_id}:{contexto.unidade_id}:"
                f"{chave_raiz}:pagamento"
            )
            if pedido.total.valor > 0
            else None
        )

        comando = ComandoCheckoutV1(
            pedido=pedido,
            timestamp=instante,
            pagamento_id=pagamento_id,
            metodo_pagamento=metodo if pedido.total.valor > 0 else None,
            snapshot_estoque=None,
            recebimento_posterior=_recebimento_posterior(metodo),
        )

        resultado = self._executor(
            comando=comando,
            contexto=contexto,
            session_factory=self._session_factory,
        )

        pagamento = resultado.pagamento

        return ResultadoCheckoutAssistente(
            pedido_id=str(resultado.aguardando_confirmacao.pedido.id),
            pedido_status=resultado.aguardando_confirmacao.pedido.status.value,
            pagamento_id=(
                str(pagamento.pagamento.id)
                if pagamento is not None
                else None
            ),
            pagamento_status=(
                pagamento.pagamento.status
                if pagamento is not None
                else None
            ),
            metodo_pagamento=(
                pagamento.pagamento.metodo
                if pagamento is not None
                else None
            ),
            idempotente=(
                resultado.pedido.idempotente
                and (
                    pagamento is None
                    or pagamento.idempotente
                )
            ),
        )
