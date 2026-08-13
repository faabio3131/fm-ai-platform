"""Executor canary do PDV sobre o núcleo transacional canônico da V1."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from application.checkout import executar_checkout_em_transacao
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.dominio.ids import IdempotencyKey
from core.estoque.servicos import consumir_reserva
from core.pagamentos.adapters import ProvedorPagamentoFake
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.servicos import (
    avaliar_criterio_financeiro,
    confirmar_pagamento,
    processar_webhook,
    reconhecer_venda,
)
from core.pedidos.servicos import transicionar_pedido
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1

from .adaptadores_sqlalchemy import (
    FaultInjector,
    LegacyPDVSQLAlchemyAdapter,
    RepositorioPDVSQLAlchemy,
)
from .cutover_canonico import montar_checkout_pdv
from .modelos import EntradaPDV, ResultadoPDV, mapear_metodo
from .reconciliacao import ReconciliacaoPDV, detectar_divergencias


def _fingerprint(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(valores, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _cashback_ganho(entrada: EntradaPDV) -> Decimal:
    return (entrada.total.valor * Decimal(".05")).quantize(
        Decimal(".01"), rounding=ROUND_HALF_UP
    )


class ExecutorAutoritativoCanonicoSQLAlchemy:
    """Canary em que Pedido/Pagamento/Estoque V1 são a fonte operacional."""

    def __init__(
        self,
        *,
        session,
        contexto: ContextoExecucao,
        legado: LegacyPDVSQLAlchemyAdapter,
        fault: FaultInjector | None = None,
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.legado = legado
        self.fault = fault or (lambda _ponto: None)

    def _registrar_pendente(
        self,
        *,
        pdv: RepositorioPDVSQLAlchemy,
        entrada: EntradaPDV,
        pedido_id: str,
        pagamento_id: str,
        instante: datetime,
        motivo: str,
    ) -> ResultadoPDV:
        pdv.reconciliar(
            tenant_id=self.contexto.tenant_id,
            unidade_id=self.contexto.unidade_id,
            modo="authoritative_canary",
            pedido_id=pedido_id,
            pagamento_id=pagamento_id,
            venda_financeira_id=None,
            venda_legada_id=None,
            idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
            valor_pedido=entrada.total.valor,
            valor_pagamento=Decimal(0),
            valor_venda_financeira=None,
            valor_venda_legada=None,
            estoque_estrategia="canonico_reservado",
            cashback_usado=Decimal(0),
            cashback_ganho=Decimal(0),
            status="pendente_financeiro",
            divergencias=[motivo],
            criado_em=instante,
        )
        return ResultadoPDV(
            "authoritative_canary",
            False,
            pedido_id=pedido_id,
            pagamento_id=pagamento_id,
            motivo=motivo,
        )

    def executar(self, entrada: EntradaPDV) -> ResultadoPDV:
        instante = datetime.now(timezone.utc)
        pdv = RepositorioPDVSQLAlchemy(self.session)
        recursos = RecursosTransacionaisV1(self.session)
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

        comando, consumos_legados = montar_checkout_pdv(
            entrada=entrada,
            contexto=self.contexto,
            instante=instante,
            recursos=recursos,
            legado=self.legado,
        )
        checkout = executar_checkout_em_transacao(
            comando=comando,
            contexto=self.contexto,
            recursos=recursos,
        )
        pedido = checkout.aguardando_confirmacao.pedido
        iniciado = checkout.pagamento
        if iniciado is None or comando.pagamento_id is None:
            raise RuntimeError("pdv_checkout_sem_obrigacao_financeira")
        self.fault("after_checkout_canonico")

        metodo = mapear_metodo(entrada.forma_pagamento)
        confirmado = None
        if metodo is MetodoPagamento.DINHEIRO:
            recebido = entrada.valor_recebido or entrada.total
            confirmado = confirmar_pagamento(
                contexto=self.contexto,
                repositorio=recursos.pagamentos,
                pagamento_id=comando.pagamento_id,
                valor=entrada.total,
                valor_recebido=recebido,
                metodo=metodo,
                idempotency_key=f"{entrada.idempotency_key}:confirmacao",
                expected_version=iniciado.pagamento.versao,
                timestamp=instante,
                referencia_externa=f"operacional:{self.contexto.usuario_id}",
            )
        elif metodo is MetodoPagamento.PIX and entrada.pix_sandbox:
            webhook = ProvedorPagamentoFake().normalizar_webhook(
                {
                    "evento_externo": f"sandbox:{entrada.checkout_id}",
                    "id_externo": f"sandbox:{entrada.checkout_id}",
                    "tipo": "confirmado",
                    "valor": entrada.total.valor,
                    "timestamp": instante,
                    "assinatura_validada": True,
                    "idempotency_key": f"{entrada.idempotency_key}:confirmacao",
                }
            )
            confirmado = processar_webhook(
                contexto=self.contexto,
                repositorio=recursos.pagamentos,
                pagamento_id=comando.pagamento_id,
                webhook=webhook,
                expected_version=iniciado.pagamento.versao,
            )
        else:
            return self._registrar_pendente(
                pdv=pdv,
                entrada=entrada,
                pedido_id=str(pedido.id),
                pagamento_id=comando.pagamento_id,
                instante=instante,
                motivo="aguardando_confirmacao_financeira",
            )

        if confirmado is None or confirmado.pagamento.status is not PagamentoStatus.PAGO:
            return self._registrar_pendente(
                pdv=pdv,
                entrada=entrada,
                pedido_id=str(pedido.id),
                pagamento_id=comando.pagamento_id,
                instante=instante,
                motivo="pagamento_nao_liquidado",
            )
        if not confirmado.idempotente:
            recursos.registrar_efeitos(
                eventos=confirmado.eventos, auditorias=confirmado.auditorias
            )
        self.fault("after_confirmacao")

        confirmado_pedido = transicionar_pedido(
            tenant_id=pedido.tenant_id,
            unidade_id=pedido.unidade_id,
            pedido_id=pedido.id,
            destino=PedidoStatus.CONFIRMADO,
            versao_esperada=pedido.versao,
            idempotency_key=IdempotencyKey(
                f"{entrada.idempotency_key}:pedido:confirmado"
            ),
            contexto=self.contexto,
            repositorio=recursos.pedidos,
            outbox=recursos.outbox,
            auditoria=recursos.auditoria,
            timestamp=instante,
            precondicoes={"dados_confirmados": True},
            metadata={"canal": "pdv", "pagamento": "confirmado"},
        )

        if checkout.reserva is not None:
            consumido = consumir_reserva(
                contexto=self.contexto,
                repositorio=recursos.estoque,
                pedido_id=str(pedido.id),
                pedido_version=confirmado_pedido.pedido.versao,
                idempotency_key=f"{entrada.idempotency_key}:estoque:consumo",
            )
            if not consumido.idempotente:
                recursos.registrar_efeitos(
                    eventos=consumido.eventos, auditorias=consumido.auditorias
                )
        self.fault("after_estoque_canonico")

        criterio = avaliar_criterio_financeiro(
            contexto=self.contexto,
            pagamento=confirmado.pagamento,
            pedido_id=str(pedido.id),
            timestamp=instante,
        )
        criterio = recursos.pagamentos.salvar_criterio(
            self.contexto.tenant_id,
            self.contexto.unidade_id,
            criterio,
            f"{entrada.idempotency_key}:criterio",
            _fingerprint(
                str(pedido.id),
                comando.pagamento_id,
                criterio.codigo,
                criterio.valor_reconhecivel.valor,
            ),
        )
        reconhecida = reconhecer_venda(
            contexto=self.contexto,
            repositorio=recursos.pagamentos,
            criterio=criterio,
            metodo=metodo,
            idempotency_key=f"{entrada.idempotency_key}:venda",
            timestamp=instante,
            produto_id_legado=entrada.produto_id,
        )
        if not reconhecida.idempotente:
            recursos.registrar_efeitos(
                eventos=reconhecida.eventos, auditorias=reconhecida.auditorias
            )
        self.fault("after_venda_financeira")

        venda = self.legado.criar_venda_uma_vez(entrada, instante=instante)
        self.legado.baixar_estoque_uma_vez(entrada, consumos_legados, instante)
        self.legado.aplicar_cashback_uma_vez(entrada, instante)
        self.fault("after_projecoes_legadas")

        pdv.criar_link(
            tenant=self.contexto.tenant_id,
            unidade=self.contexto.unidade_id,
            pedido_id=str(pedido.id),
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            instante=instante,
        )
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
            pagamento_id=comando.pagamento_id,
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
            pagamento_id=comando.pagamento_id,
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
            valor_pedido=entrada.total.valor,
            valor_pagamento=confirmado.pagamento.valor_pago.valor,
            valor_venda_financeira=reconhecida.venda.valor.valor,
            valor_venda_legada=Decimal(str(venda.valor_total)),
            estoque_estrategia="canonico_autoritativo_legado_projecao",
            cashback_usado=entrada.desconto_cashback.valor
            if entrada.usar_cashback
            else Decimal(0),
            cashback_ganho=_cashback_ganho(entrada),
            status="divergente" if divergencias else "conciliado",
            divergencias=list(divergencias),
            criado_em=instante,
        )
        troco = confirmado.confirmacao.troco if confirmado.confirmacao else Dinheiro(0)
        return ResultadoPDV(
            "authoritative_canary",
            True,
            pedido_id=str(pedido.id),
            pagamento_id=comando.pagamento_id,
            venda_financeira_id=reconhecida.venda.id,
            venda_legada_id=str(venda.id),
            troco=troco,
        )
