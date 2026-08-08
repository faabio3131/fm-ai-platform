"""Porta append-only e implementacao atomica em memoria."""

from dataclasses import replace
from decimal import Decimal
from threading import RLock
from typing import Callable, Protocol, TypeVar

from .erros import (
    ConflitoIdempotenciaEstoque,
    ConcorrenciaEstoque,
    RecursoEstoqueIndisponivel,
    SaldoInsuficiente,
)
from .modelos import (
    MovimentoEstoque,
    ReservaEstoque,
    SaldoEstoque,
    TipoMovimento,
)

T = TypeVar("T")


class RepositorioEstoque(Protocol):
    def executar_atomicamente(self, operacao: Callable[[], T]) -> T: ...
    def append(
        self,
        movimento: MovimentoEstoque,
        *,
        versao_esperada: int | None = None,
        permitir_negativo: bool = False,
    ) -> MovimentoEstoque: ...
    def listar_movimentos(
        self, tenant_id: str, unidade_id: str, insumo_id: str | None = None
    ) -> tuple[MovimentoEstoque, ...]: ...
    def consultar_saldo(
        self, tenant_id: str, unidade_id: str, insumo_id: str
    ) -> SaldoEstoque: ...
    def por_idempotencia(
        self, tenant_id: str, unidade_id: str, chave: str
    ) -> tuple[MovimentoEstoque, ...]: ...
    def por_origem(
        self, tenant_id: str, unidade_id: str, origem_tipo: str, origem_id: str
    ) -> tuple[MovimentoEstoque, ...]: ...
    def salvar_reserva(self, reserva: ReservaEstoque) -> None: ...
    def buscar_reserva(
        self, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> ReservaEstoque | None: ...


class RepositorioEstoqueEmMemoria:
    def __init__(self) -> None:
        self._movimentos: list[MovimentoEstoque] = []
        self._reservas: dict[tuple[str, str, str], ReservaEstoque] = {}
        self._lock = RLock()

    def executar_atomicamente(self, operacao: Callable[[], T]) -> T:
        with self._lock:
            return operacao()

    def append(
        self,
        movimento: MovimentoEstoque,
        *,
        versao_esperada: int | None = None,
        permitir_negativo: bool = False,
    ) -> MovimentoEstoque:
        with self._lock:
            por_chave = self.por_idempotencia(
                movimento.tenant_id, movimento.unidade_id, movimento.idempotency_key
            )
            if por_chave:
                if movimento in por_chave:
                    return por_chave[0]
                raise ConflitoIdempotenciaEstoque("conflito_idempotencia")
            if any(m.chave_logica == movimento.chave_logica for m in self._movimentos):
                raise ConflitoIdempotenciaEstoque("movimento_logico_duplicado")
            saldo = self.consultar_saldo(
                movimento.tenant_id, movimento.unidade_id, movimento.insumo_id
            )
            if versao_esperada is not None and saldo.versao != versao_esperada:
                raise ConcorrenciaEstoque("versao_estoque_divergente")
            fisico, reservado = _aplicar(saldo, movimento)
            if (fisico < 0 or fisico - reservado < 0) and not permitir_negativo:
                raise SaldoInsuficiente("saldo_disponivel_insuficiente")
            self._movimentos.append(movimento)
            return movimento

    def listar_movimentos(
        self, tenant_id: str, unidade_id: str, insumo_id: str | None = None
    ) -> tuple[MovimentoEstoque, ...]:
        return tuple(
            sorted(
                (
                    m
                    for m in self._movimentos
                    if m.tenant_id == tenant_id
                    and m.unidade_id == unidade_id
                    and (insumo_id is None or m.insumo_id == insumo_id)
                ),
                key=lambda m: (m.occurred_at, m.movimento_id),
            )
        )

    def consultar_saldo(
        self, tenant_id: str, unidade_id: str, insumo_id: str
    ) -> SaldoEstoque:
        saldo = SaldoEstoque(
            tenant_id, unidade_id, insumo_id, Decimal(0), Decimal(0), 0
        )
        for movimento in self.listar_movimentos(tenant_id, unidade_id, insumo_id):
            fisico, reservado = _aplicar(saldo, movimento)
            saldo = replace(
                saldo,
                saldo_fisico=fisico,
                saldo_reservado=reservado,
                versao=saldo.versao + 1,
            )
        return saldo

    def consultar_saldo_disponivel(
        self, tenant_id: str, unidade_id: str, insumo_id: str
    ) -> Decimal:
        return self.consultar_saldo(tenant_id, unidade_id, insumo_id).saldo_disponivel

    def por_idempotencia(
        self, tenant_id: str, unidade_id: str, chave: str
    ) -> tuple[MovimentoEstoque, ...]:
        return tuple(
            m
            for m in self._movimentos
            if m.tenant_id == tenant_id
            and m.unidade_id == unidade_id
            and m.idempotency_key == chave
        )

    def por_origem(
        self, tenant_id: str, unidade_id: str, origem_tipo: str, origem_id: str
    ) -> tuple[MovimentoEstoque, ...]:
        return tuple(
            m
            for m in self.listar_movimentos(tenant_id, unidade_id)
            if m.origem_tipo == origem_tipo and m.origem_id == origem_id
        )

    def salvar_reserva(self, reserva: ReservaEstoque) -> None:
        chave = (reserva.tenant_id, reserva.unidade_id, reserva.pedido_id)
        atual = self._reservas.get(chave)
        if atual and atual.idempotency_key != reserva.idempotency_key:
            raise ConflitoIdempotenciaEstoque("reserva_existente")
        self._reservas[chave] = reserva

    def buscar_reserva(
        self, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> ReservaEstoque | None:
        return self._reservas.get((tenant_id, unidade_id, pedido_id))

    def consultar_reservas(
        self, tenant_id: str, unidade_id: str
    ) -> tuple[ReservaEstoque, ...]:
        return tuple(
            sorted(
                (
                    r
                    for (t, u, _), r in self._reservas.items()
                    if t == tenant_id and u == unidade_id
                ),
                key=lambda r: (r.criada_em, r.reserva_id),
            )
        )


def _aplicar(
    saldo: SaldoEstoque, movimento: MovimentoEstoque
) -> tuple[Decimal, Decimal]:
    q = movimento.quantidade
    fisico, reservado = saldo.saldo_fisico, saldo.saldo_reservado
    if movimento.tipo_movimento in {
        TipoMovimento.ENTRADA,
        TipoMovimento.AJUSTE_POSITIVO,
        TipoMovimento.DEVOLUCAO,
    }:
        fisico += q
    elif movimento.tipo_movimento == TipoMovimento.RESERVA:
        reservado += q
    elif movimento.tipo_movimento == TipoMovimento.LIBERACAO_RESERVA:
        reservado -= q
    elif movimento.tipo_movimento == TipoMovimento.CONSUMO:
        fisico -= q
        reservado -= min(q, reservado)
    elif movimento.tipo_movimento in {
        TipoMovimento.PERDA,
        TipoMovimento.AJUSTE_NEGATIVO,
    }:
        fisico -= q
    elif movimento.tipo_movimento == TipoMovimento.COMPENSACAO:
        fisico += q if movimento.metadata.get("direcao") == "positivo" else -q
    if reservado < 0:
        raise RecursoEstoqueIndisponivel("reserva_indisponivel")
    return fisico, reservado
