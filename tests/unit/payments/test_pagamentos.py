from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier, Thread

import pytest

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos import (
    FlagsPagamentosV1,
    MetodoPagamento,
    ProvedorPagamentoFake,
    RepositorioPagamentosEmMemoria,
    avaliar_criterio_financeiro,
    confirmar_pagamento,
    criar_obrigacao_pagamento,
    processar_webhook,
    reconhecer_venda,
    registrar_estorno,
)
from core.pagamentos.erros import OperacaoPagamentoNaoAutorizada
from core.seguranca import ContextoExecucao, Permissao
from core.seguranca.permissoes import Papel

AGORA = datetime(2026, 8, 8, tzinfo=timezone.utc)


def ctx(
    *permissoes: Permissao,
    tenant: str = "t",
    unidade: str = "u",
    papel: Papel = Papel.CAIXA,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant,
        unidade,
        "ator",
        frozenset({papel}),
        frozenset(permissoes),
        "corr",
        AGORA,
        "teste",
        unidades_permitidas=frozenset({unidade}),
    )


def criar(
    repo: RepositorioPagamentosEmMemoria,
    valor: str = "40",
    metodo: MetodoPagamento = MetodoPagamento.DINHEIRO,
):
    return criar_obrigacao_pagamento(
        contexto=ctx(Permissao.PAGAMENTO_REGISTRAR),
        repositorio=repo,
        pagamento_id="pay",
        pedido_id="ped",
        valor_previsto=Dinheiro(Decimal(valor)),
        metodo=metodo,
        idempotency_key="obrigacao",
        timestamp=AGORA,
    )


def test_parcial_total_dinheiro_troco_e_estorno_append_only() -> None:
    repo = RepositorioPagamentosEmMemoria()
    criar(repo)
    parcial = confirmar_pagamento(
        contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR),
        repositorio=repo,
        pagamento_id="pay",
        valor=Dinheiro(Decimal("10")),
        metodo=MetodoPagamento.DINHEIRO,
        idempotency_key="c1",
        expected_version=1,
        timestamp=AGORA,
    )
    assert parcial.pagamento.status == PagamentoStatus.PARCIALMENTE_PAGO
    final = confirmar_pagamento(
        contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR),
        repositorio=repo,
        pagamento_id="pay",
        valor=Dinheiro(Decimal("50")),
        valor_recebido=Dinheiro(Decimal("50")),
        metodo=MetodoPagamento.DINHEIRO,
        idempotency_key="c2",
        expected_version=2,
        timestamp=AGORA,
    )
    assert final.pagamento.valor_pago == Dinheiro(Decimal("40"))
    assert final.confirmacao and final.confirmacao.troco == Dinheiro(Decimal("20"))
    estorno = registrar_estorno(
        contexto=ctx(Permissao.PAGAMENTO_ESTORNAR, papel=Papel.FINANCEIRO),
        repositorio=repo,
        pagamento_id="pay",
        valor=Dinheiro(Decimal("5")),
        motivo="devolucao",
        idempotency_key="e1",
        expected_version=3,
        timestamp=AGORA,
    )
    assert estorno.pagamento.status == PagamentoStatus.ESTORNADO_PARCIAL
    assert len(repo.listar_transacoes("t", "u", "pay")) == 4


def test_webhook_invalido_e_dez_duplicados_confirmam_uma_vez() -> None:
    repo = RepositorioPagamentosEmMemoria()
    criar(repo, metodo=MetodoPagamento.PIX)
    fake = ProvedorPagamentoFake()
    webhook = fake.normalizar_webhook(
        {
            "evento_externo": "evt",
            "id_externo": "ext",
            "tipo": "confirmado",
            "valor": "40",
            "timestamp": AGORA,
            "assinatura_validada": True,
            "idempotency_key": "wh",
        }
    )
    primeiro = processar_webhook(
        contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR),
        repositorio=repo,
        pagamento_id="pay",
        webhook=webhook,
        expected_version=1,
    )
    assert primeiro and primeiro.pagamento.status == PagamentoStatus.PAGO
    for _ in range(9):
        repetido = processar_webhook(
            contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR),
            repositorio=repo,
            pagamento_id="pay",
            webhook=webhook,
            expected_version=2,
        )
        assert repetido and repetido.idempotente
    assert (
        len([t for t in repo.listar_transacoes("t", "u", "pay") if t.valor.valor]) == 1
    )


def test_criterio_e_venda_exatamente_uma_vez_concorrente() -> None:
    repo = RepositorioPagamentosEmMemoria()
    criar(repo)
    pago = confirmar_pagamento(
        contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR),
        repositorio=repo,
        pagamento_id="pay",
        valor=Dinheiro(Decimal("40")),
        metodo=MetodoPagamento.DINHEIRO,
        idempotency_key="c",
        expected_version=1,
        timestamp=AGORA,
    ).pagamento
    criterio = avaliar_criterio_financeiro(
        contexto=ctx(), pagamento=pago, pedido_id="ped", timestamp=AGORA
    )
    barreira = Barrier(2)
    resultados, erros = [], []

    def worker() -> None:
        barreira.wait()
        try:
            resultados.append(
                reconhecer_venda(
                    contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR),
                    repositorio=repo,
                    criterio=criterio,
                    metodo=MetodoPagamento.DINHEIRO,
                    idempotency_key="venda",
                    timestamp=AGORA,
                )
            )
        except Exception as exc:  # pragma: no cover - diagnostico concorrente
            erros.append(exc)

    threads = [Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not erros and len(resultados) == 2
    assert len(repo.listar_vendas("t", "u")) == 1
    assert sum(r.idempotente for r in resultados) == 1


def test_cross_tenant_e_gerente_ia_negados_uniformemente() -> None:
    repo = RepositorioPagamentosEmMemoria()
    criar(repo)
    with pytest.raises(OperacaoPagamentoNaoAutorizada):
        confirmar_pagamento(
            contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR, papel=Papel.GERENTE_IA),
            repositorio=repo,
            pagamento_id="pay",
            valor=Dinheiro(Decimal("40")),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="x",
            expected_version=1,
            timestamp=AGORA,
        )
    with pytest.raises(Exception, match="recurso_indisponivel"):
        confirmar_pagamento(
            contexto=ctx(Permissao.PAGAMENTO_CONFIRMAR, tenant="outro"),
            repositorio=repo,
            pagamento_id="pay",
            valor=Dinheiro(Decimal("40")),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="x",
            expected_version=1,
            timestamp=AGORA,
        )


def test_flags_dormentes_e_decimal_roundtrip() -> None:
    assert FlagsPagamentosV1() == FlagsPagamentosV1(False, False, False)
    assert [Dinheiro(Decimal(v)).valor for v in ("0.01", "29.90", "999999.99")] == [
        Dinheiro(Decimal(v)).valor for v in ("0.01", "29.90", "999999.99")
    ]
