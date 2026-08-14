"""Composicao concreta do Pedido e dos casos de uso financeiros do PR7."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.eventos import EventoDominio, PedidoConfirmado
from core.dominio.ids import (
    ClienteId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.estados.maquinas import ComandoTransicao, SnapshotEstado, transicionar
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pagamentos.servicos import (
    avaliar_criterio_financeiro,
    confirmar_pagamento,
    criar_obrigacao_pagamento,
    reconhecer_venda,
)
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.seguranca.contexto import ContextoExecucao

from .adaptadores_sqlalchemy import (
    FaultInjector,
    LegacyPDVSQLAlchemyAdapter,
    RepositorioPDVSQLAlchemy,
)
from .modelos import (
    EntradaPDV,
    ResultadoPDV,
    id_produto_legado,
    mapear_metodo,
)
from .reconciliacao import ReconciliacaoPDV, detectar_divergencias


class PedidoAguardandoConfirmacao(EventoDominio):
    TIPO = "pedido.aguardando_confirmacao"


def id_deterministico(chave: str) -> str:
    return str(uuid5(NAMESPACE_URL, chave))


def _fingerprint(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(valores, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _evento(resultado: object, *, confirmado: bool) -> EventoDominio:
    evento = resultado.evento  # type: ignore[attr-defined]
    classe = PedidoConfirmado if confirmado else PedidoAguardandoConfirmacao
    return classe(
        event_id=EventoId(evento.event_id),
        aggregate_id=evento.aggregate_id,
        aggregate_type=evento.aggregate_type,
        tenant_id=TenantId(evento.tenant_id),
        unidade_id=UnidadeId(evento.unidade_id),
        correlation_id=CorrelationId(evento.correlation_id),
        causation_id=None,
        occurred_at=evento.timestamp,
        payload=dict(evento.payload),
        idempotency_key=IdempotencyKey(evento.idempotency_key),
        version=evento.aggregate_version,
    )


def criar_e_confirmar_pedido(
    *,
    entrada: EntradaPDV,
    contexto: ContextoExecucao,
    repositorio: RepositorioPedidosSQLAlchemy,
    instante: datetime,
) -> Pedido:
    chave = entrada.idempotency_key
    existente = repositorio.buscar_por_idempotencia(
        TenantId(contexto.tenant_id),
        UnidadeId(contexto.unidade_id),
        IdempotencyKey(f"{chave}:pedido"),
    )
    if existente:
        return existente
    pedido_id = id_deterministico(
        f"{contexto.tenant_id}:{contexto.unidade_id}:{chave}:pedido"
    )
    item = ItemPedido(
        id=PedidoItemId(id_deterministico(f"{pedido_id}:item:1")),
        tenant_id=TenantId(contexto.tenant_id),
        unidade_id=UnidadeId(contexto.unidade_id),
        produto_id=ProdutoId(id_produto_legado(entrada.produto_id)),
        nome_produto=entrada.produto_nome,
        quantidade=QuantidadeItem(entrada.quantidade),
        preco_unitario=entrada.preco_unitario,
        subtotal=entrada.subtotal,
    )
    pedido = Pedido.novo(
        id=PedidoId(pedido_id),
        tenant_id=TenantId(contexto.tenant_id),
        unidade_id=UnidadeId(contexto.unidade_id),
        origem=OrigemPedido.BALCAO,
        canal=CanalAtendimento.PRESENCIAL,
        status=PedidoStatus.RASCUNHO,
        cliente_id=ClienteId(f"legacy:cliente:{entrada.cliente_id}")
        if entrada.cliente_id
        else None,
        criado_em=instante,
        atualizado_em=instante,
        versao=1,
        correlation_id=CorrelationId(contexto.correlation_id),
        idempotency_key=IdempotencyKey(f"{chave}:pedido"),
        subtotal=entrada.subtotal,
        descontos=entrada.desconto_cashback,
        taxas=Dinheiro(Decimal(0)),
        total=entrada.total,
        itens=(item,),
    )
    pedido = repositorio.salvar(pedido, versao_esperada=0)
    snapshot = SnapshotEstado(
        "pedido",
        pedido_id,
        contexto.tenant_id,
        contexto.unidade_id,
        pedido.status.value,
        pedido.versao,
    )
    aguardando = transicionar(
        snapshot,
        ComandoTransicao(
            PedidoStatus.AGUARDANDO_CONFIRMACAO.value,
            pedido.versao,
            f"{chave}:pedido:aguardando",
            instante,
            contexto,
            {"itens_validos": True, "precos_calculados": True},
        ),
    )
    pedido = replace(
        pedido,
        status=PedidoStatus.AGUARDANDO_CONFIRMACAO,
        versao=2,
        atualizado_em=instante,
    )
    repositorio.salvar(pedido, versao_esperada=1)
    repositorio.salvar_eventos(
        pedido.tenant_id,
        pedido.unidade_id,
        pedido.id,
        (_evento(aguardando, confirmado=False),),
    )
    confirmado = transicionar(
        aguardando.snapshot,
        ComandoTransicao(
            PedidoStatus.CONFIRMADO.value,
            pedido.versao,
            f"{chave}:pedido:confirmado",
            instante,
            contexto,
            {"dados_confirmados": True},
        ),
    )
    pedido = replace(
        pedido, status=PedidoStatus.CONFIRMADO, versao=3, atualizado_em=instante
    )
    repositorio.salvar(pedido, versao_esperada=2)
    repositorio.salvar_eventos(
        pedido.tenant_id,
        pedido.unidade_id,
        pedido.id,
        (_evento(confirmado, confirmado=True),),
    )
    return pedido


class EscritorShadowSQLAlchemy:
    def __init__(self, session: Session, contexto: ContextoExecucao) -> None:
        self.session = session
        self.contexto = contexto

    def escrever(self, entrada: EntradaPDV, venda_legada_id: str | None) -> str:
        instante = datetime.now(timezone.utc)
        pedido = criar_e_confirmar_pedido(
            entrada=entrada,
            contexto=self.contexto,
            repositorio=RepositorioPedidosSQLAlchemy(self.session),
            instante=instante,
        )
        RepositorioPDVSQLAlchemy(self.session).reconciliar(
            tenant_id=self.contexto.tenant_id,
            unidade_id=self.contexto.unidade_id,
            modo="shadow",
            pedido_id=str(pedido.id),
            pagamento_id=None,
            venda_financeira_id=None,
            venda_legada_id=venda_legada_id,
            idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
            valor_pedido=entrada.total.valor,
            valor_pagamento=None,
            valor_venda_financeira=None,
            valor_venda_legada=entrada.total.valor,
            estoque_estrategia="legado",
            cashback_usado=entrada.desconto_cashback.valor,
            cashback_ganho=(entrada.total.valor * Decimal(".05")).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP
            ),
            status="conciliado",
            divergencias=[],
            criado_em=instante,
        )
        return str(pedido.id)


class ExecutorAutoritativoLegadoSQLAlchemy:
    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        legado: LegacyPDVSQLAlchemyAdapter,
        fault: FaultInjector | None = None,
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.legado = legado
        self.fault = fault or (lambda _ponto: None)

    def executar(self, entrada: EntradaPDV) -> ResultadoPDV:
        instante = datetime.now(timezone.utc)
        pedidos = RepositorioPedidosSQLAlchemy(self.session)
        pagamentos = RepositorioPagamentosSQLAlchemy(self.session)
        pdv = RepositorioPDVSQLAlchemy(self.session)
        conciliada = pdv.buscar_reconciliacao(
            self.contexto.tenant_id,
            self.contexto.unidade_id,
            f"{entrada.idempotency_key}:reconciliacao",
        )
        if conciliada and conciliada.venda_legada_id:
            recebido = entrada.valor_recebido or entrada.total
            return ResultadoPDV(
                "authoritative_canary",
                True,
                idempotente=True,
                pedido_id=conciliada.pedido_id,
                pagamento_id=conciliada.pagamento_id,
                venda_financeira_id=conciliada.venda_financeira_id,
                venda_legada_id=conciliada.venda_legada_id,
                troco=recebido - entrada.total,
            )
        consumos = self.legado.validar_estoque(entrada)
        pedido = criar_e_confirmar_pedido(
            entrada=entrada,
            contexto=self.contexto,
            repositorio=pedidos,
            instante=instante,
        )
        self.fault("after_pedido")
        metodo = mapear_metodo(entrada.forma_pagamento)
        pagamento_id = id_deterministico(f"{entrada.idempotency_key}:pagamento")
        iniciado = criar_obrigacao_pagamento(
            contexto=self.contexto,
            repositorio=pagamentos,
            pagamento_id=pagamento_id,
            pedido_id=str(pedido.id),
            valor_previsto=entrada.total,
            metodo=metodo,
            idempotency_key=f"{entrada.idempotency_key}:pagamento",
            timestamp=instante,
            provedor="sandbox" if entrada.pix_sandbox else None,
        )
        self.fault("after_pagamento")
        if metodo.value == "pix" and not entrada.pix_sandbox:
            pdv.reconciliar(
                tenant_id=self.contexto.tenant_id,
                unidade_id=self.contexto.unidade_id,
                modo="authoritative_canary",
                pedido_id=str(pedido.id),
                pagamento_id=pagamento_id,
                venda_financeira_id=None,
                venda_legada_id=None,
                idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
                valor_pedido=entrada.total.valor,
                valor_pagamento=Decimal(0),
                valor_venda_financeira=None,
                valor_venda_legada=None,
                estoque_estrategia="legado_pendente",
                cashback_usado=Decimal(0),
                cashback_ganho=Decimal(0),
                status="conciliado",
                divergencias=[],
                criado_em=instante,
            )
            return ResultadoPDV(
                "authoritative_canary",
                False,
                pedido_id=str(pedido.id),
                pagamento_id=pagamento_id,
                motivo="aguardando_confirmacao_pix",
            )
        recebido = (
            (entrada.valor_recebido or entrada.total)
            if metodo.value == "dinheiro"
            else entrada.total
        )
        confirmado = confirmar_pagamento(
            contexto=self.contexto,
            repositorio=pagamentos,
            pagamento_id=pagamento_id,
            valor=entrada.total,
            valor_recebido=recebido,
            metodo=metodo,
            idempotency_key=f"{entrada.idempotency_key}:confirmacao",
            expected_version=iniciado.pagamento.versao,
            timestamp=instante,
            referencia_externa="sandbox"
            if entrada.pix_sandbox
            else (
                f"operacional:{self.contexto.usuario_id}"
                if entrada.confirmacao_presencial
                else None
            ),
        )
        self.fault("after_confirmacao")
        criterio = avaliar_criterio_financeiro(
            contexto=self.contexto,
            pagamento=confirmado.pagamento,
            pedido_id=str(pedido.id),
            timestamp=instante,
        )
        criterio = pagamentos.salvar_criterio(
            self.contexto.tenant_id,
            self.contexto.unidade_id,
            criterio,
            f"{entrada.idempotency_key}:criterio",
            _fingerprint(
                str(pedido.id),
                pagamento_id,
                criterio.codigo,
                criterio.valor_reconhecivel.valor,
            ),
        )
        reconhecida = reconhecer_venda(
            contexto=self.contexto,
            repositorio=pagamentos,
            criterio=criterio,
            metodo=metodo,
            idempotency_key=f"{entrada.idempotency_key}:venda",
            timestamp=instante,
            produto_id_legado=entrada.produto_id,
        )
        self.fault("after_venda_financeira")
        venda = self.legado.criar_venda_uma_vez(entrada, instante=instante)
        self.fault("after_venda_legada")
        self.legado.baixar_estoque_uma_vez(entrada, consumos, instante)
        self.fault("after_estoque")
        self.legado.aplicar_cashback_uma_vez(entrada, instante)
        self.fault("after_cashback")
        pdv.criar_link(
            tenant=self.contexto.tenant_id,
            unidade=self.contexto.unidade_id,
            pedido_id=str(pedido.id),
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            instante=instante,
        )
        self.fault("before_reconciliacao")
        contagens = pdv.contar_efeitos(
            self.contexto.tenant_id, self.contexto.unidade_id, str(pedido.id)
        )
        base_reconciliacao = ReconciliacaoPDV(
            tenant_id=self.contexto.tenant_id,
            unidade_id=self.contexto.unidade_id,
            modo="authoritative_canary",
            idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
            criado_em=instante,
            pedido_id=str(pedido.id),
            pagamento_id=pagamento_id,
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            valor_pedido=entrada.total.valor,
            valor_pagamento=confirmado.pagamento.valor_pago.valor,
            valor_venda_financeira=reconhecida.venda.valor.valor,
            valor_venda_legada=Decimal(str(venda.valor_total)),
        )
        divergencias = detectar_divergencias(
            base_reconciliacao,
            vendas_legadas=contagens.get("VENDA_LEGADA", 0),
            efeitos_estoque=contagens.get("ESTOQUE_LEGADO", 0),
            efeitos_cashback_usado=contagens.get("CASHBACK_USADO", 0),
        )
        pdv.reconciliar(
            tenant_id=self.contexto.tenant_id,
            unidade_id=self.contexto.unidade_id,
            modo="authoritative_canary",
            pedido_id=str(pedido.id),
            pagamento_id=pagamento_id,
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
            valor_pedido=entrada.total.valor,
            valor_pagamento=confirmado.pagamento.valor_pago.valor,
            valor_venda_financeira=reconhecida.venda.valor.valor,
            valor_venda_legada=Decimal(str(venda.valor_total)),
            estoque_estrategia="legado",
            cashback_usado=entrada.desconto_cashback.valor
            if entrada.usar_cashback
            else Decimal(0),
            cashback_ganho=(entrada.total.valor * Decimal(".05")).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP
            ),
            status="divergente" if divergencias else "conciliado",
            divergencias=list(divergencias),
            criado_em=instante,
        )
        troco = (
            confirmado.confirmacao.troco
            if confirmado.confirmacao
            else Dinheiro(Decimal(0))
        )
        return ResultadoPDV(
            "authoritative_canary",
            True,
            pedido_id=str(pedido.id),
            pagamento_id=pagamento_id,
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            troco=troco,
        )


# O canary da Onda 1 usa o núcleo transacional canônico; shadow/legacy acima
# permanecem disponíveis para comparação e rollback controlado.
from .executor_canonico import (
    ExecutorAutoritativoCanonicoSQLAlchemy as ExecutorAutoritativoSQLAlchemy,
)

__all__ = [
    "EscritorShadowSQLAlchemy",
    "ExecutorAutoritativoLegadoSQLAlchemy",
    "ExecutorAutoritativoSQLAlchemy",
]
