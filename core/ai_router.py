"""AI Model Router canônico e provider-neutral do Kordena V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol


class CapabilityIA(StrEnum):
    TOOL_PLANNING = "tool_planning"


class OutcomeIA(StrEnum):
    SUCESSO = "success"
    FALHA_TRANSITORIA = "transient_failure"
    FALHA_DEFINITIVA = "definitive_failure"


class ErroAIRouter(RuntimeError):
    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


class SemRotaCompativel(ErroAIRouter):
    pass


class PoliticaRoteamentoAmbigua(ErroAIRouter):
    pass


class FalhaRotaTransitoria(ErroAIRouter):
    pass


class FalhaRotaDefinitiva(ErroAIRouter):
    pass


@dataclass(frozen=True, kw_only=True)
class SolicitacaoIA:
    tenant_id: str
    unidade_id: str
    request_id: str
    correlation_id: str
    capability: CapabilityIA
    conteudo: Any

    def __post_init__(self) -> None:
        for nome in (
            "tenant_id",
            "unidade_id",
            "request_id",
            "correlation_id",
        ):
            valor = getattr(self, nome)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(f"{nome}_obrigatorio")


@dataclass(frozen=True, kw_only=True)
class RotaIA:
    configuracao_id: str
    provider: str
    model: str
    capability: CapabilityIA
    prioridade: int
    price_snapshot_id: str

    def __post_init__(self) -> None:
        for nome in (
            "configuracao_id",
            "provider",
            "model",
            "price_snapshot_id",
        ):
            valor = getattr(self, nome)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(f"{nome}_obrigatorio")

        if not 0 <= self.prioridade <= 10_000:
            raise ValueError("prioridade_invalida")


@dataclass(frozen=True, kw_only=True)
class RespostaModeloIA:
    conteudo: Any
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass(frozen=True, kw_only=True)
class AIUsageEvent:
    tenant_id: str
    unidade_id: str
    request_id: str
    correlation_id: str
    capability: CapabilityIA
    provider: str
    model: str
    route_reason: str
    fallback_used: bool
    fallback_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    latency_ms: int
    outcome: OutcomeIA
    custo_real_calculado: Decimal | None
    moeda: str | None
    price_snapshot_id: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.latency_ms < 0:
            raise ValueError("latency_ms_invalida")

        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp_sem_timezone")

        object.__setattr__(
            self,
            "timestamp",
            self.timestamp.astimezone(timezone.utc),
        )


@dataclass(frozen=True, kw_only=True)
class ResultadoRoteamentoIA:
    conteudo: Any
    provider: str
    model: str
    capability: CapabilityIA
    route_reason: str
    fallback_used: bool
    fallback_reason: str | None
    price_snapshot_id: str


class ExecutorModeloIA(Protocol):
    def executar(
        self,
        *,
        rota: RotaIA,
        solicitacao: SolicitacaoIA,
    ) -> RespostaModeloIA: ...


class MedidorUsoIA(Protocol):
    def registrar(self, evento: AIUsageEvent) -> None: ...


class MedidorUsoIAEmMemoria:
    def __init__(self) -> None:
        self.eventos: list[AIUsageEvent] = []

    def registrar(self, evento: AIUsageEvent) -> None:
        self.eventos.append(evento)


class AIModelRouter:
    """Seleciona rota por capability/prioridade e aplica fallback governado."""

    def __init__(
        self,
        *,
        rotas: tuple[RotaIA, ...],
        executor: ExecutorModeloIA,
        metering: MedidorUsoIA,
        monotonic: Callable[[], float] = perf_counter,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._rotas = tuple(rotas)
        self._executor = executor
        self._metering = metering
        self._monotonic = monotonic
        self._now = now

    def _candidatas(self, capability: CapabilityIA) -> tuple[RotaIA, ...]:
        candidatas = sorted(
            (
                rota
                for rota in self._rotas
                if rota.capability is capability
            ),
            key=lambda rota: (
                -rota.prioridade,
                rota.provider,
                rota.model,
                rota.configuracao_id,
            ),
        )

        if not candidatas:
            raise SemRotaCompativel("ai_router.sem_rota_compativel")

        prioridades = [rota.prioridade for rota in candidatas]

        if len(prioridades) != len(set(prioridades)):
            raise PoliticaRoteamentoAmbigua(
                "ai_router.politica_ambigua_mesma_prioridade"
            )

        return tuple(candidatas)

    def _registrar(
        self,
        *,
        solicitacao: SolicitacaoIA,
        rota: RotaIA,
        route_reason: str,
        fallback_used: bool,
        fallback_reason: str | None,
        inicio: float,
        outcome: OutcomeIA,
        resposta: RespostaModeloIA | None = None,
    ) -> None:
        latency_ms = max(
            0,
            round((self._monotonic() - inicio) * 1000),
        )

        self._metering.registrar(
            AIUsageEvent(
                tenant_id=solicitacao.tenant_id,
                unidade_id=solicitacao.unidade_id,
                request_id=solicitacao.request_id,
                correlation_id=solicitacao.correlation_id,
                capability=solicitacao.capability,
                provider=rota.provider,
                model=rota.model,
                route_reason=route_reason,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                input_tokens=(
                    resposta.input_tokens if resposta is not None else None
                ),
                output_tokens=(
                    resposta.output_tokens if resposta is not None else None
                ),
                cached_tokens=(
                    resposta.cached_tokens if resposta is not None else None
                ),
                latency_ms=latency_ms,
                outcome=outcome,
                custo_real_calculado=None,
                moeda=None,
                price_snapshot_id=rota.price_snapshot_id,
                timestamp=self._now(),
            )
        )

    def executar(self, solicitacao: SolicitacaoIA) -> ResultadoRoteamentoIA:
        candidatas = self._candidatas(solicitacao.capability)
        fallback_reason: str | None = None

        for indice, rota in enumerate(candidatas):
            fallback_used = indice > 0
            route_reason = (
                f"capability={solicitacao.capability.value};"
                f"priority={rota.prioridade}"
            )
            inicio = self._monotonic()

            try:
                resposta = self._executor.executar(
                    rota=rota,
                    solicitacao=solicitacao,
                )

            except FalhaRotaTransitoria as exc:
                self._registrar(
                    solicitacao=solicitacao,
                    rota=rota,
                    route_reason=route_reason,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason,
                    inicio=inicio,
                    outcome=OutcomeIA.FALHA_TRANSITORIA,
                )

                fallback_reason = exc.codigo

                if indice == len(candidatas) - 1:
                    raise

                continue

            except FalhaRotaDefinitiva:
                self._registrar(
                    solicitacao=solicitacao,
                    rota=rota,
                    route_reason=route_reason,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason,
                    inicio=inicio,
                    outcome=OutcomeIA.FALHA_DEFINITIVA,
                )
                raise

            except Exception as exc:
                self._registrar(
                    solicitacao=solicitacao,
                    rota=rota,
                    route_reason=route_reason,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason,
                    inicio=inicio,
                    outcome=OutcomeIA.FALHA_DEFINITIVA,
                )

                raise FalhaRotaDefinitiva(
                    "ai_router.executor_unclassified_failure"
                ) from exc

            self._registrar(
                solicitacao=solicitacao,
                rota=rota,
                route_reason=route_reason,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                inicio=inicio,
                outcome=OutcomeIA.SUCESSO,
                resposta=resposta,
            )

            return ResultadoRoteamentoIA(
                conteudo=resposta.conteudo,
                provider=rota.provider,
                model=rota.model,
                capability=solicitacao.capability,
                route_reason=route_reason,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                price_snapshot_id=rota.price_snapshot_id,
            )

        raise AssertionError("roteamento terminou sem resultado")
