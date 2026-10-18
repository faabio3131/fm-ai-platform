"""Prova interna do bloqueio preventivo antes de cada tentativa de IA."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.ai_pricing import CatalogoPrecosIAEmMemoria, PriceSnapshotIA, TarifaIA
from core.ai_router import (
    AIModelRouter,
    CapabilityIA,
    ErroAIRouter,
    FalhaRotaTransitoria,
    MedidorUsoIAEmMemoria,
    RespostaModeloIA,
    RotaIA,
    SolicitacaoIA,
)
from infra.ai_budget_guard import AIFranchiseBudgetGuard, PoliticaReservaIA
from infra.ai_budget_sqlalchemy import (
    AIBudgetBase,
    ConflitoReservaIA,
    FranquiaEsgotadaIA,
    LedgerFranquiasIASQLAlchemy,
    OrcamentoIndisponivelIA,
)

NOW = datetime(2026, 10, 18, 19, tzinfo=timezone.utc)


class ExecutorFixture:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def executar(self, *, rota: RotaIA, solicitacao: SolicitacaoIA) -> RespostaModeloIA:
        self.calls.append(rota.provider)
        result = self.outcomes[rota.provider]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, RespostaModeloIA)
        return result


def _rota(provider: str, priority: int) -> RotaIA:
    return RotaIA(
        configuracao_id="cfg-" + provider,
        provider=provider,
        model="model-" + provider,
        capability=CapabilityIA.TOOL_PLANNING,
        prioridade=priority,
        price_snapshot_id="snapshot-" + provider,
    )


def _solicitacao(request_id: str = "req-1", tenant_id: str = "tenant-a") -> SolicitacaoIA:
    return SolicitacaoIA(
        tenant_id=tenant_id,
        unidade_id="unit-a",
        request_id=request_id,
        correlation_id="corr-" + request_id,
        capability=CapabilityIA.TOOL_PLANNING,
        conteudo={"texto": "consulta"},
    )


def _snapshot(provider: str) -> PriceSnapshotIA:
    return PriceSnapshotIA(
        price_snapshot_id="snapshot-" + provider,
        provider=provider,
        model="model-" + provider,
        modalidade="text_tokens",
        moeda="USD",
        versao=1,
        vigencia_inicio=NOW - timedelta(days=1),
        vigencia_fim=None,
        tarifas=(
            TarifaIA(componente="input_tokens", preco=Decimal("2"), unidades_por_preco=1_000_000),
            TarifaIA(componente="output_tokens", preco=Decimal("10"), unidades_por_preco=1_000_000),
        ),
    )


@pytest.fixture
def setup_guard(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'router-guard.db'}")
    AIBudgetBase.metadata.create_all(engine)
    ledger = LedgerFranquiasIASQLAlchemy(sessionmaker(bind=engine, expire_on_commit=False))
    ledger.sincronizar_politica(
        budget_id="budget-1", tenant_id="tenant-a", unidade_id="unit-a",
        capability=CapabilityIA.TOOL_PLANNING.value, ciclo_id="2026-10",
        moeda="USD", limite=Decimal("2"),
        revisao_politica=1,
        vigencia_inicio=NOW - timedelta(days=1),
        vigencia_fim=NOW + timedelta(days=30),
    )
    def resolver(_req: SolicitacaoIA, _route: RotaIA) -> PoliticaReservaIA:
        return PoliticaReservaIA(
            tenant_id="tenant-a", unidade_id="unit-a",
            capability=CapabilityIA.TOOL_PLANNING.value,
            budget_id="budget-1", ciclo_id="2026-10",
            moeda="USD", maximo_por_tentativa=Decimal("1"),
        )
    guard = AIFranchiseBudgetGuard(
        ledger=ledger,
        resolver_politica_local=resolver,
        now=lambda: NOW,
    )
    return ledger, guard


def _router(guard, executor, *, routes=None, catalog=True):
    rotas = routes or (_rota("openai", 200),)
    meter = MedidorUsoIAEmMemoria()
    router = AIModelRouter(
        rotas=rotas,
        executor=executor,
        metering=meter,
        pricing_catalog=(
            CatalogoPrecosIAEmMemoria(tuple(_snapshot(r.provider) for r in rotas))
            if catalog else None
        ),
        budget_guard=guard,
        require_budget_guard=True,
        now=lambda: NOW,
    )
    return router, meter


def test_reserva_previa_e_custo_real_conciliado(setup_guard):
    ledger, guard = setup_guard
    executor = ExecutorFixture({"openai": RespostaModeloIA(
        conteudo="ok", input_tokens=1_000, output_tokens=500)})
    router, events = _router(guard, executor)
    assert router.executar(_solicitacao()).conteudo == "ok"
    saldo = ledger.saldo(budget_id="budget-1", tenant_id="tenant-a", unidade_id="unit-a")
    assert (saldo.consumido, saldo.reservado) == (Decimal("0.007"), Decimal(0))
    assert events.eventos[0].custo_real_calculado == Decimal("0.007")


def test_insuficiencia_nega_antes_de_chamar_provider(setup_guard):
    ledger, guard = setup_guard
    ledger.sincronizar_politica(
        budget_id="budget-1", tenant_id="tenant-a", unidade_id="unit-a",
        capability="tool_planning", ciclo_id="2026-10", moeda="USD",
        limite=Decimal("0.5"), revisao_politica=2,
        vigencia_inicio=NOW - timedelta(days=1),
        vigencia_fim=NOW + timedelta(days=30),
    )
    executor = ExecutorFixture({"openai": RespostaModeloIA(conteudo="nao")})
    router, _ = _router(guard, executor)
    with pytest.raises(FranquiaEsgotadaIA):
        router.executar(_solicitacao())
    assert executor.calls == []


def test_retry_idempotente_nao_reenvia_chamada_cobravel(setup_guard):
    _, guard = setup_guard
    executor = ExecutorFixture({"openai": RespostaModeloIA(
        conteudo="ok", input_tokens=1_000, output_tokens=500)})
    router, _ = _router(guard, executor)
    router.executar(_solicitacao())
    with pytest.raises(ConflitoReservaIA):
        router.executar(_solicitacao())
    assert executor.calls == ["openai"]


def test_timeout_reserva_fica_pendente_e_fallback_reserva_novamente(setup_guard):
    ledger, guard = setup_guard
    executor = ExecutorFixture({
        "openai": FalhaRotaTransitoria("timeout"),
        "gemini": RespostaModeloIA(conteudo="ok", input_tokens=1000, output_tokens=500),
    })
    router, _ = _router(guard, executor, routes=(_rota("openai", 200), _rota("gemini", 100)))
    router.executar(_solicitacao())
    saldo = ledger.saldo(budget_id="budget-1", tenant_id="tenant-a", unidade_id="unit-a")
    assert executor.calls == ["openai", "gemini"]
    assert saldo.reservado == Decimal("1")
    assert saldo.consumido == Decimal("0.007")


def test_bloqueio_fallback_nao_executa_nova_rota_sem_saldo(setup_guard):
    ledger, guard = setup_guard
    ledger.sincronizar_politica(
        budget_id="budget-1", tenant_id="tenant-a", unidade_id="unit-a",
        capability="tool_planning", ciclo_id="2026-10", moeda="USD",
        limite=Decimal("1.5"), revisao_politica=2,
        vigencia_inicio=NOW - timedelta(days=1), vigencia_fim=NOW + timedelta(days=30),
    )
    executor = ExecutorFixture({
        "openai": FalhaRotaTransitoria("timeout"),
        "gemini": RespostaModeloIA(conteudo="nunca", input_tokens=1000, output_tokens=500),
    })
    router, _ = _router(guard, executor, routes=(_rota("openai", 200), _rota("gemini", 100)))
    with pytest.raises(FranquiaEsgotadaIA):
        router.executar(_solicitacao())
    assert executor.calls == ["openai"]


def test_sem_guard_obrigatorio_nega_antes_de_modelo():
    executor = ExecutorFixture({"openai": RespostaModeloIA(conteudo="nao")})
    router, _ = _router(None, executor)
    with pytest.raises(ErroAIRouter, match="orcamento_guard_obrigatorio"):
        router.executar(_solicitacao())
    assert executor.calls == []


def test_politica_de_outro_tenant_nega_antes_de_modelo(setup_guard):
    _, guard = setup_guard
    executor = ExecutorFixture({"openai": RespostaModeloIA(conteudo="nao")})
    router, _ = _router(guard, executor)
    with pytest.raises(OrcamentoIndisponivelIA):
        router.executar(_solicitacao(tenant_id="tenant-b"))
    assert executor.calls == []
