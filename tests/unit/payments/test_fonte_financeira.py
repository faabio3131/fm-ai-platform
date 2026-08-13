from datetime import datetime, timezone

import pytest

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos import (
    MetodoPagamento,
    RepositorioPagamentosEmMemoria,
    confirmar_pagamento,
    criar_obrigacao_pagamento,
)
from core.pagamentos.erros import FonteFinanceiraNaoConfiavel
from core.seguranca import ContextoExecucao, Permissao
from core.seguranca.permissoes import Papel

AGORA = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _contexto(permissao: Permissao) -> ContextoExecucao:
    return ContextoExecucao(
        "tenant",
        "unidade",
        "caixa",
        frozenset({Papel.CAIXA}),
        frozenset({permissao}),
        "corr-fonte-financeira",
        AGORA,
        "teste",
        unidades_permitidas=frozenset({"unidade"}),
    )


@pytest.mark.parametrize(
    "metodo",
    [
        MetodoPagamento.PIX,
        MetodoPagamento.CARTAO_CREDITO,
        MetodoPagamento.CARTAO_DEBITO,
        MetodoPagamento.VOUCHER,
        MetodoPagamento.OUTRO,
        MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        MetodoPagamento.RECEBIMENTO_POSTERIOR,
    ],
)
def test_metodo_nao_dinheiro_nao_pode_ser_liquidado_por_confirmacao_manual(
    metodo: MetodoPagamento,
) -> None:
    repo = RepositorioPagamentosEmMemoria()
    inicial = criar_obrigacao_pagamento(
        contexto=_contexto(Permissao.PAGAMENTO_REGISTRAR),
        repositorio=repo,
        pagamento_id="pay",
        pedido_id="pedido",
        valor_previsto=Dinheiro("40"),
        metodo=metodo,
        idempotency_key="obrigacao",
        timestamp=AGORA,
    )

    with pytest.raises(FonteFinanceiraNaoConfiavel):
        confirmar_pagamento(
            contexto=_contexto(Permissao.PAGAMENTO_CONFIRMAR),
            repositorio=repo,
            pagamento_id="pay",
            valor=Dinheiro("40"),
            metodo=metodo,
            idempotency_key="confirmacao-manual",
            expected_version=1,
            timestamp=AGORA,
        )

    persistido = repo.buscar_pagamento("tenant", "unidade", "pay")
    assert persistido is not None
    assert persistido.status == inicial.pagamento.status
    assert persistido.status != PagamentoStatus.PAGO
    assert len(repo.listar_transacoes("tenant", "unidade", "pay")) == 1
