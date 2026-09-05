"""Fachada comercial F11-E para a jornada autenticada do Delivery Próprio.

A UI não conhece tenant/unidade livres nem usa o runtime histórico do canal.
Carrinho permanece estado de jornada; Pedido, Pagamento, Estoque e Entrega
continuam nas autoridades canônicas e, quando há escrita coordenada, compartilham
a mesma UnitOfWorkV1.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session

from application.catalogo_estoque_cutover import preparar_snapshot_ficha_estoque_v1
from application.checkout import (
    ComandoCheckoutV1,
    confirmar_checkout_sem_obrigacao_financeira_em_transacao,
)
from application.delivery_checkout_comercial import (
    CheckoutDeliveryComercialV1,
    executar_checkout_delivery_comercial_em_transacao,
)
from application.delivery_contexto_comercial import (
    ContextoDeliveryComercialV1,
    resolver_contexto_delivery_comercial,
)
from core.crm.modelos import ClienteCRM
from core.delivery.adapters import (
    PortaEntregaCanalDelivery,
    PortaPagamentosDelivery,
    PortaPedidosDelivery,
    PortaPromocoesDelivery,
)
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import (
    CarrinhoDelivery,
    EnderecoDelivery,
    StatusCarrinhoDelivery,
)
from core.delivery.servicos import ServicoDelivery
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import (
    CanalAtendimento,
    OrigemPedido,
    PagamentoStatus,
    PedidoStatus,
)
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
from core.entrega import (
    Entrega,
    ModalidadeEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    StatusEntrega,
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from core.estoque.modelos import StatusReserva
from core.estoque.servicos import liberar_reserva
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.servicos import cancelar_pagamento
from core.pedidos.servicos import transicionar_pedido
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.crm.clientes_sqlalchemy import LeitorClientesCRMSQLAlchemy
from infra.delivery.carrinhos_sqlalchemy import RepositorioCarrinhosDeliverySQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


class ErroDeliveryComercial(RuntimeError):
    """A jornada comercial não pode prosseguir com segurança."""


@dataclass(frozen=True)
class ResultadoConfirmacaoDeliveryComercial:
    pedido_id: str
    entrega_id: str
    status_pedido: PedidoStatus
    status_entrega: StatusEntrega
    checkout: CheckoutDeliveryComercialV1


@dataclass(frozen=True)
class EventoTrackingDeliveryComercial:
    tipo: str
    ocorrido_em: datetime
    status_entrega: str


@dataclass(frozen=True)
class TrackingDeliveryComercial:
    pedido_id: str
    status_pedido: PedidoStatus
    entrega_id: str
    status_entrega: StatusEntrega
    total: Decimal
    eventos: tuple[EventoTrackingDeliveryComercial, ...]


class _PortaHistoricaIndisponivel:
    def __getattr__(self, nome: str) -> object:
        raise ErroDeliveryComercial(f"porta_historica_indisponivel:{nome}")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefixo: str, chave: str) -> str:
    digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()[:24]
    return f"{prefixo}-{digest}"


def _exigir_permissoes(
    identidade: IdentidadeUsuario, *permissoes: Permissao
) -> None:
    ausentes = [p.value for p in permissoes if p not in identidade.permissoes]
    if ausentes:
        raise PermissionError("permissoes_delivery_ausentes:" + ",".join(ausentes))


def _servico_carrinho(session: Session) -> ServicoDelivery:
    indisponivel = _PortaHistoricaIndisponivel()
    return ServicoDelivery(
        carrinhos=RepositorioCarrinhosDeliverySQLAlchemy(session),
        pedidos=cast(PortaPedidosDelivery, indisponivel),
        pagamentos=cast(PortaPagamentosDelivery, indisponivel),
        entregas=cast(PortaEntregaCanalDelivery, indisponivel),
        promocoes=cast(PortaPromocoesDelivery, indisponivel),
    )


def _contexto_sistema(
    contexto: ContextoExecucao, *, identidade: str, motivo: str
) -> ContextoExecucao:
    sistema = ContextoExecucao.sistema(
        identidade=identidade,
        motivo=motivo,
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        correlation_id=contexto.correlation_id,
        solicitado_em=contexto.solicitado_em,
    )
    if contexto.causation_id is not None:
        sistema = replace(sistema, causation_id=contexto.causation_id)
    return sistema


def _contexto_efeito(
    contexto: ContextoExecucao, permissao: Permissao
) -> ContextoExecucao:
    return replace(
        contexto,
        permissoes=frozenset({permissao}),
        unidades_permitidas=frozenset({contexto.unidade_id}),
        identidade_sistema=False,
        motivo_sistema=None,
    )


def listar_clientes_delivery_comercial(
    *, identidade: IdentidadeUsuario, session_factory: SessionFactory
) -> tuple[ClienteCRM, ...]:
    _exigir_permissoes(identidade, Permissao.CLIENTE_VISUALIZAR)
    session = session_factory()
    try:
        return LeitorClientesCRMSQLAlchemy(session).listar(
            tenant_id=identidade.tenant_id,
            unidade_id=identidade.unidade_id,
        )
    finally:
        session.close()


def resolver_contexto_jornada_delivery(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    session_factory: SessionFactory,
) -> ContextoDeliveryComercialV1:
    _exigir_permissoes(
        identidade,
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_VISUALIZAR,
    )
    session = session_factory()
    try:
        return resolver_contexto_delivery_comercial(
            session=session,
            identidade=identidade,
            cliente_id=cliente_id,
        )
    finally:
        session.close()


def abrir_carrinho_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    carrinho_id: str,
    session_factory: SessionFactory,
) -> CarrinhoDelivery:
    _exigir_permissoes(
        identidade,
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_CRIAR,
    )
    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        contexto = resolver_contexto_delivery_comercial(
            session=uow.session,
            identidade=identidade,
            cliente_id=cliente_id,
        )
        carrinho = _servico_carrinho(uow.session).abrir_carrinho(
            carrinho_id=carrinho_id,
            tenant_id=contexto.contexto.tenant_id,
            unidade_id=contexto.contexto.unidade_id,
            cliente_ref=contexto.cliente.cliente_id,
        )
        uow.commit()
        return carrinho


def obter_carrinho_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    carrinho_id: str,
    session_factory: SessionFactory,
) -> CarrinhoDelivery | None:
    _exigir_permissoes(identidade, Permissao.PEDIDO_VISUALIZAR)
    session = session_factory()
    try:
        return RepositorioCarrinhosDeliverySQLAlchemy(session).obter_do_cliente(
            tenant_id=identidade.tenant_id,
            unidade_id=identidade.unidade_id,
            cliente_ref=cliente_id,
            carrinho_id=carrinho_id,
        )
    finally:
        session.close()


def adicionar_item_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    carrinho_id: str,
    produto_id: str,
    quantidade: int,
    expected_version: int,
    session_factory: SessionFactory,
) -> CarrinhoDelivery:
    _exigir_permissoes(
        identidade,
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_CRIAR,
    )
    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        contexto = resolver_contexto_delivery_comercial(
            session=uow.session,
            identidade=identidade,
            cliente_id=cliente_id,
        )
        carrinho = _servico_carrinho(uow.session).adicionar_item(
            tenant_id=contexto.contexto.tenant_id,
            unidade_id=contexto.contexto.unidade_id,
            carrinho_id=carrinho_id,
            produto_id=produto_id,
            quantidade=quantidade,
            expected_version=expected_version,
            catalogo=contexto.catalogo,
        )
        uow.commit()
        return carrinho


def _snapshot_endereco(contexto: ContextoDeliveryComercialV1) -> EnderecoDelivery:
    formatado = " ".join(contexto.endereco.endereco_formatado.split())
    if "/" not in formatado:
        raise ErroDelivery("endereco_formatado_sem_uf")
    base, uf = formatado.rsplit("/", 1)
    uf = uf.strip().upper()
    if len(uf) != 2:
        raise ErroDelivery("endereco_formatado_sem_uf")
    partes = [parte.strip() for parte in base.split(" - ") if parte.strip()]
    if not partes:
        raise ErroDelivery("endereco_formatado_invalido")
    logradouro_numero = partes[0]
    if "," in logradouro_numero:
        logradouro, numero = [x.strip() for x in logradouro_numero.rsplit(",", 1)]
    else:
        logradouro, numero = logradouro_numero, "s/n"
    cidade = partes[-1] if len(partes) > 1 else "endereco_validado"
    bairro = partes[-2] if len(partes) > 2 else "endereco_validado"
    return EnderecoDelivery(
        endereco_id=contexto.endereco.referencia,
        cliente_ref=contexto.cliente.cliente_id,
        cep=contexto.endereco.cep,
        logradouro=logradouro,
        numero=numero or "s/n",
        bairro=bairro,
        cidade=cidade,
        uf=uf,
        validado=True,
    )


def cotar_endereco_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    carrinho_id: str,
    expected_version: int,
    session_factory: SessionFactory,
) -> CarrinhoDelivery:
    _exigir_permissoes(
        identidade,
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_CRIAR,
    )
    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        contexto = resolver_contexto_delivery_comercial(
            session=uow.session,
            identidade=identidade,
            cliente_id=cliente_id,
        )
        carrinho = _servico_carrinho(uow.session).definir_endereco(
            tenant_id=contexto.contexto.tenant_id,
            unidade_id=contexto.contexto.unidade_id,
            carrinho_id=carrinho_id,
            endereco=_snapshot_endereco(contexto),
            expected_version=expected_version,
            areas=contexto.areas_entrega,
        )
        uow.commit()
        return carrinho


def _pedido_do_carrinho(
    *,
    carrinho: CarrinhoDelivery,
    contexto: ContextoExecucao,
    idempotency_key: str,
    timestamp: datetime,
) -> Pedido:
    if not carrinho.itens or carrinho.cotacao is None or carrinho.endereco is None:
        raise ErroDeliveryComercial("carrinho_delivery_incompleto")
    pedido_id = PedidoId(
        _id(
            "ped",
            f"{contexto.tenant_id}:{contexto.unidade_id}:{idempotency_key}",
        )
    )
    itens = tuple(
        ItemPedido(
            id=PedidoItemId(_id("item", f"{pedido_id}:{indice}:{item.produto_id}")),
            tenant_id=TenantId(contexto.tenant_id),
            unidade_id=UnidadeId(contexto.unidade_id),
            produto_id=ProdutoId(item.produto_id),
            nome_produto=item.nome,
            quantidade=QuantidadeItem(item.quantidade),
            preco_unitario=Dinheiro(item.preco_unitario),
            subtotal=Dinheiro(item.subtotal),
            ficha_versao=f"delivery-catalogo-v{item.produto_versao}",
        )
        for indice, item in enumerate(carrinho.itens, start=1)
    )
    subtotal = Dinheiro(carrinho.subtotal)
    taxas = Dinheiro(carrinho.taxa_entrega)
    return Pedido.novo(
        id=pedido_id,
        tenant_id=TenantId(contexto.tenant_id),
        unidade_id=UnidadeId(contexto.unidade_id),
        origem=OrigemPedido.DELIVERY_PROPRIO,
        canal=CanalAtendimento.DELIVERY_PROPRIO,
        status=PedidoStatus.RASCUNHO,
        cliente_id=ClienteId(carrinho.cliente_ref),
        criado_em=timestamp,
        atualizado_em=timestamp,
        versao=1,
        correlation_id=CorrelationId(contexto.correlation_id),
        idempotency_key=IdempotencyKey(idempotency_key),
        subtotal=subtotal,
        descontos=Dinheiro("0.00"),
        taxas=taxas,
        total=Dinheiro(subtotal.valor + taxas.valor),
        itens=itens,
    )


def confirmar_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    carrinho_id: str,
    metodo_pagamento: MetodoPagamento,
    idempotency_key: str,
    session_factory: SessionFactory,
) -> ResultadoConfirmacaoDeliveryComercial:
    _exigir_permissoes(
        identidade,
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_CRIAR,
        Permissao.PEDIDO_ALTERAR,
        Permissao.PAGAMENTO_REGISTRAR,
    )
    chave = idempotency_key.strip()
    if not chave:
        raise ErroDeliveryComercial("idempotency_key_obrigatoria")
    instante = _agora()

    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        contexto_delivery = resolver_contexto_delivery_comercial(
            session=uow.session,
            identidade=identidade,
            cliente_id=cliente_id,
            correlation_id=_id("corr", chave),
        )
        contexto = contexto_delivery.contexto
        carrinhos = RepositorioCarrinhosDeliverySQLAlchemy(uow.session)
        carrinho = carrinhos.obter_do_cliente(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            cliente_ref=cliente_id,
            carrinho_id=carrinho_id,
        )
        if carrinho is None:
            raise ErroDeliveryComercial("carrinho_delivery_indisponivel")
        if carrinho.status not in {
            StatusCarrinhoDelivery.ABERTO,
            StatusCarrinhoDelivery.CONFIRMADO,
        }:
            raise ErroDeliveryComercial("carrinho_delivery_nao_confirmavel")
        if (
            carrinho.status is StatusCarrinhoDelivery.CONFIRMADO
            and carrinho.idempotency_confirmacao != chave
        ):
            raise ErroDeliveryComercial("carrinho_confirmado_por_outro_comando")

        pedido = _pedido_do_carrinho(
            carrinho=carrinho,
            contexto=contexto,
            idempotency_key=chave,
            timestamp=instante,
        )
        snapshot = preparar_snapshot_ficha_estoque_v1(
            session=uow.session,
            contexto=contexto,
            pedido=pedido,
            recursos=uow.recursos,
        )
        pagamento_id = _id("pag", str(pedido.id)) if pedido.total.valor > 0 else None
        comando = ComandoCheckoutV1(
            pedido=pedido,
            timestamp=instante,
            pagamento_id=pagamento_id,
            metodo_pagamento=(
                metodo_pagamento if pagamento_id is not None else None
            ),
            snapshot_estoque=snapshot,
            recebimento_posterior=(
                metodo_pagamento is MetodoPagamento.PAGAMENTO_NA_ENTREGA
            ),
        )
        checkout = executar_checkout_delivery_comercial_em_transacao(
            comando=comando,
            contexto=contexto,
            contexto_delivery=contexto_delivery,
            carrinho=carrinho,
            recursos=uow.recursos,
        )
        pedido_checkout = checkout.checkout.aguardando_confirmacao.pedido
        if pedido_checkout.total.valor == 0:
            confirmar_checkout_sem_obrigacao_financeira_em_transacao(
                checkout=checkout.checkout,
                contexto=contexto,
                recursos=uow.recursos,
                timestamp=instante,
            )

        repositorio_entrega = RepositorioEntregaSQLAlchemy(uow.session)
        entrega_existente = repositorio_entrega.buscar_por_pedido(
            contexto.tenant_id,
            contexto.unidade_id,
            str(pedido_checkout.id),
        )
        if entrega_existente is None:
            entrega_id = _id("ent", str(pedido_checkout.id))
            entrega = ServicoEntrega(
                repositorio_entrega,
                financeiro_resolvido=lambda tenant, unidade, pedido_ref: (
                    financeiro_resolvido_sqlalchemy(
                        uow.session, tenant, unidade, pedido_ref
                    )
                ),
                pedido_cancelado=lambda tenant, unidade, pedido_ref: (
                    pedido_cancelado_sqlalchemy(
                        uow.session, tenant, unidade, pedido_ref
                    )
                ),
                agora=lambda: instante,
            ).criar(
                Entrega(
                    entrega_id=entrega_id,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    pedido_id=str(pedido_checkout.id),
                    endereco_id=contexto_delivery.endereco.referencia,
                    modalidade=ModalidadeEntrega.PROPRIA,
                    status=StatusEntrega.AGUARDANDO_PRODUCAO,
                    versao=1,
                ),
                contexto=_contexto_sistema(
                    contexto,
                    identidade="delivery-commercial-f11e",
                    motivo="vincular logística canônica ao checkout do Delivery Próprio",
                ),
                idempotency_key=f"{chave}:entrega",
            )
        else:
            entrega = entrega_existente

        if carrinho.status is StatusCarrinhoDelivery.ABERTO:
            carrinhos.salvar_cas(
                replace(
                    carrinho,
                    status=StatusCarrinhoDelivery.CONFIRMADO,
                    pedido_id=str(pedido_checkout.id),
                    idempotency_confirmacao=chave,
                    versao=carrinho.versao + 1,
                ),
                expected_version=carrinho.versao,
            )
        uow.commit()
        return ResultadoConfirmacaoDeliveryComercial(
            pedido_id=str(pedido_checkout.id),
            entrega_id=entrega.entrega_id,
            status_pedido=pedido_checkout.status,
            status_entrega=entrega.status,
            checkout=checkout,
        )


def _pedido_do_cliente(
    *,
    uow: UnitOfWorkV1,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    pedido_id: str,
) -> Pedido:
    pedido = uow.recursos.pedidos.buscar(
        TenantId(identidade.tenant_id),
        UnidadeId(identidade.unidade_id),
        PedidoId(pedido_id),
    )
    if (
        pedido is None
        or pedido.origem is not OrigemPedido.DELIVERY_PROPRIO
        or pedido.cliente_id is None
        or str(pedido.cliente_id) != cliente_id
    ):
        raise ErroDeliveryComercial("pedido_delivery_indisponivel")
    return pedido


def acompanhar_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    pedido_id: str,
    session_factory: SessionFactory,
) -> TrackingDeliveryComercial:
    _exigir_permissoes(identidade, Permissao.PEDIDO_VISUALIZAR)
    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        pedido = _pedido_do_cliente(
            uow=uow,
            identidade=identidade,
            cliente_id=cliente_id,
            pedido_id=pedido_id,
        )
        repo = RepositorioEntregaSQLAlchemy(uow.session)
        entrega = repo.buscar_por_pedido(
            identidade.tenant_id, identidade.unidade_id, pedido_id
        )
        if entrega is None:
            raise ErroDeliveryComercial("entrega_delivery_indisponivel")
        eventos = tuple(
            EventoTrackingDeliveryComercial(
                tipo=str(evento.tipo),
                ocorrido_em=evento.ocorrido_em,
                status_entrega=str(evento.payload_seguro.get("status", entrega.status.value)),
            )
            for evento in repo.listar_eventos(
                identidade.tenant_id, identidade.unidade_id, entrega.entrega_id
            )
        )
        return TrackingDeliveryComercial(
            pedido_id=pedido_id,
            status_pedido=pedido.status,
            entrega_id=entrega.entrega_id,
            status_entrega=entrega.status,
            total=pedido.total.valor,
            eventos=eventos,
        )


def cancelar_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    pedido_id: str,
    motivo: str,
    idempotency_key: str,
    session_factory: SessionFactory,
) -> TrackingDeliveryComercial:
    _exigir_permissoes(
        identidade,
        Permissao.PEDIDO_CANCELAR,
        Permissao.PEDIDO_ALTERAR,
        Permissao.PAGAMENTO_REGISTRAR,
    )
    texto = motivo.strip()
    chave = idempotency_key.strip()
    if not texto or not chave:
        raise ErroDeliveryComercial("cancelamento_delivery_invalido")
    instante = _agora()

    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        pedido = _pedido_do_cliente(
            uow=uow,
            identidade=identidade,
            cliente_id=cliente_id,
            pedido_id=pedido_id,
        )
        repo_entrega = RepositorioEntregaSQLAlchemy(uow.session)
        entrega = repo_entrega.buscar_por_pedido(
            identidade.tenant_id, identidade.unidade_id, pedido_id
        )
        if entrega is None:
            raise ErroDeliveryComercial("entrega_delivery_indisponivel")
        if entrega.status in {
            StatusEntrega.COLETADA,
            StatusEntrega.EM_ROTA,
            StatusEntrega.ENTREGUE,
        }:
            raise ErroDeliveryComercial("entrega_delivery_nao_cancelavel_nesta_etapa")

        pagamento_id = _id("pag", pedido_id)
        pagamento = uow.recursos.pagamentos.buscar_pagamento(
            identidade.tenant_id, identidade.unidade_id, pagamento_id
        )
        if pagamento is not None:
            cancelaveis = {
                PagamentoStatus.NAO_INICIADO,
                PagamentoStatus.PENDENTE,
                PagamentoStatus.AGUARDANDO_ENTREGA,
                PagamentoStatus.AGUARDANDO_FECHAMENTO,
                PagamentoStatus.FALHOU,
                PagamentoStatus.CANCELADO,
            }
            if pagamento.status not in cancelaveis:
                raise ErroDeliveryComercial(
                    "pagamento_liquidado_exige_fluxo_financeiro_de_estorno"
                )
            if pagamento.status is not PagamentoStatus.CANCELADO:
                cancelado = cancelar_pagamento(
                    contexto=_contexto_efeito(
                        identidade.contexto(
                            origem="delivery.cancelamento",
                            correlation_id=str(pedido.correlation_id),
                            solicitado_em=instante,
                        ),
                        Permissao.PAGAMENTO_REGISTRAR,
                    ),
                    repositorio=uow.recursos.pagamentos,
                    pagamento_id=pagamento.id,
                    idempotency_key=f"{chave}:pagamento",
                    expected_version=pagamento.versao,
                    timestamp=instante,
                    motivo=texto,
                )
                uow.recursos.registrar_efeitos(
                    eventos=cancelado.eventos,
                    auditorias=cancelado.auditorias,
                )

        contexto = identidade.contexto(
            origem="delivery.cancelamento",
            correlation_id=str(pedido.correlation_id),
            solicitado_em=instante,
        )
        if pedido.status is not PedidoStatus.CANCELADO:
            pedido_cancelado = transicionar_pedido(
                tenant_id=pedido.tenant_id,
                unidade_id=pedido.unidade_id,
                pedido_id=pedido.id,
                destino=PedidoStatus.CANCELADO,
                versao_esperada=pedido.versao,
                idempotency_key=IdempotencyKey(f"{chave}:pedido"),
                contexto=contexto,
                repositorio=uow.recursos.pedidos,
                outbox=uow.recursos.outbox,
                auditoria=uow.recursos.auditoria,
                timestamp=instante,
                motivo=texto,
                metadata={"canal": "delivery_proprio"},
            ).pedido
        else:
            pedido_cancelado = pedido

        reserva = uow.recursos.estoque.buscar_reserva(
            identidade.tenant_id,
            identidade.unidade_id,
            pedido_id,
        )
        if reserva is not None and reserva.status is StatusReserva.ATIVA:
            liberada = liberar_reserva(
                contexto=_contexto_efeito(contexto, Permissao.ESTOQUE_LIBERAR),
                repositorio=uow.recursos.estoque,
                pedido_id=pedido_id,
                pedido_version=pedido_cancelado.versao,
                idempotency_key=f"{chave}:estoque",
                motivo=texto,
            )
            uow.recursos.registrar_efeitos(
                eventos=liberada.eventos,
                auditorias=liberada.auditorias,
            )

        entrega = ServicoEntrega(
            repo_entrega,
            financeiro_resolvido=lambda tenant, unidade, pedido_ref: (
                financeiro_resolvido_sqlalchemy(
                    uow.session, tenant, unidade, pedido_ref
                )
            ),
            pedido_cancelado=lambda tenant, unidade, pedido_ref: (
                pedido_cancelado_sqlalchemy(uow.session, tenant, unidade, pedido_ref)
            ),
            agora=lambda: instante,
        ).cancelar(
            entrega.entrega_id,
            texto,
            versao_esperada=entrega.versao,
            contexto=_contexto_sistema(
                contexto,
                identidade="delivery-cancel-f11e",
                motivo="cancelamento logístico após cancelamento canônico do Pedido",
            ),
            idempotency_key=f"{chave}:entrega",
        )
        uow.commit()
        return TrackingDeliveryComercial(
            pedido_id=pedido_id,
            status_pedido=pedido_cancelado.status,
            entrega_id=entrega.entrega_id,
            status_entrega=entrega.status,
            total=pedido_cancelado.total.valor,
            eventos=(),
        )


def repetir_delivery_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    pedido_id: str,
    novo_carrinho_id: str,
    session_factory: SessionFactory,
) -> CarrinhoDelivery:
    _exigir_permissoes(
        identidade,
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_VISUALIZAR,
        Permissao.PEDIDO_CRIAR,
    )
    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise ErroDeliveryComercial("uow_delivery_nao_iniciada")
        pedido = _pedido_do_cliente(
            uow=uow,
            identidade=identidade,
            cliente_id=cliente_id,
            pedido_id=pedido_id,
        )
        contexto = resolver_contexto_delivery_comercial(
            session=uow.session,
            identidade=identidade,
            cliente_id=cliente_id,
        )
        servico = _servico_carrinho(uow.session)
        novo = servico.abrir_carrinho(
            carrinho_id=novo_carrinho_id,
            tenant_id=identidade.tenant_id,
            unidade_id=identidade.unidade_id,
            cliente_ref=cliente_id,
        )
        catalogo = {produto.produto_id: produto for produto in contexto.catalogo}
        for item in pedido.itens:
            if item.produto_id is None or str(item.produto_id) not in catalogo:
                raise ErroDeliveryComercial("produto_indisponivel_repeticao")
            novo = servico.adicionar_item(
                tenant_id=identidade.tenant_id,
                unidade_id=identidade.unidade_id,
                carrinho_id=novo.carrinho_id,
                produto_id=str(item.produto_id),
                quantidade=item.quantidade.valor,
                expected_version=novo.versao,
                catalogo=contexto.catalogo,
            )
        novo = servico.definir_endereco(
            tenant_id=identidade.tenant_id,
            unidade_id=identidade.unidade_id,
            carrinho_id=novo.carrinho_id,
            endereco=_snapshot_endereco(contexto),
            expected_version=novo.versao,
            areas=contexto.areas_entrega,
        )
        uow.commit()
        return novo
