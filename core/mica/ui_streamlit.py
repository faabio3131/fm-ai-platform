"""Interface Streamlit da Mica V1, atrás de flag fail-closed."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import uuid4

import streamlit as st

from core.pagamentos.modelos import MetodoPagamento

from .adapters import OperacaoMicaFake
from .erros import ErroMica
from .flags import assistente_atendimento_v1_enabled
from .modelos import (
    EstadoAtendimentoMica,
    ProdutoCatalogoMica,
    ResultadoAtendimentoMica,
)
from .servicos import ServicoMica


def _cliente_ref(telefone: str) -> str:
    return hashlib.sha256(telefone.strip().encode("utf-8")).hexdigest()


def _operacao() -> OperacaoMicaFake:
    chave = "_mica_v1_operacao"
    if chave not in st.session_state:
        st.session_state[chave] = OperacaoMicaFake()
    return st.session_state[chave]


def _servico() -> ServicoMica:
    operacao = _operacao()
    return ServicoMica(pedidos=operacao, pagamentos=operacao, handoff=operacao)


def _prompt(menu: str, mensagem: str, nome_publico: str) -> str:
    return f"""Você é {nome_publico}, o Assistente de Atendimento deste estabelecimento. Interprete sem inventar produtos.
Cardápio autorizado:
{menu}
Mensagem do cliente:
{mensagem}
Retorne SOMENTE JSON puro com exatamente estas chaves:
{{"cliente_nome":"nome ou Cliente WhatsApp","itens":[{{"nome_produto":"nome EXATO do cardápio","quantidade":1}}],"resposta_whatsapp":"resumo para conferência, sem afirmar pagamento"}}
Se não conseguir resolver um produto exatamente, retorne JSON ainda no schema usando o nome pedido pelo cliente; o sistema fará handoff humano.
"""


def render_mica_v1(
    *,
    session_factory: Callable[[], Any],
    produto_cls: Any,
    generate_content: Callable[..., Any],
    nome_publico: str = "Assistente de Atendimento",
) -> None:
    nome_publico = " ".join(nome_publico.split()) or "Assistente de Atendimento"
    st.header(f"💬 {nome_publico} — Atendimento seguro V1")
    if not assistente_atendimento_v1_enabled():
        st.info(
            "O Assistente de Atendimento está desativado neste ambiente. O fluxo legado de venda automática foi removido por segurança."
        )
        return

    tenant_id = os.getenv("FM_AI_TEST_TENANT", "tenant-e2e")
    unidade_id = os.getenv("FM_AI_TEST_UNIDADE", "unidade-e2e")
    db = session_factory()
    try:
        produtos = db.query(produto_cls).all()
        catalogo = tuple(
            ProdutoCatalogoMica(
                produto_id=str(produto.id),
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                nome=str(produto.nome),
                preco=Decimal(str(produto.preco_venda or 0)),
            )
            for produto in produtos
        )
    finally:
        db.close()

    if not catalogo:
        st.warning("Nenhum produto disponível. Atendimento humano necessário.")
        return

    menu = "\n".join(f"- {p.nome}: R$ {p.preco:.2f}" for p in catalogo)
    st.caption(
        "A IA interpreta a conversa, mas não escolhe pagamento, não confirma dinheiro, não baixa estoque e não cria Venda diretamente."
    )
    telefone = st.text_input("WhatsApp do cliente", value="5511999995432", key="mica_v1_tel")
    mensagem = st.text_area("Mensagem do cliente", key="mica_v1_msg")
    metodo_label = st.selectbox(
        "Forma de pagamento solicitada pelo cliente",
        ["Pix", "Dinheiro", "Cartão de crédito", "Cartão de débito", "Pagamento na entrega"],
        key="mica_v1_metodo",
    )
    metodos = {
        "Pix": MetodoPagamento.PIX,
        "Dinheiro": MetodoPagamento.DINHEIRO,
        "Cartão de crédito": MetodoPagamento.CARTAO_CREDITO,
        "Cartão de débito": MetodoPagamento.CARTAO_DEBITO,
        "Pagamento na entrega": MetodoPagamento.PAGAMENTO_NA_ENTREGA,
    }

    if st.button(f"Analisar pedido com {nome_publico}", type="primary", key="mica_v1_analisar"):
        if not telefone.strip() or not mensagem.strip():
            st.error("WhatsApp e mensagem são obrigatórios.")
        else:
            conversa_id = str(st.session_state.get("_mica_v1_conversa") or uuid4())
            st.session_state["_mica_v1_conversa"] = conversa_id
            mensagem_id = str(uuid4())
            try:
                resposta = generate_content(contents=_prompt(menu, mensagem, nome_publico))
                raw = str(resposta.text)
            except Exception:  # noqa: BLE001 - fronteira de provedor externo
                raw = "{resposta-invalida"
            resultado_analisado = _servico().interpretar(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                conversa_id=conversa_id,
                mensagem_id=mensagem_id,
                raw_ia=raw,
                catalogo=catalogo,
            )
            st.session_state["_mica_v1_resultado"] = resultado_analisado
            st.session_state["_mica_v1_idempotencia"] = str(uuid4())

    resultado = st.session_state.get("_mica_v1_resultado")
    if not isinstance(resultado, ResultadoAtendimentoMica):
        return
    if resultado.estado is EstadoAtendimentoMica.HANDOFF_HUMANO:
        st.warning(f"Atendimento humano solicitado: {resultado.handoff_motivo}")
        return
    if resultado.carrinho is None:
        return

    st.subheader("Conferência do carrinho")
    for item in resultado.carrinho.itens:
        st.write(f"{item.quantidade}x {item.nome_produto} — R$ {item.subtotal:.2f}")
    st.write(f"**Total: R$ {resultado.carrinho.total:.2f}**")
    st.warning("Nada foi cobrado nem enviado à produção ainda. Confirme o carrinho abaixo.")
    confirmado = st.checkbox(
        "Confirmo que o cliente revisou e aprovou exatamente este carrinho",
        key="mica_v1_confirmacao",
    )
    if st.button("Confirmar pedido", key="mica_v1_confirmar"):
        try:
            final = _servico().confirmar(
                resultado=resultado,
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                cliente_ref=_cliente_ref(telefone),
                confirmacao_cliente=confirmado,
                fingerprint_confirmado=resultado.carrinho.fingerprint,
                metodo=metodos[metodo_label],
                idempotency_key=str(st.session_state["_mica_v1_idempotencia"]),
            )
        except ErroMica as exc:
            st.error(f"Pedido não confirmado: {exc.codigo}")
            return
        st.session_state["_mica_v1_resultado"] = final
        st.success(final.mensagem)
        if final.pedido:
            st.write(f"Pedido: `{final.pedido.pedido_id}` — {final.pedido.status}")
        if final.pagamento:
            st.write(
                f"Pagamento: `{final.pagamento.pagamento_id}` — **{final.pagamento.status.value}**"
            )
