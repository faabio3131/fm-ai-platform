"""AI Model Router canônico e provider-neutral do Kordena V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol

from core.ai_cost import CalculadoraCustoIA
from core.ai_pricing import CatalogoPrecosIA, ErroPricingCatalog


class CapabilityIA(StrEnum):
    TOOL_PLANNING = "tool_planning"
    ATENDIMENTO_INTERPRETACAO = "atendimento_interpretacao"
    ATENDIMENTO_TRANSCRICAO = "atendimento_transcricao"
    ESTOQUE_LEITURA_DOCUMENTAL = "estoque_leitura_documental"
    ATENDIMENTO_DIAGNOSTICO_GEMINI = "atendimento_diagnostico_gemini"


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
class ConteudoAudioIA:
    """Conteúdo multimodal provider-neutral sem expor bytes em repr/telemetria."""

    audio: bytes = field(repr=False)
    mime_type: str
    instrucao: str

    def __post_init__(self) -> None:
        if not isinstance(self.audio, bytes) or not self.audio:
            raise ValueError("audio_obrigatorio")
        mime = self.mime_type.strip().casefold()
        if not mime.startswith("audio/"):
            raise ValueError("mime_type_audio_invalido")
        instrucao = self.instrucao.strip()
        if not instrucao:
            raise ValueError("instrucao_audio_obrigatoria")
        object.__setattr__(self, "mime_type", mime)
        object.__setattr__(self, "instrucao", instrucao)


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


@dataclass(frozen=True, kw_only=True)
class ReservaAutorizadaIA:
    reserva_id: str
    tenant_id: str
    unidade_id: str
    moeda: str


class GuardaConsumoIA(Protocol):
    """Autoriza uso financeiro localmente, sem Command no caminho de cada consulta."""

    def reservar(
        self, *, solicitacao: SolicitacaoIA, rota: RotaIA, tentativa: int
    ) -> ReservaAutorizadaIA: ...

    def reconciliar(
        self, *, reserva: ReservaAutorizadaIA, evento: AIUsageEvent | None
    ) -> None: ...


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
        pricing_catalog: CatalogoPrecosIA | None = None,
        cost_calculator: CalculadoraCustoIA | None = None,
        budget_guard: GuardaConsumoIA | None = None,
        require_budget_guard: bool = False,
        monotonic: Callable[[], float] = perf_counter,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._rotas = tuple(rotas)
        self._executor = executor
        self._metering = metering
        self._pricing_catalog = pricing_catalog
        self._cost_calculator = cost_calculator or CalculadoraCustoIA()
        self._budget_guard = budget_guard
        self._require_budget_guard = require_budget_guard
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

    def _custo_precificado(
        self,
        *,
        rota: RotaIA,
        resposta: RespostaModeloIA | None,
        instante: datetime,
    ) -> tuple[Decimal | None, str | None]:
        """Estima custo a partir de tarifa versionada, sem fazer chamada externa.

        Ausência, divergência ou expiração de preços não vira custo zero.
        O evento continua registrável e o custo permanece desconhecido.
        """
        if resposta is None or self._pricing_catalog is None:
            return None, None

        try:
            snapshot = self._pricing_catalog.obter_snapshot(
                price_snapshot_id=rota.price_snapshot_id
            )
            if (
                snapshot.provider != rota.provider.casefold()
                or snapshot.model != rota.model
                or not snapshot.vigente_em(instante)
            ):
                return None, None
            custo = self._cost_calculator.estimar_tokens(
                snapshot=snapshot,
                input_tokens=resposta.input_tokens,
                output_tokens=resposta.output_tokens,
                cached_tokens=resposta.cached_tokens,
            )
        except (ErroPricingCatalog, ValueError):
            return None, None

        if custo.valor is None:
            return None, None
        return custo.valor, custo.moeda

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
    ) -> AIUsageEvent:
        latency_ms = max(
            0,
            round((self._monotonic() - inicio) * 1000),
        )
        instante = self._now()
        custo, moeda = self._custo_precificado(
            rota=rota,
            resposta=resposta if outcome is OutcomeIA.SUCESSO else None,
            instante=instante,
        )

        evento = AIUsageEvent(
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
                custo_real_calculado=custo,
                moeda=moeda,
                price_snapshot_id=rota.price_snapshot_id,
                timestamp=instante,
        )
        self._metering.registrar(evento)
        return evento

    def _registrar_e_reconciliar(
        self, *, reserva: ReservaAutorizadaIA | None, **kwargs: Any
    ) -> None:
        try:
            evento = self._registrar(**kwargs)
        except Exception:
            # A chamada externa pode ja ter sido faturada; nao liberar a reserva.
            if self._budget_guard is not None and reserva is not None:
                self._budget_guard.reconciliar(reserva=reserva, evento=None)
            raise
        if self._budget_guard is not None and reserva is not None:
            self._budget_guard.reconciliar(reserva=reserva, evento=evento)

    def executar(self, solicitacao: SolicitacaoIA) -> ResultadoRoteamentoIA:
        if self._require_budget_guard and self._budget_guard is None:
            raise ErroAIRouter("ai_router.orcamento_guard_obrigatorio")
        candidatas = self._candidatas(solicitacao.capability)
        fallback_reason: str | None = None

        for indice, rota in enumerate(candidatas):
            fallback_used = indice > 0
            route_reason = (
                f"capability={solicitacao.capability.value};"
                f"priority={rota.prioridade}"
            )
            reserva = (
                self._budget_guard.reservar(
                    solicitacao=solicitacao, rota=rota, tentativa=indice,
                )
                if self._budget_guard is not None
                else None
            )
            inicio = self._monotonic()

            try:
                resposta = self._executor.executar(
                    rota=rota,
                    solicitacao=solicitacao,
                )

            except FalhaRotaTransitoria as exc:
                self._registrar_e_reconciliar(
                    reserva=reserva,
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
                self._registrar_e_reconciliar(
                    reserva=reserva,
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
                self._registrar_e_reconciliar(
                    reserva=reserva,
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

            self._registrar_e_reconciliar(
                    reserva=reserva,
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
