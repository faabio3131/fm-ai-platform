"""Interface cliente do Delivery Próprio V1, isolada e test-only nesta PR."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import streamlit as st

from core.pagamentos.modelos import MetodoPagamento

from .erros import ErroDelivery
from .flags import delivery_v1_enabled
from .modelos import EnderecoDelivery, EstagioCancelamento, StatusCarrinhoDelivery
from .runtime_teste import RuntimeDeliveryTeste


def _runtime() -> RuntimeDeliveryTeste:
    runtime = st.session_state.get("_delivery_runtime")
    if isinstance(runtime, RuntimeDeliveryTeste):
        return runtime
    runtime = RuntimeDeliveryTeste()
    st.session_state["_delivery_runtime"] = runtime
    return runtime


def _carrinho_atual(runtime: RuntimeDeliveryTeste):
    carrinho_id = st.session_state.get("_delivery_carrinho_id")
    if not isinstance(carrinho_id, str):
        carrinho_id = f"cart-ui-{uuid4().hex[:12]}"
        runtime.servico.abrir_carrinho(
            carrinho_id=carrinho_id,
            tenant_id="tenant-demo",
            unidade_id="unidade-demo",
            cliente_ref="cliente-demo",
        )
        st.session_state["_delivery_carrinho_id"] = carrinho_id
    carrinho = runtime.carrinhos.obter(
        tenant_id="tenant-demo",
        unidade_id="unidade-demo",
        carrinho_id=carrinho_id,
    )
    if carrinho is None:
        raise ErroDelivery("carrinho_ui_ausente")
    return carrinho


def _executar(acao):
    try:
        return acao()
    except ErroDelivery as exc:
        st.error(f"Não foi possível concluir: {exc.codigo}")
        return None


def render_delivery_v1(*, runtime: RuntimeDeliveryTeste | None = None) -> None:
    """Renderiza a jornada completa do canal próprio em runtime seguro de teste."""
    if not delivery_v1_enabled():
        st.info("Delivery Próprio V1 está desabilitado neste ambiente.")
        return

    runtime = runtime or _runtime()
    carrinho = _carrinho_atual(runtime)

    st.header("🛵 Delivery Próprio")
    st.caption(
        "Catálogo, carrinho, área de entrega, taxa/SLA, promoções, pagamento e tracking."
    )

    if carrinho.status is StatusCarrinhoDelivery.ABERTO:
        st.subheader("1. Cardápio")
        cols = st.columns(len(runtime.catalogo))
        for col, produto in zip(cols, runtime.catalogo, strict=True):
            with col:
                st.markdown(f"**{produto.nome}**")
                st.write(f"R$ {produto.preco:.2f}")
                st.caption(f"Disponível: {produto.estoque_disponivel}")
                if st.button(
                    f"Adicionar {produto.nome}",
                    key=f"delivery_add_{produto.produto_id}",
                    use_container_width=True,
                ):
                    novo = _executar(
                        lambda p=produto: runtime.servico.adicionar_item(
                            tenant_id="tenant-demo",
                            unidade_id="unidade-demo",
                            carrinho_id=carrinho.carrinho_id,
                            produto_id=p.produto_id,
                            quantidade=1,
                            expected_version=carrinho.versao,
                            catalogo=runtime.catalogo,
                        )
                    )
                    if novo is not None:
                        st.session_state["_delivery_flash"] = f"{produto.nome} adicionado."
                        st.rerun()

        flash = st.session_state.pop("_delivery_flash", None)
        if flash:
            st.success(str(flash))

        carrinho = _carrinho_atual(runtime)
        st.subheader("2. Carrinho")
        if not carrinho.itens:
            st.info("Seu carrinho está vazio.")
        else:
            for item in carrinho.itens:
                st.write(f"{item.quantidade}x {item.nome} — R$ {item.subtotal:.2f}")
            st.metric("Subtotal", f"R$ {carrinho.subtotal:.2f}")

        st.subheader("3. Endereço e entrega")
        with st.form("delivery_endereco"):
            cep = st.text_input("CEP", value="01001000")
            logradouro = st.text_input("Logradouro", value="Praça da Sé")
            numero = st.text_input("Número", value="100")
            bairro = st.text_input("Bairro", value="Sé")
            cidade = st.text_input("Cidade", value="São Paulo")
            uf = st.text_input("UF", value="SP")
            calcular = st.form_submit_button("Calcular entrega", type="primary")
        if calcular:
            endereco = _executar(
                lambda: EnderecoDelivery(
                    endereco_id=f"end-{carrinho.carrinho_id}",
                    cliente_ref="cliente-demo",
                    cep=cep,
                    logradouro=logradouro,
                    numero=numero,
                    bairro=bairro,
                    cidade=cidade,
                    uf=uf,
                )
            )
            if endereco is not None:
                novo = _executar(
                    lambda: runtime.servico.definir_endereco(
                        tenant_id="tenant-demo",
                        unidade_id="unidade-demo",
                        carrinho_id=carrinho.carrinho_id,
                        endereco=endereco,
                        expected_version=carrinho.versao,
                        areas=runtime.areas,
                    )
                )
                if novo is not None:
                    st.success(
                        f"Entrega: R$ {novo.taxa_entrega:.2f} — "
                        f"{novo.cotacao.sla_minutos}-{novo.cotacao.sla_maxutos} min"
                    )
                    st.rerun()

        carrinho = _carrinho_atual(runtime)
        if carrinho.cotacao:
            st.success(
                f"Área {carrinho.cotacao.nome_area}: taxa R$ {carrinho.taxa_entrega:.2f}, "
                f"SLA {carrinho.cotacao.sla_minutos}-{carrinho.cotacao.sla_maxutos} min."
            )

        st.subheader("4. Benefícios")
        col_cupom, col_cashback = st.columns(2)
        with col_cupom:
            with st.form("delivery_cupom"):
                codigo = st.text_input("Cupom", value="BEMVINDO10")
                aplicar = st.form_submit_button("Aplicar cupom")
            if aplicar:
                novo = _executar(
                    lambda: runtime.servico.aplicar_cupom(
                        tenant_id="tenant-demo",
                        unidade_id="unidade-demo",
                        carrinho_id=carrinho.carrinho_id,
                        codigo=codigo,
                        expected_version=carrinho.versao,
                        cupons=runtime.cupons,
                    )
                )
                if novo is not None:
                    st.success(f"Cupom aplicado: -R$ {novo.desconto_cupom:.2f}")
                    st.rerun()
        carrinho = _carrinho_atual(runtime)
        with col_cashback:
            saldo = runtime.promocoes.saldo_cashback(
                tenant_id="tenant-demo",
                unidade_id="unidade-demo",
                cliente_ref="cliente-demo",
            )
            st.caption(f"Cashback disponível: R$ {saldo:.2f}")
            with st.form("delivery_cashback"):
                valor = st.number_input(
                    "Usar cashback (R$)", min_value=0.0, value=5.0, step=1.0
                )
                usar = st.form_submit_button("Reservar cashback")
            if usar:
                novo = _executar(
                    lambda: runtime.servico.reservar_cashback(
                        tenant_id="tenant-demo",
                        unidade_id="unidade-demo",
                        carrinho_id=carrinho.carrinho_id,
                        valor_desejado=Decimal(str(valor)),
                        expected_version=carrinho.versao,
                    )
                )
                if novo is not None:
                    st.success(f"Cashback reservado: R$ {novo.cashback_reservado:.2f}")
                    st.rerun()

        carrinho = _carrinho_atual(runtime)
        st.subheader("5. Fechamento")
        st.write(f"Desconto cupom: R$ {carrinho.desconto_cupom:.2f}")
        st.write(f"Cashback: R$ {carrinho.cashback_reservado:.2f}")
        st.metric("Total do pedido", f"R$ {carrinho.total:.2f}")
        labels = {
            "Pix": MetodoPagamento.PIX,
            "Cartão de crédito": MetodoPagamento.CARTAO_CREDITO,
            "Cartão de débito": MetodoPagamento.CARTAO_DEBITO,
            "Pagamento na entrega": MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        }
        metodo_label = st.selectbox("Forma de pagamento", list(labels))
        if st.button("Confirmar pedido", type="primary", use_container_width=True):
            idem = f"ui-confirm-{carrinho.carrinho_id}"
            resultado = _executar(
                lambda: runtime.servico.confirmar(
                    tenant_id="tenant-demo",
                    unidade_id="unidade-demo",
                    carrinho_id=carrinho.carrinho_id,
                    expected_version=carrinho.versao,
                    metodo_pagamento=labels[metodo_label],
                    idempotency_key=idem,
                    catalogo=runtime.catalogo,
                    areas=runtime.areas,
                )
            )
            if resultado is not None:
                st.session_state["_delivery_pedido_id"] = resultado.pedido.pedido_id
                st.success("Pedido confirmado com segurança.")
                st.rerun()

    pedido_id = st.session_state.get("_delivery_pedido_id")
    if isinstance(pedido_id, str):
        pedido = runtime.pedidos.obter(
            tenant_id="tenant-demo",
            unidade_id="unidade-demo",
            pedido_id=pedido_id,
        )
        if pedido is not None:
            st.subheader("Pedido confirmado")
            st.write(f"Pedido: `{pedido.pedido_id}`")
            st.metric("Total", f"R$ {pedido.total:.2f}")
            st.write(f"Pagamento: **{pedido.pagamento.status.value}**")
            st.write(
                "O canal nunca considera Pix/cartão pago sem confirmação da fonte financeira."
            )

            st.subheader("Acompanhar pedido")
            timeline = _executar(
                lambda: runtime.servico.acompanhar(
                    tenant_id="tenant-demo",
                    unidade_id="unidade-demo",
                    cliente_ref="cliente-demo",
                    pedido_id=pedido.pedido_id,
                )
            )
            if timeline:
                for evento in timeline:
                    st.write(f"• {evento.status.value}: {evento.mensagem}")

            if pedido.status.value != "cancelado":
                with st.expander("Cancelar pedido"):
                    motivo = st.text_input(
                        "Motivo do cancelamento", value="Solicitação do cliente"
                    )
                    if st.button("Cancelar pedido agora"):
                        resultado_cancel = _executar(
                            lambda: runtime.servico.cancelar(
                                tenant_id="tenant-demo",
                                unidade_id="unidade-demo",
                                cliente_ref="cliente-demo",
                                pedido_id=pedido.pedido_id,
                                estagio=EstagioCancelamento.ANTES_PRODUCAO,
                                motivo=motivo,
                                idempotency_key=f"ui-cancel-{pedido.pedido_id}",
                            )
                        )
                        if resultado_cancel is not None:
                            st.success(
                                "Pedido cancelado. Benefícios reservados foram reconciliados."
                            )
                            st.rerun()
            else:
                st.warning("Pedido cancelado.")

            if st.button("Repetir este pedido"):
                novo_id = f"cart-repeat-{uuid4().hex[:10]}"
                novo = _executar(
                    lambda: runtime.servico.repetir(
                        tenant_id="tenant-demo",
                        unidade_id="unidade-demo",
                        cliente_ref="cliente-demo",
                        pedido_id=pedido.pedido_id,
                        novo_carrinho_id=novo_id,
                        catalogo=runtime.catalogo,
                        areas=runtime.areas,
                    )
                )
                if novo is not None:
                    st.session_state["_delivery_carrinho_id"] = novo.carrinho_id
                    st.session_state.pop("_delivery_pedido_id", None)
                    st.success(
                        "Carrinho reconstruído com catálogo, preço, estoque, taxa e SLA atuais."
                    )
                    st.rerun()
