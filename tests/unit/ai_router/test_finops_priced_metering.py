"""Contrato interno: custo versionado acompanha AIUsageEvent sem chamada extra."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.ai_pricing import CatalogoPrecosIAEmMemoria, PriceSnapshotIA, TarifaIA
from core.ai_router import (
    AIModelRouter,
    CapabilityIA,
    FalhaRotaTransitoria,
    MedidorUsoIAEmMemoria,
    RespostaModeloIA,
    RotaIA,
    SolicitacaoIA,
)

AGORA = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)


class ExecutorFixture:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def executar(
        self, *, rota: RotaIA, solicitacao: SolicitacaoIA
    ) -> RespostaModeloIA:
        self.calls.append(rota.provider)
        result = self.outcomes[rota.provider]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, RespostaModeloIA)
        return result


def _snapshot(
    provider: str = "openai",
    *,
    expiration: datetime | None = None,
    model: str | None = None,
) -> PriceSnapshotIA:
    return PriceSnapshotIA(
        price_snapshot_id="cost-" + provider,
        provider=provider,
        model=model or "model-" + provider,
        modalidade="text_tokens",
        moeda="USD",
        versao=1,
        vigencia_inicio=AGORA - timedelta(days=1),
        vigencia_fim=expiration,
        tarifas=(
            TarifaIA(
                componente="input_tokens",
                preco=Decimal("2"),
                unidades_por_preco=1_000_000,
            ),
            TarifaIA(
                componente="output_tokens",
                preco=Decimal("10"),
                unidades_por_preco=1_000_000,
            ),
        ),
    )


def _route(provider: str, priority: int = 100) -> RotaIA:
    return RotaIA(
        configuracao_id="cfg-" + provider,
        provider=provider,
        model="model-" + provider,
        capability=CapabilityIA.TOOL_PLANNING,
        prioridade=priority,
        price_snapshot_id="cost-" + provider,
    )


def _request() -> SolicitacaoIA:
    return SolicitacaoIA(
        tenant_id="tenant-a",
        unidade_id="unit-a",
        request_id="request-1",
        correlation_id="correlation-1",
        capability=CapabilityIA.TOOL_PLANNING,
        conteudo="teste sem segredos",
    )


def _router(
    *,
    executor: ExecutorFixture,
    meter: MedidorUsoIAEmMemoria,
    routes: tuple[RotaIA, ...],
    snapshots: tuple[PriceSnapshotIA, ...] | None,
) -> AIModelRouter:
    catalog = (
        CatalogoPrecosIAEmMemoria(snapshots)
        if snapshots is not None
        else None
    )
    return AIModelRouter(
        rotas=routes,
        executor=executor,
        metering=meter,
        pricing_catalog=catalog,
        now=lambda: AGORA,
    )


def test_custo_estimado_segue_evento_duravel_com_modelo_e_snapshot() -> None:
    meter = MedidorUsoIAEmMemoria()
    router = _router(
        executor=ExecutorFixture(
            {
                "openai": RespostaModeloIA(
                    conteudo="ok",
                    input_tokens=1_000,
                    output_tokens=500,
                    cached_tokens=0,
                )
            }
        ),
        meter=meter,
        routes=(_route("openai"),),
        snapshots=(_snapshot(),),
    )

    assert router.executar(_request()).conteudo == "ok"
    assert len(meter.eventos) == 1
    evento = meter.eventos[0]
    assert evento.custo_real_calculado == Decimal("0.007")
    assert evento.moeda == "USD"
    assert evento.price_snapshot_id == "cost-openai"
    assert evento.tenant_id == "tenant-a"
    assert evento.unidade_id == "unit-a"


def test_catalogo_ausente_ou_snapshot_desconhecido_nao_vira_custo_zero() -> None:
    for snapshots in (None, ()):
        meter = MedidorUsoIAEmMemoria()
        router = _router(
            executor=ExecutorFixture(
                {
                    "openai": RespostaModeloIA(
                        conteudo="ok", input_tokens=1_000, output_tokens=500
                    )
                }
            ),
            meter=meter,
            routes=(_route("openai"),),
            snapshots=snapshots,
        )
        router.executar(_request())
        assert meter.eventos[0].custo_real_calculado is None
        assert meter.eventos[0].moeda is None


def test_snapshot_de_outro_modelo_nao_gera_custo_falso() -> None:
    meter = MedidorUsoIAEmMemoria()
    router = _router(
        executor=ExecutorFixture(
            {
                "openai": RespostaModeloIA(
                    conteudo="ok", input_tokens=1_000, output_tokens=500
                )
            }
        ),
        meter=meter,
        routes=(_route("openai"),),
        snapshots=(_snapshot(model="outro-modelo"),),
    )
    router.executar(_request())
    assert meter.eventos[0].custo_real_calculado is None


def test_snapshot_vencido_nao_gera_custo_falso() -> None:
    meter = MedidorUsoIAEmMemoria()
    router = _router(
        executor=ExecutorFixture(
            {
                "openai": RespostaModeloIA(
                    conteudo="ok", input_tokens=1_000, output_tokens=500
                )
            }
        ),
        meter=meter,
        routes=(_route("openai"),),
        snapshots=(_snapshot(expiration=AGORA),),
    )
    router.executar(_request())
    assert meter.eventos[0].custo_real_calculado is None


def test_usage_incompleto_fica_desconhecido() -> None:
    meter = MedidorUsoIAEmMemoria()
    router = _router(
        executor=ExecutorFixture(
            {
                "openai": RespostaModeloIA(
                    conteudo="ok", input_tokens=1_000, output_tokens=None
                )
            }
        ),
        meter=meter,
        routes=(_route("openai"),),
        snapshots=(_snapshot(),),
    )
    router.executar(_request())
    assert meter.eventos[0].custo_real_calculado is None


def test_fallback_so_precifica_rota_que_respondeu() -> None:
    meter = MedidorUsoIAEmMemoria()
    executor = ExecutorFixture(
        {
            "openai": FalhaRotaTransitoria("provider_timeout"),
            "gemini": RespostaModeloIA(
                conteudo="ok", input_tokens=1_000, output_tokens=500
            ),
        }
    )
    router = _router(
        executor=executor,
        meter=meter,
        routes=(_route("openai", 200), _route("gemini", 100)),
        snapshots=(_snapshot("openai"), _snapshot("gemini")),
    )
    response = router.executar(_request())
    assert response.provider == "gemini"
    assert executor.calls == ["openai", "gemini"]
    assert meter.eventos[0].custo_real_calculado is None
    assert meter.eventos[1].custo_real_calculado == Decimal("0.007")
    assert meter.eventos[1].moeda == "USD"
    assert meter.eventos[1].fallback_used is True
