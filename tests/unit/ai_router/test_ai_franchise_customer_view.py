"""FinOps do cliente não revela custo interno e respeita escopo da sessão."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.ai_franchise_customer_view import consultar_franquias_ia
from infra.ai_budget_sqlalchemy import (
    AIBudgetBase,
    LedgerFranquiasIASQLAlchemy,
)

AGORA = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'franquia-view.db'}")
    AIBudgetBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    ledger = LedgerFranquiasIASQLAlchemy(factory)
    ledger.sincronizar_politica(
        budget_id="bud-a", tenant_id="tenant-a", unidade_id="unit-a",
        capability="tool_planning", ciclo_id="out-2026",
        moeda="USD", limite=Decimal("100"), revisao_politica=1,
        vigencia_inicio=AGORA - timedelta(days=1),
        vigencia_fim=AGORA + timedelta(days=28),
    )
    return factory, ledger


def _reserve(ledger, index: int, amount: str) -> None:
    ledger.reservar(
        reserva_id=f"res-{index}", budget_id="bud-a",
        tenant_id="tenant-a", unidade_id="unit-a",
        capability="tool_planning", ciclo_id="out-2026",
        request_id=f"request-{index}", attempt_key="0",
        provider="openai", model="model-test",
        valor=Decimal(amount), agora=AGORA,
    )


def test_cliente_so_enxerga_seu_proprio_tenant_e_unidade(tmp_path) -> None:
    factory, ledger = _factory(tmp_path)
    _reserve(ledger, 1, "75")
    correto = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a", agora=AGORA
    )
    assert correto["status"] == "warning"
    assert correto["percentual_utilizado"] == "75.0"
    assert correto["franquias"][0]["em_processamento"] is True
    for tenant, unidade in (("tenant-b", "unit-a"), ("tenant-a", "unit-b")):
        outro = consultar_franquias_ia(
            factory, tenant_id=tenant, unidade_id=unidade, agora=AGORA,
        )
        assert outro["status"] == "not_configured"
        assert outro["franquias"] == []


def test_alertas_70_90_100_e_reservas_em_andamento(tmp_path) -> None:
    factory, ledger = _factory(tmp_path)
    normal = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a", agora=AGORA
    )
    assert normal["status"] == "normal"
    _reserve(ledger, 1, "70")
    aviso = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a", agora=AGORA
    )
    assert aviso["status"] == "warning"
    _reserve(ledger, 2, "20")
    critico = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a", agora=AGORA
    )
    assert critico["status"] == "critical"
    _reserve(ledger, 3, "10")
    esgotado = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a", agora=AGORA
    )
    assert esgotado["status"] == "blocked"
    assert esgotado["percentual_utilizado"] == "100.0"


def test_custos_internos_nao_sao_expostos_nem_viram_creditos(tmp_path) -> None:
    factory, ledger = _factory(tmp_path)
    _reserve(ledger, 1, "37")
    response = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a", agora=AGORA
    )
    texto = str(response).casefold()
    for dado_privado in ("usd", "limite", "custo_real", "valor_reservado", "budget_id"):
        assert dado_privado not in texto
    assert "percentual_utilizado" in response
    assert "creditos" not in response


def test_periodo_expirado_nao_herda_franquia_antiga(tmp_path) -> None:
    factory, _ = _factory(tmp_path)
    result = consultar_franquias_ia(
        factory, tenant_id="tenant-a", unidade_id="unit-a",
        agora=AGORA + timedelta(days=29),
    )
    assert result["status"] == "not_configured"
    assert result["percentual_utilizado"] is None
