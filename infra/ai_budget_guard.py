"""Adaptador local de preautorizacao de IA para o router provider-neutral.

O resolver de politicas deve ler somente a projecao comercial autenticada do
Kordena; chamadas ao Command nao podem ocorrer em cada pergunta.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from core.ai_router import (
    AIUsageEvent,
    GuardaConsumoIA,
    OutcomeIA,
    ReservaAutorizadaIA,
    RotaIA,
    SolicitacaoIA,
)
from infra.ai_budget_sqlalchemy import (
    ConflitoReservaIA,
    EstadoReservaIA,
    LedgerFranquiasIASQLAlchemy,
    OrcamentoIndisponivelIA,
)


@dataclass(frozen=True, kw_only=True)
class PoliticaReservaIA:
    tenant_id: str
    unidade_id: str
    capability: str
    budget_id: str
    ciclo_id: str
    moeda: str
    maximo_por_tentativa: Decimal
    revisao_politica: int


class AIFranchiseBudgetGuard(GuardaConsumoIA):
    """Integra preautorizacao e concilia uso; nao cria creditos por consulta."""

    def __init__(
        self,
        *,
        ledger: LedgerFranquiasIASQLAlchemy,
        resolver_politica_local: Callable[[SolicitacaoIA, RotaIA], PoliticaReservaIA],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._ledger = ledger
        self._resolver = resolver_politica_local
        self._now = now

    def reservar(
        self, *, solicitacao: SolicitacaoIA, rota: RotaIA, tentativa: int
    ) -> ReservaAutorizadaIA:
        politica = self._resolver(solicitacao, rota)
        if (
            politica.tenant_id != solicitacao.tenant_id
            or politica.unidade_id != solicitacao.unidade_id
            or politica.capability != solicitacao.capability.value
        ):
            raise OrcamentoIndisponivelIA("politica_ia_escopo_divergente")
        if (
            not politica.maximo_por_tentativa.is_finite()
            or politica.maximo_por_tentativa <= 0
            or not politica.moeda
            or tentativa < 0
        ):
            raise OrcamentoIndisponivelIA("politica_ia_limite_invalido")
        # O identificador nao inclui o modelo para impedir que um mesmo attempt
        # possa ser repetido em outro provedor sem uma nova reserva autorizada.
        material = "|".join((
            solicitacao.tenant_id,
            solicitacao.unidade_id,
            solicitacao.capability.value,
            politica.ciclo_id,
            solicitacao.request_id,
            str(tentativa),
        ))
        reserva_id = str(uuid5(NAMESPACE_URL, material))
        status = self._ledger.reservar(
            reserva_id=reserva_id,
            budget_id=politica.budget_id,
            tenant_id=solicitacao.tenant_id,
            unidade_id=solicitacao.unidade_id,
            capability=solicitacao.capability.value,
            ciclo_id=politica.ciclo_id,
            request_id=solicitacao.request_id,
            attempt_key=str(tentativa),
            provider=rota.provider,
            model=rota.model,
            valor=politica.maximo_por_tentativa,
            agora=self._now(),
            expected_revision=politica.revisao_politica,
            falhar_em_replay=True,
        )
        if status is not EstadoReservaIA.RESERVED:
            raise ConflitoReservaIA("reserva_nao_autorizada")
        return ReservaAutorizadaIA(
            reserva_id=reserva_id,
            tenant_id=solicitacao.tenant_id,
            unidade_id=solicitacao.unidade_id,
            moeda=politica.moeda.upper(),
        )

    def reconciliar(
        self, *, reserva: ReservaAutorizadaIA, evento: AIUsageEvent | None
    ) -> None:
        # Timeout ou metering indisponivel: conservar reserva para reconciliar.
        real: Decimal | None = None
        if (
            evento is not None
            and evento.outcome is OutcomeIA.SUCESSO
            and evento.tenant_id == reserva.tenant_id
            and evento.unidade_id == reserva.unidade_id
            and evento.moeda == reserva.moeda
        ):
            real = evento.custo_real_calculado
        self._ledger.finalizar(
            reserva_id=reserva.reserva_id,
            tenant_id=reserva.tenant_id,
            unidade_id=reserva.unidade_id,
            valor_real=real,
            agora=self._now(),
        )
