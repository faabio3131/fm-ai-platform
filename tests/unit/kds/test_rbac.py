from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from core.kds import (
    ErroKDS,
    ProducaoItem,
    RepositorioAuditoriaEmMemoria,
    RepositorioKDSSQLAlchemy,
    ServicoKDS,
)
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def contexto(papel: Papel):
    return ContextoExecucao(
        "tenant-1",
        "unidade-1",
        f"ator-{papel.value}",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{papel.value}",
        AGORA,
        "teste-kds",
        unidades_permitidas=frozenset({"unidade-1"}),
    )


def producao(status: str) -> ProducaoItem:
    return ProducaoItem(
        "prod-1",
        "tenant-1",
        "unidade-1",
        "pedido-1",
        "item-1",
        "setor-1",
        status,
        0,
        Decimal("1.0000"),
        1,
        1,
        AGORA,
        AGORA,
    )


class RepositorioMinimo:
    def __init__(self, item: ProducaoItem) -> None:
        self.item = item

    def obter_producao(self, tenant_id: str, unidade_id: str, producao_id: str):
        if (tenant_id, unidade_id, producao_id) == (
            self.item.tenant_id,
            self.item.unidade_id,
            self.item.producao_id,
        ):
            return self.item
        return None


def servico(item: ProducaoItem) -> ServicoKDS:
    return ServicoKDS(
        cast(RepositorioKDSSQLAlchemy, RepositorioMinimo(item)),
        RepositorioAuditoriaEmMemoria(),
        agora=lambda: AGORA,
    )


def test_cozinha_nao_registra_retirada_da_expedicao():
    with pytest.raises(ErroKDS) as erro:
        servico(producao("pronta")).transicionar(
            contexto(Papel.COZINHA),
            producao_id="prod-1",
            destino="retirada",
            versao_esperada=1,
            idempotency_key="retirar",
            precondicoes={"conferencia_realizada": True, "posse_transferida": True},
        )
    assert erro.value.codigo == "permissao_insuficiente"


def test_expedicao_nao_inicia_producao_da_cozinha():
    with pytest.raises(ErroKDS) as erro:
        servico(producao("aceita")).transicionar(
            contexto(Papel.EXPEDICAO),
            producao_id="prod-1",
            destino="em_preparo",
            versao_esperada=1,
            idempotency_key="iniciar",
            precondicoes={"estoque_resolvido": True, "estacao_apta": True},
        )
    assert erro.value.codigo == "permissao_insuficiente"
