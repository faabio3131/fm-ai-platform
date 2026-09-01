from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier

from sqlalchemy import func, select

from application.finalizacao_pagamento import (
    ResultadoFinalizacaoPagamento,
    finalizar_pagamento_liquidado_em_transacao,
)
from core.pagamentos.adapters import ProvedorPagamentoFake
from core.pagamentos.modelos_orm import VendaFinanceiraORM
from core.pagamentos.servicos import processar_webhook
from core.pdv.modelos_orm import FinalizacaoPendentePDVORM
from core.pdv.roteamento import ModoPDV
from infra.transacoes.uow import RecursosTransacionaisV1

from .conftest import InsumoTeste, VendaTeste
from .helpers import executar


def test_duas_fontes_concorrentes_finalizam_efeito_economico_uma_vez(
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
    assert pendente.pagamento_id is not None

    instante = datetime.now(timezone.utc)
    with fabrica() as session:
        recursos = RecursosTransacionaisV1(session)
        pagamento = recursos.pagamentos.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pendente.pagamento_id
        )
        assert pagamento is not None
        webhook = ProvedorPagamentoFake().normalizar_webhook(
            {
                "evento_externo": "race-event-paid",
                "id_externo": "race-order-paid",
                "tipo": "confirmado",
                "valor": pix.total.valor,
                "timestamp": instante,
                "assinatura_validada": True,
                "idempotency_key": f"{pix.idempotency_key}:race-paid",
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
                eventos=confirmado.eventos, auditorias=confirmado.auditorias
            )
        session.commit()

    barreira = Barrier(2)

    def worker():
        barreira.wait()
        try:
            with fabrica() as session:
                recursos = RecursosTransacionaisV1(session)
                pagamento = recursos.pagamentos.buscar_pagamento(
                    contexto.tenant_id, contexto.unidade_id, pendente.pagamento_id
                )
                assert pagamento is not None
                resultado = finalizar_pagamento_liquidado_em_transacao(
                    recursos=recursos,
                    pagamento=pagamento,
                    timestamp=instante,
                )
                session.commit()
                return resultado
        except Exception as exc:  # noqa: BLE001 - race test captures worker outcome
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: worker(), range(2)))

    concluidos = [
        item
        for item in resultados
        if isinstance(item, ResultadoFinalizacaoPagamento) and item.finalizada
    ]
    assert concluidos

    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert session.get(InsumoTeste, 1).saldo_atual == 9
        trabalho = session.scalar(
            select(FinalizacaoPendentePDVORM).where(
                FinalizacaoPendentePDVORM.pagamento_id == pendente.pagamento_id
            )
        )
        assert trabalho is not None
        assert trabalho.status == "FINALIZADA"
