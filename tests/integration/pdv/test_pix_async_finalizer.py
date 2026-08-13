from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from application.finalizacao_pagamento import finalizar_pagamento_liquidado_em_transacao
from core.estoque.modelos_orm import ReservaEstoqueORM, SaldoEstoqueORM
from core.pagamentos.adapters import ProvedorPagamentoFake
from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pagamentos.servicos import processar_webhook
from core.pdv.modelos_orm import FinalizacaoPendentePDVORM
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM
from infra.transacoes.uow import RecursosTransacionaisV1

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def test_pix_pago_assincrono_finaliza_tudo_e_replay_nao_duplica(
    fabrica, contexto, entrada
):
    pix = replace(
        entrada,
        forma_pagamento="Pix (Gerar QR Code Instantâneo)",
        valor_recebido=None,
        pix_sandbox=False,
        confirmacao_presencial=False,
    )
    pendente = executar(fabrica, contexto, pix, ModoPDV.AUTHORITATIVE_CANARY)
    assert not pendente.sucesso
    assert pendente.pagamento_id is not None
    assert pendente.pedido_id is not None

    instante = datetime.now(timezone.utc)
    with fabrica() as session:
        recursos = RecursosTransacionaisV1(session)
        pagamento = recursos.pagamentos.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pendente.pagamento_id
        )
        assert pagamento is not None
        webhook = ProvedorPagamentoFake().normalizar_webhook(
            {
                "evento_externo": "provider-event-async-1",
                "id_externo": "provider-order-async-1",
                "tipo": "confirmado",
                "valor": pix.total.valor,
                "timestamp": instante,
                "assinatura_validada": True,
                "idempotency_key": f"{pix.idempotency_key}:provider-paid",
            }
        )
        confirmado = processar_webhook(
            contexto=contexto,
            repositorio=recursos.pagamentos,
            pagamento_id=pagamento.id,
            webhook=webhook,
            expected_version=pagamento.versao,
        )
        assert confirmado is not None
        if not confirmado.idempotente:
            recursos.registrar_efeitos(
                eventos=confirmado.eventos,
                auditorias=confirmado.auditorias,
            )
        finalizado = finalizar_pagamento_liquidado_em_transacao(
            recursos=recursos,
            pagamento=confirmado.pagamento,
            timestamp=instante,
        )
        assert finalizado.aplicavel
        assert finalizado.finalizada
        assert not finalizado.idempotente
        session.commit()

    with fabrica() as session:
        pagamento_row = session.get(PagamentoORM, pendente.pagamento_id)
        pedido_row = session.get(PedidoORM, pendente.pedido_id)
        assert pagamento_row is not None and pagamento_row.status == "pago"
        assert pedido_row is not None and pedido_row.status == "confirmado"
        reserva = session.scalar(
            select(ReservaEstoqueORM).where(
                ReservaEstoqueORM.pedido_id == pendente.pedido_id
            )
        )
        assert reserva is not None and reserva.status == "consumida"
        saldo = session.get(
            SaldoEstoqueORM,
            (contexto.tenant_id, contexto.unidade_id, "legacy:insumo:1"),
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal("9")
        assert Decimal(str(saldo.saldo_reservado)) == Decimal("0")
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert session.get(InsumoTeste, 1).saldo_atual == 9
        cliente = session.get(ClienteTeste, 1)
        assert cliente is not None
        assert Decimal(str(cliente.saldo_cashback)) == Decimal("6.25")
        assert Decimal(str(cliente.total_gasto)) == Decimal("24.9")
        trabalho = session.scalar(
            select(FinalizacaoPendentePDVORM).where(
                FinalizacaoPendentePDVORM.pagamento_id == pendente.pagamento_id
            )
        )
        assert trabalho is not None
        assert trabalho.status == "FINALIZADA"
        assert trabalho.venda_financeira_id is not None
        assert trabalho.venda_legada_id is not None

    with fabrica() as session:
        recursos = RecursosTransacionaisV1(session)
        pagamento = recursos.pagamentos.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pendente.pagamento_id
        )
        assert pagamento is not None
        replay = finalizar_pagamento_liquidado_em_transacao(
            recursos=recursos,
            pagamento=pagamento,
            timestamp=instante,
        )
        assert replay.finalizada
        assert replay.idempotente
        session.commit()

    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert session.get(InsumoTeste, 1).saldo_atual == 9
