from datetime import datetime, timezone

import pytest

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.erros import ConflitoIdempotenciaPagamento
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.repositorios import RepositorioPagamentosEmMemoria

AGORA = datetime(2026, 8, 12, 22, tzinfo=timezone.utc)


def _transacao(tenant: str, unidade: str, pagamento: str, chave: str):
    return TransacaoPagamento(
        f"tx-{tenant}",
        pagamento,
        tenant,
        unidade,
        TipoTransacao.INICIACAO,
        StatusTransacao.PENDENTE,
        Dinheiro(0),
        MetodoPagamento.PIX,
        "pagbank",
        "ORDE_MESMO_ID",
        chave,
        AGORA,
        AGORA,
        f"corr-{tenant}",
        None,
        (),
    )


def test_referencia_externa_ambigua_entre_tenants_falha_fechado() -> None:
    repo = RepositorioPagamentosEmMemoria()
    repo.append_transacao(_transacao("tenant-a", "loja-a", "pay-a", "idem-a"), "fp-a")
    repo.append_transacao(_transacao("tenant-b", "loja-b", "pay-b", "idem-b"), "fp-b")

    with pytest.raises(
        ConflitoIdempotenciaPagamento, match="referencia_externa_ambigua"
    ):
        repo.buscar_transacao_externa(
            "pagbank", "ORDE_MESMO_ID", TipoTransacao.INICIACAO
        )
