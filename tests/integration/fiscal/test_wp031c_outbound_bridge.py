from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from application.fiscal_outbound import (
    FiscalOutboundBridgeError,
    KordenaFiscalOutboundBridge,
)
from core.dominio.dinheiro import Dinheiro
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.pagamentos import (
    CodigoCriterioFinanceiro,
    CriterioFinanceiro,
    MetodoPagamento,
    RepositorioPagamentosEmMemoria,
    reconhecer_venda,
)
from core.seguranca import ContextoExecucao, Permissao
from core.seguranca.permissoes import Papel
from kordena_fiscal.contingency import InMemoryFiscalOutboxStore
from kordena_fiscal.documents import FiscalLineSnapshot
from kordena_fiscal.domain import (
    BrazilianJurisdiction,
    CnaeCode,
    Cnpj,
    ExecutionScope,
    FiscalAddress,
    FiscalEnvironment,
    FiscalProductProfile,
    FiscalProfile,
    FiscalUnitCode,
    Money,
    NcmCode,
    ProductOrigin,
    StateRegistration,
    TaxRegimeCode,
)
from kordena_fiscal.tax import TaxDecision, TaxRuleOutcome
from tests.unit.orders.factories import pedido

AGORA = datetime(2026, 9, 18, 18, 0, tzinfo=timezone.utc)


class _IssuerResolver:
    def resolve(
        self,
        *,
        scope: ExecutionScope,
        issued_at: datetime,
    ) -> FiscalProfile:
        return FiscalProfile(
            profile_id="issuer-a",
            scope=scope,
            cnpj=Cnpj("11222333000181"),
            legal_name="Kordena Teste Ltda",
            tax_regime=TaxRegimeCode.SIMPLES_NACIONAL,
            state_registration=StateRegistration(
                state_code="SP",
                number="110042490114",
            ),
            primary_cnae=CnaeCode("5611201"),
            address=FiscalAddress(
                street="Rua Teste",
                number="100",
                district="Centro",
                municipality_name="Sao Paulo",
                jurisdiction=BrazilianJurisdiction("SP", "3550308"),
                postal_code="01001000",
            ),
            effective_from=issued_at - timedelta(days=1),
        )


class _LineResolver:
    def resolve(
        self,
        *,
        scope: ExecutionScope,
        pedido,
        issued_at: datetime,
    ) -> tuple[FiscalLineSnapshot, ...]:
        product = FiscalProductProfile(
            profile_id="product-a",
            product_id="produto-que-pode-mudar",
            scope=scope,
            commercial_code="P1",
            description="X-Burger snapshot",
            ncm=NcmCode("21069090"),
            commercial_unit=FiscalUnitCode("UN"),
            taxable_unit=FiscalUnitCode("UN"),
            origin=ProductOrigin.NATIONAL,
            effective_from=issued_at - timedelta(days=1),
        )
        decision = TaxDecision(
            rule_id="rule-a",
            rule_version=1,
            source_normative="fixture deterministica",
            outcome=TaxRuleOutcome(
                cfop="5102",
                icms_code="102",
                pis_cst="01",
                cofins_cst="01",
            ),
            rank=(1, 8, 1),
        )
        return (
            FiscalLineSnapshot(
                line_number=1,
                product=product,
                quantity=Decimal("1"),
                unit_price=Money(pedido.total.valor),
                gross_amount=Money(pedido.total.valor),
                tax_decision=decision,
            ),
        )


def _event(
    *,
    tenant: str = "tenant-a",
    unidade: str = "unidade-a",
    valor: str = "24.00",
) -> EnvelopeMensagem:
    return EnvelopeMensagem(
        event_id=EventoId("evt-sale-1"),
        event_type="venda.criada",
        aggregate_id="sale-1",
        aggregate_type="venda",
        tenant_id=TenantId(tenant),
        unidade_id=UnidadeId(unidade),
        correlation_id=CorrelationId("corr-fiscal"),
        causation_id=None,
        idempotency_key=IdempotencyKey("sale-idem-1"),
        occurred_at=AGORA,
        payload={
            "pedido_id": "pedido-1",
            "pagamento_id": "pay-1",
            "valor": valor,
            "moeda": "BRL",
            "metodo": "pix",
            "criterio": "PAGAMENTO_CONFIRMADO",
            "criterio_versao": 2,
            "aggregate_version": 1,
        },
        version=1,
    )


def _bridge(store: InMemoryFiscalOutboxStore) -> KordenaFiscalOutboundBridge:
    return KordenaFiscalOutboundBridge(
        outbox_store=store,
        issuer_resolver=_IssuerResolver(),
        line_resolver=_LineResolver(),
        environment=FiscalEnvironment.HOMOLOGATION,
    )


def test_wp031c_venda_criada_gera_uma_intencao_fiscal_idempotente() -> None:
    store = InMemoryFiscalOutboxStore()
    bridge = _bridge(store)
    canonical_order = pedido()

    first = bridge.process(event=_event(), pedido=canonical_order)
    replay = bridge.process(event=_event(), pedido=canonical_order)

    assert first.sale_id == "sale-1"
    assert first.pedido_id == "pedido-1"
    assert first.document.source.source_type == "venda"
    assert first.document.source.source_id == "sale-1"
    assert first.document.scope.tenant_id == "tenant-a"
    assert first.document.scope.unit_id == "unidade-a"
    assert first.document.totals.net_amount.amount == Decimal("24.00")
    assert first.document.totals.payment_amount.amount == Decimal("24.00")
    assert first.outbox.entry.operation == "nfce.issue"
    assert first.outbox.entry.deduplication_key == "venda:sale-1:nfce:v1"
    assert not first.outbox.replay
    assert replay.outbox.replay
    assert replay.outbox.entry.entry_id == first.outbox.entry.entry_id

    payload = json.loads(first.outbox.entry.payload)
    assert payload["source"] == {"source_type": "venda", "source_id": "sale-1"}
    assert payload["scope"]["environment"] == "homologation"
    assert payload["payments"][0]["method"] == "pix"
    assert payload["totals"]["net_amount"]["amount"] == "24"


def test_wp031c_divergencia_financeira_falha_fechado() -> None:
    with pytest.raises(
        FiscalOutboundBridgeError,
        match="valor does not match canonical pedido total",
    ):
        _bridge(InMemoryFiscalOutboxStore()).process(
            event=_event(valor="25.00"),
            pedido=pedido(),
        )


def test_wp031c_cross_tenant_falha_fechado() -> None:
    with pytest.raises(
        FiscalOutboundBridgeError,
        match="share tenant/unidade",
    ):
        _bridge(InMemoryFiscalOutboxStore()).process(
            event=_event(tenant="tenant-b"),
            pedido=pedido(),
        )


def test_wp031c_venda_criada_publica_contrato_fiscal_minimo() -> None:
    contexto = ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="unidade-a",
        usuario_id="user-1",
        papeis=frozenset({Papel.GERENTE}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-fiscal",
        timestamp=AGORA,
        origem="wp031c-test",
        unidades_permitidas=frozenset({"unidade-a"}),
    )
    criterio = CriterioFinanceiro(
        elegivel=True,
        codigo=CodigoCriterioFinanceiro.PAGAMENTO_CONFIRMADO,
        motivo="pagamento confirmado",
        pedido_id="pedido-1",
        valor_reconhecivel=Dinheiro("24.00"),
        policy="financeiro_v1",
        versao=2,
        ator="user-1",
        timestamp=AGORA,
        correlation_id="corr-fiscal",
        pagamento_id="pay-1",
    )
    resultado = reconhecer_venda(
        contexto=contexto,
        repositorio=RepositorioPagamentosEmMemoria(),
        criterio=criterio,
        metodo=MetodoPagamento.PIX,
        idempotency_key="sale-idem-1",
        timestamp=AGORA,
    )

    assert resultado.evento.event_type == "venda.criada"
    assert resultado.evento.payload["pedido_id"] == "pedido-1"
    assert resultado.evento.payload["pagamento_id"] == "pay-1"
    assert resultado.evento.payload["valor"] == "24.00"
    assert resultado.evento.payload["moeda"] == "BRL"
    assert resultado.evento.payload["metodo"] == "pix"
    assert resultado.evento.payload["criterio_versao"] == 2
