from types import SimpleNamespace

import pytest

from application.fmcc_core_service import (
    ErroCoreCompartilhadoFMCC,
    ServicoCoreCompartilhadoFMCC,
)
from core.ai_router import CapabilityIA


class FakeRouter:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def executar(self, solicitacao):
        self.requests.append(solicitacao)
        return SimpleNamespace(conteudo=self.responses.pop(0))


def test_plan_uses_canonical_router_and_external_tenant_scope():
    router = FakeRouter(
        ['{"capability":"metric.query","arguments":{"metricId":"revenue.mrr"}}']
    )
    service = ServicoCoreCompartilhadoFMCC(router)

    result = service.planejar(
        pergunta="Qual o MRR?",
        tenant_id="fmcc-tenant-a",
        usuario_id="user-a",
        correlation_id="corr-a",
        capabilities_permitidas=("metric.query",),
    )

    assert result == {
        "capability": "metric.query",
        "arguments": {"metricId": "revenue.mrr"},
    }
    request = router.requests[0]
    assert request.tenant_id == "fmcc-tenant-a"
    assert request.unidade_id == "fm-control-center"
    assert request.capability is CapabilityIA.FMCC_PLANNING
    assert request.conteudo["allowed_capabilities"] == ("metric.query",)


def test_plan_rejects_capability_outside_allowlist():
    router = FakeRouter(
        ['{"capability":"dangerous.execute","arguments":{}}']
    )
    service = ServicoCoreCompartilhadoFMCC(router)

    with pytest.raises(
        ErroCoreCompartilhadoFMCC,
        match="fmcc_core.capability_nao_permitida",
    ):
        service.planejar(
            pergunta="Execute algo",
            tenant_id="fmcc-tenant-a",
            usuario_id="user-a",
            correlation_id="corr-a",
            capabilities_permitidas=("metric.query",),
        )


def test_plan_rejects_scope_arguments_from_model():
    router = FakeRouter(
        [
            (
                '{"capability":"metric.query",'
                '"arguments":{"metricId":"trial.starts.count","tenantId":"other"}}'
            )
        ]
    )
    service = ServicoCoreCompartilhadoFMCC(router)

    with pytest.raises(
        ErroCoreCompartilhadoFMCC,
        match="fmcc_core.arguments_de_escopo_proibidos",
    ):
        service.planejar(
            pergunta="Trials?",
            tenant_id="fmcc-tenant-a",
            usuario_id="user-a",
            correlation_id="corr-a",
            capabilities_permitidas=("metric.query",),
        )


def test_synthesis_keeps_evidence_authoritative_and_model_only_writes_answer():
    router = FakeRouter([{"answer": "O valor governado é R$ 10,00."}])
    service = ServicoCoreCompartilhadoFMCC(router)
    evidence = (
        {
            "kind": "metric",
            "ref": "billing.gross_billed",
            "sourceAuthority": "billing",
        },
    )

    result = service.sintetizar(
        pergunta="Quanto faturamos?",
        tenant_id="fmcc-tenant-a",
        usuario_id="user-a",
        correlation_id="corr-a",
        fatos=(
            {
                "metricId": "billing.gross_billed",
                "value": "10.00",
                "unit": "currency",
                "currency": "BRL",
            },
        ),
        evidencias=evidence,
    )

    assert result["answer"] == "O valor governado é R$ 10,00."
    assert result["evidence"] == list(evidence)
    assert result["factualStatus"] == "grounded"
    assert router.requests[0].capability is CapabilityIA.FMCC_SYNTHESIS


def test_synthesis_requires_governed_evidence():
    service = ServicoCoreCompartilhadoFMCC(FakeRouter(["unused"]))

    with pytest.raises(
        ErroCoreCompartilhadoFMCC,
        match="fmcc_core.evidencia_obrigatoria",
    ):
        service.sintetizar(
            pergunta="Quanto?",
            tenant_id="fmcc-tenant-a",
            usuario_id="user-a",
            correlation_id="corr-a",
            fatos=(),
            evidencias=(),
        )


def test_plan_receives_operational_context_without_promoting_it_to_authority():
    router = FakeRouter(
        ['{"capability":"metric.query","arguments":{"metricId":"revenue.mrr"}}']
    )
    service = ServicoCoreCompartilhadoFMCC(router)
    context = (
        {
            "question": "Quanto faturamos ontem?",
            "answer": "R$ 100,00",
            "evidenceRefs": ["billing.gross_billed"],
        },
    )

    service.planejar(
        pergunta="E hoje?",
        tenant_id="fmcc-tenant-a",
        usuario_id="user-a",
        correlation_id="corr-a",
        capabilities_permitidas=("metric.query", "metrics.query_many"),
        contexto_operacional=context,
    )

    request = router.requests[0]
    assert request.conteudo["operational_context"] == list(context)


def test_synthesis_supports_explanation_anomaly_risk_and_recommendation_only_from_facts():
    router = FakeRouter(
        [
            {
                "answer": (
                    "A queda está concentrada na métrica governada enviada; "
                    "vale investigar a origem indicada pela evidência."
                )
            }
        ]
    )
    service = ServicoCoreCompartilhadoFMCC(router)
    facts = (
        {"metricId": "revenue.mrr", "value": "1000", "unit": "currency"},
        {"metricId": "churn.rate", "value": "8", "unit": "percent"},
    )
    evidence = (
        {"kind": "metric", "ref": "revenue.mrr", "sourceAuthority": "billing"},
        {"kind": "metric", "ref": "churn.rate", "sourceAuthority": "billing"},
    )

    result = service.sintetizar(
        pergunta="Há algum risco e o que recomenda?",
        tenant_id="fmcc-tenant-a",
        usuario_id="user-a",
        correlation_id="corr-a",
        fatos=facts,
        evidencias=evidence,
        contexto_operacional=(
            {"question": "Como estava ontem?", "factualStatus": "grounded"},
        ),
    )

    assert result["factualStatus"] == "grounded"
    assert result["evidence"] == list(evidence)
    request = router.requests[0]
    assert request.conteudo["facts"] == list(facts)
    assert request.conteudo["operational_context"][0]["factualStatus"] == "grounded"
