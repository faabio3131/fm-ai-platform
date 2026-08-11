"""Orquestração segura da Mica V1.

A IA interpreta intenção; somente services determinísticos resolvem catálogo, confirmação,
Pedido, Pagamento e handoff. Nenhum fallback inventa produto ou confirma dinheiro.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento

from .adapters import PortaHandoffMica, PortaPagamentosMica, PortaPedidosMica
from .erros import ErroMica
from .modelos import (
    CarrinhoMica,
    EstadoAtendimentoMica,
    IntencaoMica,
    ItemCarrinhoMica,
    PedidoSolicitadoMica,
    ProdutoCatalogoMica,
    ResultadoAtendimentoMica,
)
from .schemas import parse_intencao_mica


def _normalizar_nome(valor: str) -> str:
    return " ".join(valor.casefold().strip().split())


def _fingerprint(
    tenant_id: str,
    unidade_id: str,
    conversa_id: str,
    mensagem_id: str,
    itens: tuple[ItemCarrinhoMica, ...],
) -> str:
    payload = [
        tenant_id,
        unidade_id,
        conversa_id,
        mensagem_id,
        [(i.produto_id, i.quantidade, str(i.preco_unitario)) for i in itens],
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _mensagem_pagamento(status: PagamentoStatus) -> str:
    if status is PagamentoStatus.PAGO:
        return "Pedido confirmado e pagamento confirmado pela fonte financeira autorizada."
    if status is PagamentoStatus.AGUARDANDO_ENTREGA:
        return "Pedido confirmado. O pagamento permanece aguardando o recebimento na entrega."
    if status is PagamentoStatus.PARCIALMENTE_PAGO:
        return "Pedido confirmado. Há saldo financeiro pendente."
    if status in {PagamentoStatus.FALHOU, PagamentoStatus.CANCELADO}:
        return "Pedido confirmado, mas o pagamento exige atendimento humano."
    return "Pedido confirmado. Pagamento ainda pendente de confirmação financeira."


class ServicoMica:
    def __init__(
        self,
        *,
        pedidos: PortaPedidosMica,
        pagamentos: PortaPagamentosMica,
        handoff: PortaHandoffMica,
    ) -> None:
        self.pedidos = pedidos
        self.pagamentos = pagamentos
        self.handoff = handoff

    def _handoff(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        conversa_id: str,
        motivo: str,
    ) -> ResultadoAtendimentoMica:
        self.handoff.registrar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            conversa_id=conversa_id,
            motivo=motivo,
        )
        return ResultadoAtendimentoMica(
            estado=EstadoAtendimentoMica.HANDOFF_HUMANO,
            mensagem="Não vou adivinhar esse pedido. Encaminhei para atendimento humano.",
            handoff_motivo=motivo,
            auditoria=(("handoff", motivo),),
        )

    def interpretar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        conversa_id: str,
        mensagem_id: str,
        raw_ia: str,
        catalogo: Iterable[ProdutoCatalogoMica],
    ) -> ResultadoAtendimentoMica:
        if not all(x.strip() for x in (tenant_id, unidade_id, conversa_id, mensagem_id)):
            raise ErroMica("contexto_mica_invalido")
        try:
            intencao: IntencaoMica = parse_intencao_mica(raw_ia)
        except ErroMica as exc:
            return self._handoff(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                conversa_id=conversa_id,
                motivo=exc.codigo,
            )

        por_nome: dict[str, list[ProdutoCatalogoMica]] = {}
        for produto in catalogo:
            if (
                not produto.ativo
                or produto.tenant_id != tenant_id
                or produto.unidade_id != unidade_id
            ):
                continue
            por_nome.setdefault(_normalizar_nome(produto.nome), []).append(produto)

        itens: list[ItemCarrinhoMica] = []
        for solicitado in intencao.itens:
            candidatos = por_nome.get(_normalizar_nome(solicitado.nome_produto), [])
            if len(candidatos) != 1:
                return self._handoff(
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    conversa_id=conversa_id,
                    motivo="produto_nao_resolvido_exatamente",
                )
            produto = candidatos[0]
            itens.append(
                ItemCarrinhoMica(
                    produto_id=produto.produto_id,
                    nome_produto=produto.nome,
                    quantidade=solicitado.quantidade,
                    preco_unitario=produto.preco,
                )
            )

        itens_t = tuple(itens)
        carrinho = CarrinhoMica(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            conversa_id=conversa_id,
            mensagem_id=mensagem_id,
            itens=itens_t,
            fingerprint=_fingerprint(
                tenant_id, unidade_id, conversa_id, mensagem_id, itens_t
            ),
        )
        return ResultadoAtendimentoMica(
            estado=EstadoAtendimentoMica.AGUARDANDO_CONFIRMACAO,
            mensagem=(
                f"Carrinho validado com {len(itens_t)} item(ns), total R$ {carrinho.total:.2f}. "
                "Confirme explicitamente antes de criar o pedido."
            ),
            carrinho=carrinho,
            auditoria=(("schema", "valido"), ("catalogo", "resolucao_exata")),
        )

    def confirmar(
        self,
        *,
        resultado: ResultadoAtendimentoMica,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        confirmacao_cliente: bool,
        fingerprint_confirmado: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> ResultadoAtendimentoMica:
        carrinho = resultado.carrinho
        if resultado.estado is not EstadoAtendimentoMica.AGUARDANDO_CONFIRMACAO or carrinho is None:
            raise ErroMica("atendimento_nao_confirmavel")
        if carrinho.tenant_id != tenant_id or carrinho.unidade_id != unidade_id:
            raise ErroMica("recurso_indisponivel")
        if not confirmacao_cliente:
            raise ErroMica("confirmacao_cliente_obrigatoria")
        if fingerprint_confirmado != carrinho.fingerprint:
            raise ErroMica("carrinho_alterado_reconfirmacao_obrigatoria")
        if not cliente_ref.strip() or not idempotency_key.strip():
            raise ErroMica("identificador_obrigatorio")
        if metodo not in {
            MetodoPagamento.PIX,
            MetodoPagamento.DINHEIRO,
            MetodoPagamento.CARTAO_CREDITO,
            MetodoPagamento.CARTAO_DEBITO,
            MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        }:
            return self._handoff(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                conversa_id=carrinho.conversa_id,
                motivo="metodo_pagamento_nao_suportado",
            )

        solicitado = PedidoSolicitadoMica(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            carrinho=carrinho,
            cliente_ref=cliente_ref,
            idempotency_key=f"mica:pedido:{idempotency_key}",
        )
        pedido = self.pedidos.registrar_confirmado(solicitado)
        pagamento = self.pagamentos.criar_obrigacao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            pedido_id=pedido.pedido_id,
            valor=str(carrinho.total),
            metodo=metodo,
            idempotency_key=f"mica:pagamento:{idempotency_key}",
        )
        if pagamento.status in {PagamentoStatus.FALHOU, PagamentoStatus.CANCELADO}:
            self.handoff.registrar(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                conversa_id=carrinho.conversa_id,
                motivo="pagamento_exige_humano",
            )
        return ResultadoAtendimentoMica(
            estado=EstadoAtendimentoMica.PEDIDO_CONFIRMADO,
            mensagem=_mensagem_pagamento(pagamento.status),
            carrinho=carrinho,
            pedido=pedido,
            pagamento=pagamento,
            auditoria=(
                ("confirmacao_cliente", "explicita"),
                ("pedido", pedido.status),
                ("pagamento", pagamento.status.value),
            ),
        )
