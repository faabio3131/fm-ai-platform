"""Orquestração determinística do Agente Inteligente de Atendimento V1.

A IA interpreta linguagem; este serviço valida contexto, catálogo, cliente,
confirmação e autorização de efeitos. Nenhum dado comercial é inventado aqui.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable
from dataclasses import replace
from decimal import Decimal

from core.pagamentos.modelos import MetodoPagamento

from .atendimento_adapters import PortaCheckoutAssistente, PortaHandoffAssistente
from .atendimento_modelos import (
    CarrinhoAtendimento,
    CotacaoEntregaAtendimento,
    EstadoAtendimento,
    IntencaoAtendimento,
    ItemCarrinhoAtendimento,
    ModalidadePedidoAtendimento,
    PreferenciaPagamentoAtendimento,
    ProdutoCatalogoAtendimento,
    ResultadoAtendimento,
    SugestaoProdutoAtendimento,
)
from .atendimento_schemas import parse_intencao_atendimento
from .contexto import ContextoAtendimento, TipoClienteAtendimento
from .entradas import EntradaAtendimento
from .erros import ErroAssistenteAtendimento


def _normalizar_nome(valor: str) -> str:
    return " ".join(valor.casefold().strip().split())


def _classe_produto(nome: str) -> str | None:
    """Classificação conservadora; nunca inventa itens fora do catálogo."""
    texto = "".join(
        ch for ch in unicodedata.normalize("NFKD", nome.casefold())
        if not unicodedata.combining(ch)
    )
    # Sem verificação de idade, não sugerir álcool automaticamente.
    if any(p in texto for p in ("cerveja", "vinho", "vodka", "whisky", "licor", "chopp", "caipirinha")):
        return None
    if any(p in texto for p in ("refrigerante", "suco", "agua ", "agua mineral", "coca", "guarana", "shake", "bebida")):
        return "bebida"
    if any(p in texto for p in ("batata", "frita", "nugget", "anel de cebola", "porcao", "acompanhamento")):
        return "acompanhamento"
    if any(p in texto for p in ("sobremesa", "brownie", "pudim", "sorvete", "mousse", "brigadeiro")):
        return "sobremesa"
    if any(p in texto for p in ("burger", "hamburg", "x-bacon", "x-salada", "sanduiche", "lanche", "pizza")):
        return "principal"
    return None


def _sugerir_complemento(
    *,
    carrinho: CarrinhoAtendimento,
    catalogo: Iterable[ProdutoCatalogoAtendimento],
) -> SugestaoProdutoAtendimento | None:
    """No máximo uma oferta verificável por pedido; jamais inclui item sem aceite."""
    no_pedido = {item.produto_id for item in carrinho.itens}
    catalogo = tuple(catalogo)
    # Upsell genuíno: apenas variante superior do MESMO item, sem inferir
    # equivalência entre produtos diferentes. Não trocar múltiplas unidades.
    for item in carrinho.itens:
        if item.quantidade != 1 or _classe_produto(item.nome_produto) != "principal":
            continue
        nome_base = _normalizar_nome(item.nome_produto)
        variantes = [
            p for p in catalogo
            if p.ativo and p.tenant_id == carrinho.tenant_id
            and p.unidade_id == carrinho.unidade_id
            and p.produto_id not in no_pedido and p.preco > item.preco_unitario
            and _normalizar_nome(p.nome).startswith(nome_base + " ")
            and any(palavra in _normalizar_nome(p.nome)[len(nome_base):]
                    for palavra in ("duplo", "grande", "premium", "gigante"))
        ]
        if variantes:
            superior = min(variantes, key=lambda p: (p.preco, p.produto_id))
            return SugestaoProdutoAtendimento(
                produto_id=superior.produto_id,
                nome=superior.nome,
                preco=superior.preco,
                tipo="upsell",
                substitui_produto_id=item.produto_id,
            )
    classes_no_pedido = {_classe_produto(item.nome_produto) for item in carrinho.itens}
    if "principal" in classes_no_pedido:
        prioridades = ("bebida", "acompanhamento", "sobremesa")
    elif "acompanhamento" in classes_no_pedido:
        prioridades = ("bebida", "principal", "sobremesa")
    elif "bebida" in classes_no_pedido:
        prioridades = ("principal", "acompanhamento", "sobremesa")
    else:
        return None
    elegiveis = [
        p for p in catalogo
        if p.ativo and p.tenant_id == carrinho.tenant_id
        and p.unidade_id == carrinho.unidade_id
        and p.produto_id not in no_pedido
        and p.preco > 0
        and _classe_produto(p.nome) not in classes_no_pedido
    ]
    for categoria in prioridades:
        candidatos = [p for p in elegiveis if _classe_produto(p.nome) == categoria]
        if candidatos:
            candidato = min(candidatos, key=lambda p: (p.preco, p.produto_id))
            return SugestaoProdutoAtendimento(
                produto_id=candidato.produto_id,
                nome=candidato.nome,
                preco=candidato.preco,
            )
    return None


def _mensagem_oferta(oferta: SugestaoProdutoAtendimento) -> str:
    if oferta.tipo == "upsell":
        return (
            f"Quer trocar seu item pela versão {oferta.nome}, "
            f"por R$ {oferta.preco:.2f}? Responda sim para trocar ou não para manter."
        )
    return (
        f"Posso sugerir {oferta.nome} por R$ {oferta.preco:.2f} "
        "para acompanhar seu pedido? Responda sim para adicionar ou não para seguir."
    )


def _fingerprint(
    *,
    tenant_id: str,
    unidade_id: str,
    conversa_id: str,
    mensagem_id: str,
    itens: tuple[ItemCarrinhoAtendimento, ...],
    modalidade: ModalidadePedidoAtendimento,
    entrega: CotacaoEntregaAtendimento | None = None,
    pagamento: PreferenciaPagamentoAtendimento | None = None,
) -> str:
    entrega_payload = None
    if entrega is not None:
        entrega_payload = (
            entrega.place_id,
            entrega.cep,
            entrega.distancia_metros,
            entrega.eta_rota_minutos,
            entrega.area_id,
            str(entrega.taxa),
            entrega.sla_minutos,
            entrega.sla_maxutos,
            entrega.versao_area,
        )
    pagamento_payload = None
    if pagamento is not None:
        pagamento_payload = (
            pagamento.metodo.value,
            (
                str(pagamento.valor_para_troco)
                if pagamento.valor_para_troco is not None
                else None
            ),
        )
    payload = [
        tenant_id,
        unidade_id,
        conversa_id,
        mensagem_id,
        modalidade.value,
        [
            (item.produto_id, item.quantidade, str(item.preco_unitario))
            for item in itens
        ],
        entrega_payload,
        pagamento_payload,
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _estado_operacional(carrinho: CarrinhoAtendimento) -> EstadoAtendimento:
    if carrinho.modalidade is ModalidadePedidoAtendimento.INDEFINIDA:
        return EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA
    if (
        carrinho.modalidade is ModalidadePedidoAtendimento.ENTREGA
        and carrinho.entrega is None
    ):
        return EstadoAtendimento.AGUARDANDO_ENDERECO_ENTREGA
    if carrinho.pagamento is None:
        return EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO
    return EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE


def _mensagem_operacional(carrinho: CarrinhoAtendimento) -> str:
    estado = _estado_operacional(carrinho)
    if estado is EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA:
        return "Confirme se o pedido será para retirada ou entrega antes do checkout."
    if estado is EstadoAtendimento.AGUARDANDO_ENDERECO_ENTREGA:
        return (
            "O pedido é para entrega. Informe/confirme o endereço e CEP para "
            "validar área, taxa, rota e ETA antes do checkout."
        )
    if estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO:
        return (
            f"Pedido validado, total R$ {carrinho.total:.2f}. "
            "Defina a forma de pagamento e, se for dinheiro, informe se precisa "
            "de troco antes da confirmação final."
        )
    return (
        f"Pedido validado, total R$ {carrinho.total:.2f}. "
        "Confirme explicitamente o carrinho final e a forma de pagamento antes "
        "do checkout."
    )


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
        snapshot_seguro: dict[str, str | int | bool] | None = None,
    ) -> ResultadoAtendimento:
        metadata: dict[str, str | int | bool] = {
            "cliente_tipo": contexto.cliente.tipo.value,
            "cliente_ref": contexto.cliente.cliente_ref or "novo",
        }
        customer_context = contexto.customer_context
        if customer_context is not None:
            metadata.update(
                {
                    "historico_count": len(customer_context.historico),
                    "possui_endereco_salvo": customer_context.possui_endereco_salvo,
                    "consentimentos_count": len(customer_context.consentimentos),
                }
            )
            if customer_context.historico:
                metadata["ultimo_pedido_id"] = customer_context.historico[0].pedido_id
        if snapshot_seguro:
            metadata.update(snapshot_seguro)
        self.handoff.registrar(
            contexto=contexto.contexto_execucao,
            conversa_id=contexto.conversa_id,
            motivo=motivo,
            metadata_segura=metadata,
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

        catalogo = tuple(catalogo)
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
                    snapshot_seguro={
                        "modalidade": intencao.modalidade.value,
                        "itens_solicitados": len(intencao.itens),
                        "itens_resolvidos": len(itens),
                    },
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
                modalidade=intencao.modalidade,
            ),
            modalidade=intencao.modalidade,
            endereco_solicitado=intencao.endereco_texto,
        )

        oferta = _sugerir_complemento(carrinho=carrinho, catalogo=catalogo)

        if contexto.cliente.tipo is TipoClienteAtendimento.NOVO:
            return ResultadoAtendimento(
                estado=EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE,
                mensagem=(
                    f"Entendi o pedido, subtotal R$ {carrinho.subtotal:.2f}. "
                    "Antes de confirmar, preciso concluir os dados necessários "
                    "do novo cliente."
                ),
                carrinho=carrinho,
                sugestao=oferta,
                auditoria=(
                    ("schema", "valido"),
                    ("catalogo", "resolucao_exata"),
                    ("cliente", "novo"),
                    ("modalidade", carrinho.modalidade.value),
                ),
            )

        estado = (
            EstadoAtendimento.AGUARDANDO_RESPOSTA_OFERTA
            if oferta is not None else _estado_operacional(carrinho)
        )
        return ResultadoAtendimento(
            estado=estado,
            mensagem=_mensagem_oferta(oferta) if oferta is not None else _mensagem_operacional(carrinho),
            carrinho=carrinho,
            sugestao=oferta,
            auditoria=(
                ("schema", "valido"),
                ("catalogo", "resolucao_exata"),
                ("cliente", "conhecido"),
                ("modalidade", carrinho.modalidade.value),
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
        oferta = resultado.sugestao
        estado = (
            EstadoAtendimento.AGUARDANDO_RESPOSTA_OFERTA
            if oferta is not None else _estado_operacional(resultado.carrinho)
        )
        atualizado = ResultadoAtendimento(
            estado=estado,
            mensagem=(
                "Cliente registrado no CRM canônico. "
                + (_mensagem_oferta(oferta) if oferta is not None
                   else _mensagem_operacional(resultado.carrinho))
            ),
            carrinho=resultado.carrinho,
            sugestao=oferta,
            auditoria=(
                *resultado.auditoria,
                ("cliente", "registrado_crm_canonico"),
            ),
        )
        return novo_contexto, atualizado

    def responder_oferta(
        self,
        *,
        contexto: ContextoAtendimento,
        resultado: ResultadoAtendimento,
        aceitar: bool,
        catalogo: Iterable[ProdutoCatalogoAtendimento],
    ) -> ResultadoAtendimento:
        """Aceite/rejeição explícitos, com recotação canônica antes de adicionar."""
        carrinho = resultado.carrinho
        oferta = resultado.sugestao
        if (
            resultado.estado is not EstadoAtendimento.AGUARDANDO_RESPOSTA_OFERTA
            or carrinho is None or oferta is None
        ):
            raise ErroAssistenteAtendimento("oferta_fora_de_estado")
        if carrinho.tenant_id != contexto.tenant_id or carrinho.unidade_id != contexto.unidade_id:
            raise ErroAssistenteAtendimento("recurso_indisponivel")
        if not aceitar:
            return ResultadoAtendimento(
                estado=_estado_operacional(carrinho),
                mensagem="Tudo bem, seguimos com seu pedido. " + _mensagem_operacional(carrinho),
                carrinho=carrinho,
                auditoria=(*resultado.auditoria, ("oferta", "recusada")),
            )
        produto = next(
            (p for p in catalogo if p.produto_id == oferta.produto_id
             and p.ativo and p.tenant_id == contexto.tenant_id
             and p.unidade_id == contexto.unidade_id and p.preco > 0),
            None,
        )
        if produto is None or any(item.produto_id == oferta.produto_id for item in carrinho.itens):
            return ResultadoAtendimento(
                estado=_estado_operacional(carrinho),
                mensagem="O complemento não está mais disponível. " + _mensagem_operacional(carrinho),
                carrinho=carrinho,
                auditoria=(*resultado.auditoria, ("oferta", "indisponivel")),
            )
        if produto.preco != oferta.preco:
            return ResultadoAtendimento(
                estado=_estado_operacional(carrinho),
                mensagem="O preço do complemento mudou; não adicionei o item. "
                        + _mensagem_operacional(carrinho),
                carrinho=carrinho,
                auditoria=(*resultado.auditoria, ("oferta", "preco_alterado")),
            )
        novo_item = ItemCarrinhoAtendimento(
            produto_id=produto.produto_id,
            nome_produto=produto.nome,
            quantidade=1,
            preco_unitario=produto.preco,
        )
        if oferta.tipo == "upsell":
            substituido = [
                item for item in carrinho.itens
                if item.produto_id == oferta.substitui_produto_id and item.quantidade == 1
            ]
            if len(substituido) != 1:
                raise ErroAssistenteAtendimento("upsell_item_original_indisponivel")
            itens = tuple(
                novo_item if item.produto_id == oferta.substitui_produto_id else item
                for item in carrinho.itens
            )
        else:
            itens = (*carrinho.itens, novo_item)
        novo_carrinho = replace(
            carrinho,
            itens=itens,
            pagamento=None,
            fingerprint=_fingerprint(
                tenant_id=carrinho.tenant_id,
                unidade_id=carrinho.unidade_id,
                conversa_id=carrinho.conversa_id,
                mensagem_id=carrinho.mensagem_id,
                itens=itens,
                modalidade=carrinho.modalidade,
                entrega=carrinho.entrega,
            ),
        )
        return ResultadoAtendimento(
            estado=_estado_operacional(novo_carrinho),
            mensagem=(
                f"Troquei pelo {produto.nome} por R$ {produto.preco:.2f}. "
                if oferta.tipo == "upsell"
                else f"Adicionei {produto.nome} por R$ {produto.preco:.2f}. "
            ) + _mensagem_operacional(novo_carrinho),
            carrinho=novo_carrinho,
            auditoria=(*resultado.auditoria, ("oferta", "aceita"), ("oferta_produto_id", produto.produto_id)),
        )

    def definir_modalidade(
        self,
        *,
        resultado: ResultadoAtendimento,
        modalidade: ModalidadePedidoAtendimento,
    ) -> ResultadoAtendimento:
        carrinho = resultado.carrinho
        if carrinho is None:
            raise ErroAssistenteAtendimento("carrinho_ausente")
        if modalidade is ModalidadePedidoAtendimento.INDEFINIDA:
            raise ErroAssistenteAtendimento("modalidade_atendimento_invalida")
        if carrinho.modalidade is not ModalidadePedidoAtendimento.INDEFINIDA:
            if carrinho.modalidade is modalidade:
                return resultado
            raise ErroAssistenteAtendimento("modalidade_alterada_reconfirmacao")

        atualizado = replace(
            carrinho,
            modalidade=modalidade,
            fingerprint=_fingerprint(
                tenant_id=carrinho.tenant_id,
                unidade_id=carrinho.unidade_id,
                conversa_id=carrinho.conversa_id,
                mensagem_id=carrinho.mensagem_id,
                itens=carrinho.itens,
                modalidade=modalidade,
            ),
        )
        estado = _estado_operacional(atualizado)
        return ResultadoAtendimento(
            estado=estado,
            mensagem=_mensagem_operacional(atualizado),
            carrinho=atualizado,
            auditoria=(*resultado.auditoria, ("modalidade", modalidade.value)),
        )

    def aplicar_cotacao_entrega(
        self,
        *,
        contexto: ContextoAtendimento,
        resultado: ResultadoAtendimento,
        cotacao: CotacaoEntregaAtendimento,
    ) -> ResultadoAtendimento:
        carrinho = resultado.carrinho
        if carrinho is None:
            raise ErroAssistenteAtendimento("carrinho_ausente")
        if carrinho.modalidade is not ModalidadePedidoAtendimento.ENTREGA:
            raise ErroAssistenteAtendimento("cotacao_sem_modalidade_entrega")
        if contexto.cliente.tipo is not TipoClienteAtendimento.CONHECIDO:
            raise ErroAssistenteAtendimento("cliente_novo_exige_cadastro_antes_da_cotacao")

        atualizado = replace(
            carrinho,
            entrega=cotacao,
            fingerprint=_fingerprint(
                tenant_id=carrinho.tenant_id,
                unidade_id=carrinho.unidade_id,
                conversa_id=carrinho.conversa_id,
                mensagem_id=carrinho.mensagem_id,
                itens=carrinho.itens,
                modalidade=carrinho.modalidade,
                entrega=cotacao,
            ),
        )
        return ResultadoAtendimento(
            estado=_estado_operacional(atualizado),
            mensagem=(
                f"Entrega validada para {cotacao.nome_area}: taxa R$ {cotacao.taxa:.2f}, "
                f"rota {cotacao.distancia_metros / 1000:.1f} km, "
                f"ETA de trajeto {cotacao.eta_rota_minutos} min e prazo operacional "
                f"{cotacao.sla_minutos}-{cotacao.sla_maxutos} min. "
                + _mensagem_operacional(atualizado)
            ),
            carrinho=atualizado,
            auditoria=(
                *resultado.auditoria,
                ("endereco", "google_maps_validado"),
                ("area_entrega", cotacao.area_id),
                ("taxa_entrega", str(cotacao.taxa)),
            ),
        )

    def definir_pagamento(
        self,
        *,
        resultado: ResultadoAtendimento,
        metodo: MetodoPagamento,
        valor_para_troco: Decimal | str | float | None = None,
    ) -> ResultadoAtendimento:
        carrinho = resultado.carrinho
        if carrinho is None:
            raise ErroAssistenteAtendimento("carrinho_ausente")
        if resultado.estado not in {
            EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO,
            EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE,
        }:
            raise ErroAssistenteAtendimento("forma_pagamento_fora_de_estado")
        if carrinho.modalidade is ModalidadePedidoAtendimento.INDEFINIDA:
            raise ErroAssistenteAtendimento("modalidade_atendimento_invalida")
        if (
            carrinho.modalidade is ModalidadePedidoAtendimento.ENTREGA
            and carrinho.entrega is None
        ):
            raise ErroAssistenteAtendimento("entrega_nao_cotada")

        troco = None
        if valor_para_troco is not None:
            try:
                troco = Decimal(str(valor_para_troco)).quantize(Decimal("0.01"))
            except Exception as exc:
                raise ErroAssistenteAtendimento("valor_para_troco_invalido") from exc
            if metodo is not MetodoPagamento.DINHEIRO:
                raise ErroAssistenteAtendimento("troco_somente_para_dinheiro")
            if troco < carrinho.total:
                raise ErroAssistenteAtendimento("valor_para_troco_inferior_total")

        try:
            preferencia = PreferenciaPagamentoAtendimento(
                metodo=metodo,
                valor_para_troco=troco,
            )
        except ValueError as exc:
            raise ErroAssistenteAtendimento(str(exc)) from exc

        atualizado = replace(
            carrinho,
            pagamento=preferencia,
            fingerprint=_fingerprint(
                tenant_id=carrinho.tenant_id,
                unidade_id=carrinho.unidade_id,
                conversa_id=carrinho.conversa_id,
                mensagem_id=carrinho.mensagem_id,
                itens=carrinho.itens,
                modalidade=carrinho.modalidade,
                entrega=carrinho.entrega,
                pagamento=preferencia,
            ),
        )

        detalhe = f"Forma de pagamento solicitada: {metodo.value}."
        if preferencia.valor_para_troco is not None:
            estimado = preferencia.troco_estimado(atualizado.total)
            detalhe = (
                f"Pagamento em dinheiro; troco solicitado para "
                f"R$ {preferencia.valor_para_troco:.2f} "
                f"(estimativa de troco R$ {estimado:.2f})."
            )

        return ResultadoAtendimento(
            estado=EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE,
            mensagem=(
                f"{detalhe} Pagamento ainda não confirmado. "
                f"Total final R$ {atualizado.total:.2f}. "
                "Confirme explicitamente o carrinho e a forma de pagamento."
            ),
            carrinho=atualizado,
            auditoria=(
                *resultado.auditoria,
                ("metodo_pagamento_solicitado", metodo.value),
                (
                    "troco_para",
                    (
                        str(preferencia.valor_para_troco)
                        if preferencia.valor_para_troco is not None
                        else "nao_solicitado"
                    ),
                ),
            ),
        )

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

        if carrinho.modalidade is ModalidadePedidoAtendimento.INDEFINIDA:
            raise ErroAssistenteAtendimento("modalidade_atendimento_invalida")
        if (
            carrinho.modalidade is ModalidadePedidoAtendimento.ENTREGA
            and carrinho.entrega is None
        ):
            raise ErroAssistenteAtendimento("entrega_nao_cotada")
        if carrinho.pagamento is None:
            raise ErroAssistenteAtendimento("forma_pagamento_nao_definida")
        if metodo is not carrinho.pagamento.metodo:
            raise ErroAssistenteAtendimento(
                "forma_pagamento_alterada_reconfirmacao_obrigatoria"
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

        endereco_ref = None
        if carrinho.modalidade is ModalidadePedidoAtendimento.ENTREGA:
            customer_context = contexto.customer_context
            if (
                customer_context is None
                or customer_context.ultimo_endereco_ref is None
            ):
                raise ErroAssistenteAtendimento(
                    "entrega_sem_referencia_endereco_autorizada"
                )
            endereco_ref = customer_context.ultimo_endereco_ref

        checkout = self.checkout.executar(
            contexto=contexto.contexto_execucao,
            carrinho=carrinho,
            cliente_ref=cliente_ref,
            canal=contexto.canal,
            metodo=carrinho.pagamento.metodo,
            idempotency_key=idempotency_key,
            endereco_ref=endereco_ref,
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
                ("metodo_pagamento", carrinho.pagamento.metodo.value),
                ("pedido", checkout.pedido_status),
                (
                    "estoque",
                    "reservado"
                    if checkout.estoque_reservado
                    else "sem_ficha_aplicavel",
                ),
                (
                    "entrega",
                    checkout.entrega_status
                    if checkout.entrega_status is not None
                    else "nao_aplicavel",
                ),
            ),
        )
