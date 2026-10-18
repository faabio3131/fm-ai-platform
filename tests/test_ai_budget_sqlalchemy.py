from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from infra.ai_budget_sqlalchemy import (
    AIBudgetBase,
    ConflitoReservaIA,
    EstadoReservaIA,
    FranquiaEsgotadaIA,
    LedgerFranquiasIASQLAlchemy,
    OrcamentoIndisponivelIA,
    ReservaAIBudgetORM,
)

NOW = datetime(2026, 10, 18, 19, 0, tzinfo=timezone.utc)


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"timeout": 20})
    AIBudgetBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    obj = LedgerFranquiasIASQLAlchemy(factory)
    obj.sincronizar_politica(
        budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1",
        capability="tool_planning", ciclo_id="ciclo-out-26", moeda="USD",
        limite=Decimal("10"), revisao_politica=1,
        vigencia_inicio=NOW - timedelta(days=1),
        vigencia_fim=NOW + timedelta(days=30),
    )
    return obj, factory


def reserve(ledger, *, id: str = "res-1", amount="3", tenant="tenant-a", unit="loja-1", attempt="0"):
    return ledger.reservar(
        reserva_id=id, budget_id="bud-a-10", tenant_id=tenant, unidade_id=unit,
        capability="tool_planning", ciclo_id="ciclo-out-26", request_id=id,
        attempt_key=attempt, provider="openai", model="model-a",
        valor=Decimal(amount), agora=NOW,
    )


def test_reserva_concilia_custo_e_libera_sobra(ledger):
    obj, _ = ledger
    assert reserve(obj) is EstadoReservaIA.RESERVED
    assert obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1").disponivel == Decimal("7")
    assert obj.finalizar(reserva_id="res-1", tenant_id="tenant-a", unidade_id="loja-1", valor_real=Decimal("2"), agora=NOW) is EstadoReservaIA.COMMITTED
    saldo = obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1")
    assert (saldo.consumido, saldo.reservado, saldo.disponivel) == (Decimal("2"), Decimal("0"), Decimal("8"))


def test_bloqueia_antes_de_exceder_e_nao_cria_debito(ledger):
    obj, factory = ledger
    with pytest.raises(FranquiaEsgotadaIA):
        reserve(obj, amount="11")
    assert obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1").reservado == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ReservaAIBudgetORM)) == 0


def test_tentativa_repetida_nao_duplica_reserva(ledger):
    obj, _ = ledger
    assert reserve(obj) is EstadoReservaIA.RESERVED
    assert reserve(obj) is EstadoReservaIA.RESERVED
    assert obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1").reservado == Decimal("3")
    with pytest.raises(ConflitoReservaIA):
        reserve(obj, amount="4")


def test_timeout_mantem_valor_bloqueado_ate_conciliar(ledger):
    obj, _ = ledger
    reserve(obj, amount="9")
    obj.finalizar(reserva_id="res-1", tenant_id="tenant-a", unidade_id="loja-1", valor_real=None, agora=NOW)
    with pytest.raises(FranquiaEsgotadaIA):
        reserve(obj, id="res-2", amount="2")
    obj.finalizar(reserva_id="res-1", tenant_id="tenant-a", unidade_id="loja-1", valor_real=Decimal("4"), agora=NOW)
    assert obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1").disponivel == Decimal("6")


def test_cobranca_superior_a_reserva_e_registrada_e_para_novas_chamadas(ledger):
    obj, _ = ledger
    reserve(obj, amount="9")
    obj.finalizar(reserva_id="res-1", tenant_id="tenant-a", unidade_id="loja-1", valor_real=Decimal("12"), agora=NOW)
    saldo = obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1")
    assert (saldo.consumido, saldo.disponivel) == (Decimal("12"), Decimal("0"))
    with pytest.raises(FranquiaEsgotadaIA):
        reserve(obj, id="res-2", amount="0.01")


def test_libera_somente_com_prova_inequivoca_sem_cobranca(ledger):
    obj, _ = ledger
    reserve(obj)
    obj.finalizar(reserva_id="res-1", tenant_id="tenant-a", unidade_id="loja-1", valor_real=None, agora=NOW, sem_cobranca_comprovada=True)
    assert obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1").disponivel == Decimal("10")


def test_isolamento_de_tenant_e_unidade(ledger):
    obj, _ = ledger
    for tenant, unit in [("tenant-b", "loja-1"), ("tenant-a", "loja-2")]:
        with pytest.raises(OrcamentoIndisponivelIA):
            reserve(obj, tenant=tenant, unit=unit)
        with pytest.raises(OrcamentoIndisponivelIA):
            obj.saldo(budget_id="bud-a-10", tenant_id=tenant, unidade_id=unit)


def test_politica_versionada_nao_retrocede_nem_reset_consumo(ledger):
    obj, _ = ledger
    reserve(obj, amount="4")
    p = dict(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1",
        capability="tool_planning", ciclo_id="ciclo-out-26", moeda="USD",
        vigencia_inicio=NOW - timedelta(days=1), vigencia_fim=NOW + timedelta(days=30))
    obj.sincronizar_politica(**p, limite=Decimal("3"), revisao_politica=2)
    assert obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1").reservado == Decimal("4")
    with pytest.raises(FranquiaEsgotadaIA):
        reserve(obj, id="res-2", amount="0.1")
    with pytest.raises(ConflitoReservaIA):
        obj.sincronizar_politica(**p, limite=Decimal("200"), revisao_politica=1)
    with pytest.raises(ConflitoReservaIA):
        obj.sincronizar_politica(**p, limite=Decimal("200"), revisao_politica=2)


def test_concorrencia_nao_excede_orcamento(ledger):
    obj, _ = ledger
    def attempt(i):
        try:
            reserve(obj, id=f"res-{i}", amount="3")
            return True
        except FranquiaEsgotadaIA:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        decisions = list(pool.map(attempt, range(20)))
    assert sum(decisions) == 3
    saldo = obj.saldo(budget_id="bud-a-10", tenant_id="tenant-a", unidade_id="loja-1")
    assert (saldo.reservado, saldo.consumido, saldo.disponivel) == (Decimal("9"), Decimal("0"), Decimal("1"))
