"""Ledger transacional de franquias de IA, isolado do financeiro do restaurante.

A autoridade do orçamento vem de uma politica comercial previamente autenticada.
Este adaptador NUNCA cria orçamento durante uma pergunta de IA e nunca acessa
provedores de modelos ou o Command para conferir cada consulta.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class AIBudgetBase(DeclarativeBase):
    pass


class FranquiaAIBudgetORM(AIBudgetBase):
    __tablename__ = "fm_ai_franchise_budgets_v1"
    __table_args__ = (
        CheckConstraint("limite >= 0", name="ck_ai_franchise_limite_v1"),
        CheckConstraint("consumido >= 0", name="ck_ai_franchise_consumido_v1"),
        CheckConstraint("reservado >= 0", name="ck_ai_franchise_reservado_v1"),
        UniqueConstraint(
            "tenant_id", "unidade_id", "capability", "ciclo_id",
            name="uq_ai_franchise_scope_cycle_v1",
        ),
        Index("ix_ai_franchise_scope_v1", "tenant_id", "unidade_id", "capability"),
    )

    budget_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(96), nullable=False)
    ciclo_id: Mapped[str] = mapped_column(String(96), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False)
    limite: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    consumido: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=Decimal(0))
    reservado: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=Decimal(0))
    revisao_politica: Mapped[int] = mapped_column(nullable=False)
    vigencia_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vigencia_fim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReservaAIBudgetORM(AIBudgetBase):
    __tablename__ = "fm_ai_franchise_reservations_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "unidade_id", "capability", "ciclo_id",
            "request_id", "attempt_key", name="uq_ai_franchise_attempt_v1",
        ),
        CheckConstraint("valor_reservado > 0", name="ck_ai_franchise_reserva_positiva_v1"),
        Index("ix_ai_franchise_reserva_status_v1", "budget_id", "status"),
    )

    reserva_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    budget_id: Mapped[str] = mapped_column(String(180), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(96), nullable=False)
    ciclo_id: Mapped[str] = mapped_column(String(96), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(96), nullable=False)
    model: Mapped[str] = mapped_column(String(192), nullable=False)
    valor_reservado: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    valor_final: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EstadoReservaIA(StrEnum):
    RESERVED = "reserved"
    PENDING_RECONCILIATION = "pending_reconciliation"
    COMMITTED = "committed"
    RELEASED = "released"


class ErroOrcamentoIA(RuntimeError):
    """Erro de orcamento controlado; nao contem prompt, chave ou dados privados."""


class OrcamentoIndisponivelIA(ErroOrcamentoIA):
    pass


class FranquiaEsgotadaIA(ErroOrcamentoIA):
    pass


class ConflitoReservaIA(ErroOrcamentoIA):
    pass


@dataclass(frozen=True)
class SaldoFranquiaIA:
    limite: Decimal
    consumido: Decimal
    reservado: Decimal
    disponivel: Decimal
    moeda: str
    ciclo_id: str
    revisao_politica: int


def _decimal_positivo(valor: Decimal, *, permitir_zero: bool = False) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("valor_financeiro_invalido") from exc
    if not numero.is_finite() or numero < 0 or (numero == 0 and not permitir_zero):
        raise ValueError("valor_financeiro_invalido")
    return numero


def _identidade(valor: str, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{campo}_obrigatorio")
    return valor.strip()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime_sem_timezone")
    return value.astimezone(timezone.utc)


def _db_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else _utc(value)


class LedgerFranquiasIASQLAlchemy:
    """Autoridade local: soma de gastos + reservas atomica no PostgreSQL.

    O metodo sincronizar_politica deve ser chamado SOMENTE pelo adaptador de
    politicas autenticadas, fora da rota publica de consultas de IA.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._sessions = session_factory

    def sincronizar_politica(
        self, *, budget_id: str, tenant_id: str, unidade_id: str,
        capability: str, ciclo_id: str, moeda: str, limite: Decimal,
        revisao_politica: int, vigencia_inicio: datetime, vigencia_fim: datetime,
    ) -> None:
        for name, value in (
            ("budget_id", budget_id), ("tenant_id", tenant_id),
            ("unidade_id", unidade_id), ("capability", capability),
            ("ciclo_id", ciclo_id),
        ):
            _identidade(value, name)
        if not isinstance(moeda, str) or len(moeda) != 3 or not moeda.isalpha():
            raise ValueError("moeda_invalida")
        amount = _decimal_positivo(limite, permitir_zero=True)
        start, end = _utc(vigencia_inicio), _utc(vigencia_fim)
        if end <= start or revisao_politica < 1:
            raise ValueError("politica_franquia_invalida")
        with self._sessions() as session, session.begin():
            old = session.get(FranquiaAIBudgetORM, budget_id, with_for_update=True)
            if old is None:
                session.add(FranquiaAIBudgetORM(
                    budget_id=budget_id, tenant_id=tenant_id, unidade_id=unidade_id,
                    capability=capability, ciclo_id=ciclo_id, moeda=moeda.upper(),
                    limite=amount, consumido=Decimal(0), reservado=Decimal(0),
                    revisao_politica=revisao_politica,
                    vigencia_inicio=start, vigencia_fim=end,
                ))
                return
            identity = (old.tenant_id, old.unidade_id, old.capability, old.ciclo_id, old.moeda)
            if identity != (tenant_id, unidade_id, capability, ciclo_id, moeda.upper()):
                raise ConflitoReservaIA("identidade_politica_divergente")
            if revisao_politica < old.revisao_politica:
                raise ConflitoReservaIA("politica_obsoleta")
            if revisao_politica == old.revisao_politica:
                if (old.limite != amount or _db_utc(old.vigencia_inicio) != start or _db_utc(old.vigencia_fim) != end):
                    raise ConflitoReservaIA("revisao_reutilizada_com_payload_diferente")
                return
            old.limite = amount
            old.revisao_politica = revisao_politica
            old.vigencia_inicio = start
            old.vigencia_fim = end

    def saldo(self, *, budget_id: str, tenant_id: str, unidade_id: str) -> SaldoFranquiaIA:
        with self._sessions() as session:
            row = session.get(FranquiaAIBudgetORM, _identidade(budget_id, "budget_id"))
            if row is None or (row.tenant_id, row.unidade_id) != (tenant_id, unidade_id):
                raise OrcamentoIndisponivelIA("franquia_nao_encontrada")
            return SaldoFranquiaIA(
                limite=row.limite, consumido=row.consumido, reservado=row.reservado,
                disponivel=max(Decimal(0), row.limite - row.consumido - row.reservado),
                moeda=row.moeda, ciclo_id=row.ciclo_id, revisao_politica=row.revisao_politica,
            )

    def reservar(
        self, *, reserva_id: str, budget_id: str, tenant_id: str,
        unidade_id: str, capability: str, ciclo_id: str,
        request_id: str, attempt_key: str, provider: str, model: str,
        valor: Decimal, agora: datetime, falhar_em_replay: bool = False,
        expected_revision: int | None = None,
    ) -> EstadoReservaIA:
        amount = _decimal_positivo(valor)
        instant = _utc(agora)
        for name, key in (
            ("reserva_id", reserva_id), ("budget_id", budget_id),
            ("tenant_id", tenant_id), ("unidade_id", unidade_id),
            ("capability", capability), ("ciclo_id", ciclo_id),
            ("request_id", request_id), ("attempt_key", attempt_key),
            ("provider", provider), ("model", model),
        ):
            _identidade(key, name)
        try:
            with self._sessions() as session, session.begin():
                existing = session.get(ReservaAIBudgetORM, reserva_id)
                if existing is not None:
                    expected = (budget_id, tenant_id, unidade_id, capability, ciclo_id, request_id, attempt_key, provider, model, amount)
                    actual = (existing.budget_id, existing.tenant_id, existing.unidade_id, existing.capability, existing.ciclo_id, existing.request_id, existing.attempt_key, existing.provider, existing.model, existing.valor_reservado)
                    if actual != expected:
                        raise ConflitoReservaIA("reserva_idempotencia_divergente")
                    if falhar_em_replay:
                        raise ConflitoReservaIA("reserva_replay_nao_pode_reexecutar_provider")
                    return EstadoReservaIA(existing.status)
                row = session.get(FranquiaAIBudgetORM, budget_id)
                if (row is None or
                    (row.tenant_id, row.unidade_id, row.capability, row.ciclo_id) !=
                    (tenant_id, unidade_id, capability, ciclo_id)):
                    raise OrcamentoIndisponivelIA("franquia_nao_encontrada")
                if not (_db_utc(row.vigencia_inicio) <= instant < _db_utc(row.vigencia_fim)):
                    raise OrcamentoIndisponivelIA("franquia_fora_da_vigencia")
                if expected_revision is not None and row.revisao_politica != expected_revision:
                    raise OrcamentoIndisponivelIA("franquia_revisao_desatualizada")
                session.add(ReservaAIBudgetORM(
                    reserva_id=reserva_id, budget_id=budget_id,
                    tenant_id=tenant_id, unidade_id=unidade_id,
                    capability=capability, ciclo_id=ciclo_id,
                    request_id=request_id, attempt_key=attempt_key,
                    provider=provider, model=model,
                    valor_reservado=amount, valor_final=None,
                    status=EstadoReservaIA.RESERVED.value, criado_em=instant,
                ))
                session.flush()
                # UPDATE condicional faz o check e a reserva em uma unica operacao
                # atomica no PostgreSQL, inclusive sob varias instancias concorrentes.
                result = session.execute(
                    update(FranquiaAIBudgetORM)
                    .where(
                        FranquiaAIBudgetORM.budget_id == budget_id,
                        *(
                            (FranquiaAIBudgetORM.revisao_politica == expected_revision,)
                            if expected_revision is not None else ()
                        ),
                        FranquiaAIBudgetORM.vigencia_inicio <= instant,
                        FranquiaAIBudgetORM.vigencia_fim > instant,
                        FranquiaAIBudgetORM.consumido +
                        FranquiaAIBudgetORM.reservado + amount <=
                        FranquiaAIBudgetORM.limite,
                    )
                    .values(reservado=FranquiaAIBudgetORM.reservado + amount)
                )
                if getattr(result, "rowcount", None) != 1:
                    raise FranquiaEsgotadaIA("franquia_saldo_insuficiente")
            return EstadoReservaIA.RESERVED
        except IntegrityError as exc:
            # Mesma operacao concorrente: nunca criar reserva extra por retry.
            with self._sessions() as session:
                old = session.get(ReservaAIBudgetORM, reserva_id)
                if old is not None and (old.budget_id, old.request_id, old.attempt_key, old.valor_reservado) == (budget_id, request_id, attempt_key, amount):
                    if falhar_em_replay:
                        raise ConflitoReservaIA("reserva_replay_nao_pode_reexecutar_provider") from exc
                    return EstadoReservaIA(old.status)
            raise ConflitoReservaIA("reserva_concorrente_duplicada") from exc

    def finalizar(
        self, *, reserva_id: str, tenant_id: str, unidade_id: str,
        valor_real: Decimal | None, agora: datetime, sem_cobranca_comprovada: bool = False,
    ) -> EstadoReservaIA:
        instant = _utc(agora)
        if sem_cobranca_comprovada and valor_real is not None:
            raise ValueError("liquidacao_ambigua")
        real = _decimal_positivo(valor_real, permitir_zero=True) if valor_real is not None else None
        with self._sessions() as session, session.begin():
            reservation = session.get(ReservaAIBudgetORM, _identidade(reserva_id, "reserva_id"), with_for_update=True)
            if reservation is None or (reservation.tenant_id, reservation.unidade_id) != (tenant_id, unidade_id):
                raise OrcamentoIndisponivelIA("reserva_nao_encontrada")
            if reservation.status in (EstadoReservaIA.COMMITTED.value, EstadoReservaIA.RELEASED.value):
                if (reservation.status == EstadoReservaIA.COMMITTED.value and real == reservation.valor_final) or (reservation.status == EstadoReservaIA.RELEASED.value and sem_cobranca_comprovada):
                    return EstadoReservaIA(reservation.status)
                raise ConflitoReservaIA("finalizacao_repetida_divergente")
            if real is None and not sem_cobranca_comprovada:
                reservation.status = EstadoReservaIA.PENDING_RECONCILIATION.value
                return EstadoReservaIA.PENDING_RECONCILIATION
            # A finalizacao atomica diminui a reserva e aumenta o custo confirmado.
            # Se o provedor cobrar acima do reservado, contabiliza a diferenca real:
            # as novas reservas falham naturalmente ate recomposicao da franquia.
            session.execute(
                update(FranquiaAIBudgetORM)
                .where(FranquiaAIBudgetORM.budget_id == reservation.budget_id)
                .values(
                    reservado=FranquiaAIBudgetORM.reservado - reservation.valor_reservado,
                    consumido=FranquiaAIBudgetORM.consumido + (real or Decimal(0)),
                )
            )
            reservation.valor_final = real
            reservation.finalizado_em = instant
            reservation.status = (
                EstadoReservaIA.RELEASED.value if sem_cobranca_comprovada
                else EstadoReservaIA.COMMITTED.value
            )
            return EstadoReservaIA(reservation.status)
