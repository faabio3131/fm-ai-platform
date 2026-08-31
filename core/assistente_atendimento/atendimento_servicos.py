"""Orquestração determinística do Agente Inteligente de Atendimento V1.

A IA interpreta linguagem; este serviço valida contexto, catálogo, cliente,
confirmação e autorização de efeitos. Nenhum dado comercial é inventado aqui.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from core.pagamentos.modelos import MetodoPagamento

from .atendimento_adapters import PortaCheckoutAssistente, PortaHandoffAssistente
from .atendimento_modelos import (
    CarrinhoAtendimento,
    EstadoAtendimento,
    IntencaoAtendimento,
    ItemCarrinhoAtendimento,
    ProdutoCatalogoAtendimento,
    ResultadoAtendimento,
)
from .atendimento_schemas import parse_intencao_atendimento
from .contexto import ContextoAtendimento, TipoClienteAtendimento
from .entradas import EntradaAtendimento
from .erros import ErroAssistenteAtendimento


def _normalizar_nome(valor: str) -> str:
    return " ".join(valor.casefold().strip().split())


def _fingerprint(
    *,
    tenant_id: str,
    unidade_id: str,
    conversa_id: str,
    mensagem_id: str,
    itens: tuple[ItemCarrinhoAtendimento, ...],
) -> str:
    payload = [
        tenant_id,
        unidade_id,
        conversa_id,
        mensagem_id,
        [
            (item.produto_id, item.quantidade, str(item.preco_unitario))
            for item in itens
        ],
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class ServicoAssistenteAtendimento:
    def __init__(
        self,
        *,
        checkout: PortaCheckoutAssistente,
        handoff: PortaHandoffAssistente,
    ) -> None:
        self.checkout = checkout
        self.handoff = handoff

    def _handoff(
        self,
        *,
        contexto: ContextoAtendimento,
        motivo: str,
    ) -> ResultadoAtendimento:
        self.handoff.registrar(
            contexto=contexto.contexto_execucao,
            conversa_id=contexto.conversa_id,
            motivo=motivo,
        )
        return ResultadoAtendimento(
            estado=EstadoAtendimento.HANDOFF_HUMANO,
            mensagem=(
                "Não consegui concluir esse atendimento com segurança. "
                "Vou encaminhar para atendimento humano."
            ),
            handoff_motivo=motivo,
            auditoria=(("handoff", motivo),),
        )

    def interpretar(
        self,
        *,
        contexto: ContextoAtendimento,
        entrada: EntradaAtendimento,
        raw_ia: str,
        catalogo: Iterable[ProdutoCatalogoAtendimento],
    ) -> ResultadoAtendimento:
        if (
            contexto.tenant_id != contexto.contexto_execucao.tenant_id
            or contexto.unidade_id != contexto.contexto_execucao.unidade_id
        ):
            raise ErroAssistenteAtendimento("contexto_atendimento_invalido")

        try:
            intencao: IntencaoAtendimento = parse_intencao_atendimento(raw_ia)
        except ErroAssistenteAtendimento as exc:
            return self._handoff(contexto=contexto, motivo=exc.codigo)

        por_nome: dict[str, list[ProdutoCatalogoAtendimento]] = {}
        for produto in catalogo:
            if (
                not produto.ativo
                or produto.tenant_id != contexto.tenant_id
                or produto.unidade_id != contexto.unidade_id
            ):
                continue
            por_nome.setdefault(_normalizar_nome(produto.nome), []).append(produto)

        itens: list[ItemCarrinhoAtendimento] = []
        for solicitado in intencao.itens:
            candidatos = por_nome.get(_normalizar_nome(solicitado.nome_produto), [])
            if len(candidatos) != 1:
                return self._handoff(
                    contexto=contexto,
                    motivo="produto_nao_resolvido_exatamente",
                )
            produto = candidatos[0]
            itens.append(
                ItemCarrinhoAtendimento(
                    produto_id=produto.produto_id,
                    nome_produto=produto.nome,
                    quantidade=solicitado.quantidade,
                    preco_unitario=produto.preco,
                )
            )

        itens_t = tuple(itens)
        carrinho = CarrinhoAtendimento(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            conversa_id=contexto.conversa_id,
            mensagem_id=entrada.mensagem_id,
            itens=itens_t,
            fingerprint=_fingerprint(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                conversa_id=contexto.conversa_id,
                mensagem_id=entrada.mensagem_id,
                itens=itens_t,
            ),
        )

        if contexto.cliente.tipo is TipoClienteAtendimento.NOVO:
            return ResultadoAtendimento(
                estado=EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE,
                mensagem=(
                    f"Entendi o pedido, total R$ {carrinho.total:.2f}. "
                    "Antes de confirmar, preciso concluir os dados necessários "
                    "do novo cliente."
                ),
                carrinho=carrinho,
                auditoria=(
                    ("schema", "valido"),
                    ("catalogo", "resolucao_exata"),
                    ("cliente", "novo"),
                ),
            )

        return ResultadoAtendimento(
            estado=EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE,
            mensagem=(
                f"Pedido interpretado e validado com {len(itens_t)} item(ns), "
                f"total R$ {carrinho.total:.2f}. "
                "Confirme explicitamente antes de concluir o checkout."
            ),
            carrinho=carrinho,
            auditoria=(
                ("schema", "valido"),
                ("catalogo", "resolucao_exata"),
                ("cliente", "conhecido"),
            ),
        )

    def concluir_cadastro_cliente(
        self,
        *,
        contexto_anterior: ContextoAtendimento,
        resultado: ResultadoAtendimento,
        cliente_ref: str,
    ) -> tuple[ContextoAtendimento, ResultadoAtendimento]:
        """Promove cliente novo já persistido sem repetir a interpretação da IA."""

        if (
            resultado.estado is not EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE
            or resultado.carrinho is None
        ):
            raise ErroAssistenteAtendimento("cadastro_cliente_fora_de_estado")
        if not cliente_ref.strip():
            raise ErroAssistenteAtendimento("cliente_ref_obrigatorio")

        from .contexto import ClienteAtendimento

        novo_contexto = ContextoAtendimento(
            contexto_execucao=contexto_anterior.contexto_execucao,
            conversa_id=contexto_anterior.conversa_id,
            canal=contexto_anterior.canal,
            cliente=ClienteAtendimento(
                tipo=TipoClienteAtendimento.CONHECIDO,
                cliente_ref=cliente_ref.strip(),
            ),
        )
        atualizado = ResultadoAtendimento(
            estado=EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE,
            mensagem=(
                "Cliente registrado no CRM canônico. "
                "Revise o carrinho e confirme explicitamente antes do checkout."
            ),
            carrinho=resultado.carrinho,
            auditoria=(
                *resultado.auditoria,
                ("cliente", "registrado_crm_canonico"),
            ),
        )
        return novo_contexto, atualizado

    def confirmar(
        self,
        *,
        contexto: ContextoAtendimento,
        resultado: ResultadoAtendimento,
        confirmacao_cliente: bool,
        fingerprint_confirmado: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> ResultadoAtendimento:
        carrinho = resultado.carrinho

        if (
            resultado.estado
            is not EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE
            or carrinho is None
        ):
            raise ErroAssistenteAtendimento("atendimento_nao_confirmavel")

        if (
            carrinho.tenant_id != contexto.tenant_id
            or carrinho.unidade_id != contexto.unidade_id
        ):
            raise ErroAssistenteAtendimento("recurso_indisponivel")

        if contexto.cliente.tipo is not TipoClienteAtendimento.CONHECIDO:
            raise ErroAssistenteAtendimento(
                "cliente_novo_exige_cadastro_antes_do_checkout"
            )

        cliente_ref = contexto.cliente.cliente_ref
        if cliente_ref is None or not cliente_ref.strip():
            raise ErroAssistenteAtendimento("cliente_ref_obrigatorio")

        if not confirmacao_cliente:
            raise ErroAssistenteAtendimento("confirmacao_cliente_obrigatoria")

        if fingerprint_confirmado != carrinho.fingerprint:
            raise ErroAssistenteAtendimento(
                "carrinho_alterado_reconfirmacao_obrigatoria"
            )

        if not idempotency_key.strip():
            raise ErroAssistenteAtendimento("idempotency_key_obrigatoria")

        checkout = self.checkout.executar(
            contexto=contexto.contexto_execucao,
            carrinho=carrinho,
            cliente_ref=cliente_ref,
            canal=contexto.canal,
            metodo=metodo,
            idempotency_key=idempotency_key,
        )

        return ResultadoAtendimento(
            estado=EstadoAtendimento.CHECKOUT_REGISTRADO,
            mensagem=(
                "Pedido enviado ao fluxo autoritativo. "
                "O status de pagamento deve ser acompanhado pela fonte "
                "financeira oficial."
            ),
            carrinho=carrinho,
            checkout=checkout,
            auditoria=(
                ("confirmacao_cliente", "explicita"),
                ("checkout", "autoritativo"),
                ("pedido", checkout.pedido_status),
            ),
        )
