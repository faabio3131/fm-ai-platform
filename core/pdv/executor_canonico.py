"""Executor canary do PDV sobre o núcleo transacional canônico da V1."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from application.checkout import (
    confirmar_checkout_sem_obrigacao_financeira_em_transacao,
    executar_checkout_em_transacao,
)
from application.order_result_orchestrator import (
    orquestrar_resultado_pagamento_em_transacao,
)
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.servicos import (
    confirmar_pagamento,
    confirmar_pagamento_presencial,
    processar_webhook,
)
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1

from .adaptadores_sqlalchemy import FaultInjector, RepositorioPDVSQLAlchemy
from .cutover_canonico import montar_checkout_pdv
from .finalizacao_pendente import RepositorioFinalizacaoPendentePDV
from .modelos import EntradaPDV, ResultadoPDV, mapear_metodo
from .reconciliacao import ReconciliacaoPDV, detectar_divergencias
from .repositorios import PonteProjecaoCompatLegadaPDV


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
        legado: PonteProjecaoCompatLegadaPDV,
        fault: FaultInjector | None = None,
        permitir_pix_sandbox: bool = False,
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.legado = legado
        self.fault = fault or (lambda _ponto: None)
        self.permitir_pix_sandbox = permitir_pix_sandbox

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
        RepositorioFinalizacaoPendentePDV(self.session).registrar(
            tenant_id=self.contexto.tenant_id,
            unidade_id=self.contexto.unidade_id,
            pedido_id=pedido_id,
            pagamento_id=pagamento_id,
            entrada=entrada,
            instante=instante,
        )
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
        if entrada.pix_sandbox and not self.permitir_pix_sandbox:
            raise RuntimeError("pix_sandbox_nao_autorizado")
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

        comando, _consumos_legados = montar_checkout_pdv(
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
        self.fault("after_checkout_canonico")

        if entrada.total.valor == 0:
            if (
                iniciado is not None
                or comando.pagamento_id is not None
                or comando.metodo_pagamento is not None
            ):
                raise RuntimeError("pdv_saldo_zero_com_obrigacao_financeira")
            confirmado_zero = confirmar_checkout_sem_obrigacao_financeira_em_transacao(
                checkout=checkout,
                contexto=self.contexto,
                recursos=recursos,
                timestamp=instante,
            )
            pedido = confirmado_zero.pedido
            self.fault("after_confirmacao_saldo_zero")

            venda = self.legado.criar_venda_uma_vez(entrada, instante=instante)
            self.legado.aplicar_cashback_uma_vez(entrada, instante)
            self.fault("after_projecoes_legadas")
            self.fault("before_reconciliacao")
            pdv.reconciliar(
                tenant_id=self.contexto.tenant_id,
                unidade_id=self.contexto.unidade_id,
                modo="authoritative_canary",
                pedido_id=str(pedido.id),
                pagamento_id=None,
                venda_financeira_id=None,
                venda_legada_id=str(venda.id),
                idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
                valor_pedido=entrada.total.valor,
                valor_pagamento=None,
                valor_venda_financeira=None,
                valor_venda_legada=Decimal(str(venda.valor_total)),
                estoque_estrategia="canonico_reservado",
                cashback_usado=(
                    entrada.desconto_cashback.valor
                    if entrada.usar_cashback
                    else Decimal(0)
                ),
                cashback_ganho=_cashback_ganho(entrada),
                status="conciliado",
                divergencias=[],
                criado_em=instante,
            )
            return ResultadoPDV(
                "authoritative_canary",
                True,
                pedido_id=str(pedido.id),
                venda_legada_id=str(venda.id),
                troco=Dinheiro(Decimal(0)),
            )

        if iniciado is None or comando.pagamento_id is None:
            raise RuntimeError("pdv_checkout_sem_obrigacao_financeira")

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
        elif (
            metodo
            in {MetodoPagamento.CARTAO_CREDITO, MetodoPagamento.CARTAO_DEBITO}
            and entrada.confirmacao_presencial
        ):
            confirmado = confirmar_pagamento_presencial(
                contexto=self.contexto,
                repositorio=recursos.pagamentos,
                pagamento_id=comando.pagamento_id,
                valor=entrada.total,
                metodo=metodo,
                idempotency_key=f"{entrada.idempotency_key}:confirmacao",
                expected_version=iniciado.pagamento.versao,
                timestamp=instante,
                referencia_externa=(
                    f"presencial:{entrada.terminal_id}:{self.contexto.usuario_id}"
                ),
            )
        elif metodo is MetodoPagamento.PIX and entrada.pix_sandbox:
            from core.pagamentos.adapters import ProvedorPagamentoFake

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

        resultado_ordem = orquestrar_resultado_pagamento_em_transacao(
            recursos=recursos,
            pagamento=confirmado.pagamento,
            timestamp=instante,
        )
        if (
            not resultado_ordem.finalizado
            or resultado_ordem.pedido_id is None
            or resultado_ordem.venda_financeira_id is None
        ):
            raise RuntimeError("pdv_resultado_financeiro_nao_finalizado")

        # Hooks históricos de rollback permanecem durante o cutover. Neste ponto
        # a reserva segue ativa; consumo pertence ao início real da produção.
        self.fault("after_estoque_canonico")
        self.fault("after_venda_financeira")

        venda = self.legado.criar_venda_uma_vez(entrada, instante=instante)
        self.legado.aplicar_cashback_uma_vez(entrada, instante)
        self.fault("after_projecoes_legadas")

        pdv.criar_link(
            tenant=self.contexto.tenant_id,
            unidade=self.contexto.unidade_id,
            pedido_id=str(pedido.id),
            venda_financeira_id=resultado_ordem.venda_financeira_id,
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
            venda_financeira_id=resultado_ordem.venda_financeira_id,
            venda_legada_id=str(venda.id),
            valor_pedido=entrada.total.valor,
            valor_pagamento=confirmado.pagamento.valor_pago.valor,
            valor_venda_financeira=confirmado.pagamento.valor_pago.valor,
            valor_venda_legada=Decimal(str(venda.valor_total)),
            estoque_estrategia="canonico_reservado_aguardando_producao",
        )
        divergencias = detectar_divergencias(
            base_reconciliacao,
            vendas_legadas=contagens.get("VENDA_LEGADA", 0),
            efeitos_estoque=contagens.get("ESTOQUE_LEGADO", 0),
            efeitos_cashback_usado=contagens.get("CASHBACK_USADO", 0),
        )
        self.fault("before_reconciliacao")
        pdv.reconciliar(
            tenant_id=self.contexto.tenant_id,
            unidade_id=self.contexto.unidade_id,
            modo="authoritative_canary",
            pedido_id=str(pedido.id),
            pagamento_id=comando.pagamento_id,
            venda_financeira_id=resultado_ordem.venda_financeira_id,
            venda_legada_id=str(venda.id),
            idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
            valor_pedido=entrada.total.valor,
            valor_pagamento=confirmado.pagamento.valor_pago.valor,
            valor_venda_financeira=confirmado.pagamento.valor_pago.valor,
            valor_venda_legada=Decimal(str(venda.valor_total)),
            estoque_estrategia="canonico_reservado_aguardando_producao",
            cashback_usado=entrada.desconto_cashback.valor
            if entrada.usar_cashback
            else Decimal(0),
            cashback_ganho=_cashback_ganho(entrada),
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
            pagamento_id=comando.pagamento_id,
            venda_financeira_id=resultado_ordem.venda_financeira_id,
            venda_legada_id=str(venda.id),
            troco=troco,
        )
