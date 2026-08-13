"""Porta financeira e implementacao atomica append-only em memoria."""

from collections.abc import Callable
from threading import RLock
from typing import Protocol, TypeVar

from .erros import ConcorrenciaPagamento, ConflitoIdempotenciaPagamento
from .modelos import (
    CriterioFinanceiro,
    ObrigacaoPagamento,
    Pagamento,
    TipoTransacao,
    TransacaoPagamento,
    VendaFinanceira,
)

T = TypeVar("T")


class RepositorioPagamentos(Protocol):
    def executar_atomicamente(self, operacao: Callable[[], T]) -> T: ...
    def salvar_obrigacao(
        self, obrigacao: ObrigacaoPagamento, chave: str, fingerprint: str
    ) -> ObrigacaoPagamento: ...
    def buscar_obrigacao(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> ObrigacaoPagamento | None: ...
    def salvar_pagamento(self, pagamento: Pagamento, versao_esperada: int) -> None: ...
    def buscar_pagamento(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> Pagamento | None: ...
    def append_transacao(
        self, transacao: TransacaoPagamento, fingerprint: str
    ) -> TransacaoPagamento: ...
    def listar_transacoes(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> tuple[TransacaoPagamento, ...]: ...
    def buscar_transacao_externa(
        self, provedor: str, id_externo: str, tipo: TipoTransacao
    ) -> TransacaoPagamento | None: ...
    def salvar_venda(
        self, venda: VendaFinanceira, fingerprint: str
    ) -> VendaFinanceira: ...
    def buscar_venda_pedido(
        self, tenant_id: str, unidade_id: str, pedido_id: str, criterio_versao: int
    ) -> VendaFinanceira | None: ...
    def salvar_criterio(
        self,
        tenant_id: str,
        unidade_id: str,
        criterio: CriterioFinanceiro,
        chave: str,
        fingerprint: str,
    ) -> CriterioFinanceiro: ...
    def buscar_criterio(
        self, tenant_id: str, unidade_id: str, pedido_id: str, versao: int
    ) -> CriterioFinanceiro | None: ...


class RepositorioPagamentosEmMemoria:
    def __init__(self) -> None:
        self._obrigacoes: dict[tuple[str, str, str], ObrigacaoPagamento] = {}
        self._pagamentos: dict[tuple[str, str, str], Pagamento] = {}
        self._transacoes: list[TransacaoPagamento] = []
        self._vendas: list[VendaFinanceira] = []
        self._criterios: list[tuple[str, str, CriterioFinanceiro]] = []
        self._idem: dict[tuple[str, str, str, str], tuple[str, object]] = {}
        self._lock = RLock()

    def executar_atomicamente(self, operacao: Callable[[], T]) -> T:
        with self._lock:
            return operacao()

    def _idempotente(
        self,
        tipo: str,
        tenant: str,
        unidade: str,
        chave: str,
        fingerprint: str,
        valor: T,
    ) -> T:
        indice = (tipo, tenant, unidade, chave)
        existente = self._idem.get(indice)
        if existente:
            if existente[0] != fingerprint:
                raise ConflitoIdempotenciaPagamento("conflito_idempotencia")
            return existente[1]  # type: ignore[return-value]
        self._idem[indice] = (fingerprint, valor)
        return valor

    def salvar_obrigacao(
        self, obrigacao: ObrigacaoPagamento, chave: str, fingerprint: str
    ) -> ObrigacaoPagamento:
        anterior = self._idempotente(
            "obrigacao",
            obrigacao.tenant_id,
            obrigacao.unidade_id,
            chave,
            fingerprint,
            obrigacao,
        )
        if anterior is not obrigacao:
            return anterior
        indice = (obrigacao.tenant_id, obrigacao.unidade_id, obrigacao.id)
        if indice in self._obrigacoes:
            raise ConflitoIdempotenciaPagamento("obrigacao_duplicada")
        self._obrigacoes[indice] = obrigacao
        return obrigacao

    def buscar_obrigacao(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> ObrigacaoPagamento | None:
        return self._obrigacoes.get((tenant_id, unidade_id, pagamento_id))

    def salvar_pagamento(self, pagamento: Pagamento, versao_esperada: int) -> None:
        indice = (pagamento.tenant_id, pagamento.unidade_id, pagamento.id)
        atual = self._pagamentos.get(indice)
        versao = atual.versao if atual else 0
        if versao != versao_esperada:
            raise ConcorrenciaPagamento("versao_pagamento_divergente")
        self._pagamentos[indice] = pagamento

    def buscar_pagamento(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> Pagamento | None:
        return self._pagamentos.get((tenant_id, unidade_id, pagamento_id))

    def append_transacao(
        self, transacao: TransacaoPagamento, fingerprint: str
    ) -> TransacaoPagamento:
        anterior = self._idempotente(
            "transacao",
            transacao.tenant_id,
            transacao.unidade_id,
            transacao.idempotency_key,
            fingerprint,
            transacao,
        )
        if anterior is not transacao:
            return anterior
        self._transacoes.append(transacao)
        return transacao

    def listar_transacoes(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> tuple[TransacaoPagamento, ...]:
        return tuple(
            t
            for t in self._transacoes
            if t.tenant_id == tenant_id
            and t.unidade_id == unidade_id
            and t.pagamento_id == pagamento_id
        )

    def buscar_transacao_externa(
        self, provedor: str, id_externo: str, tipo: TipoTransacao
    ) -> TransacaoPagamento | None:
        encontradas = [
            t
            for t in self._transacoes
            if t.provedor == provedor
            and t.id_externo == id_externo
            and t.tipo is tipo
        ]
        if len(encontradas) > 1:
            escopos = {(t.tenant_id, t.unidade_id, t.pagamento_id) for t in encontradas}
            if len(escopos) > 1:
                raise ConflitoIdempotenciaPagamento("referencia_externa_ambigua")
        return encontradas[0] if encontradas else None

    def salvar_venda(self, venda: VendaFinanceira, fingerprint: str) -> VendaFinanceira:
        anterior = self._idempotente(
            "venda",
            venda.tenant_id,
            venda.unidade_id,
            venda.idempotency_key,
            fingerprint,
            venda,
        )
        if anterior is not venda:
            return anterior
        if self.buscar_venda_pedido(
            venda.tenant_id, venda.unidade_id, venda.pedido_id, venda.criterio_versao
        ):
            raise ConflitoIdempotenciaPagamento("venda_equivalente_existente")
        self._vendas.append(venda)
        return venda

    def buscar_venda_pedido(
        self, tenant_id: str, unidade_id: str, pedido_id: str, criterio_versao: int
    ) -> VendaFinanceira | None:
        return next(
            (
                v
                for v in self._vendas
                if v.tenant_id == tenant_id
                and v.unidade_id == unidade_id
                and v.pedido_id == pedido_id
                and v.criterio_versao == criterio_versao
            ),
            None,
        )

    def listar_vendas(
        self, tenant_id: str, unidade_id: str
    ) -> tuple[VendaFinanceira, ...]:
        return tuple(
            v
            for v in self._vendas
            if v.tenant_id == tenant_id and v.unidade_id == unidade_id
        )

    def salvar_criterio(
        self,
        tenant_id: str,
        unidade_id: str,
        criterio: CriterioFinanceiro,
        chave: str,
        fingerprint: str,
    ) -> CriterioFinanceiro:
        anterior = self._idempotente(
            "criterio", tenant_id, unidade_id, chave, fingerprint, criterio
        )
        if anterior is criterio:
            self._criterios.append((tenant_id, unidade_id, criterio))
        return anterior

    def buscar_criterio(
        self, tenant_id: str, unidade_id: str, pedido_id: str, versao: int
    ) -> CriterioFinanceiro | None:
        return next(
            (
                c
                for tenant, unidade, c in self._criterios
                if tenant == tenant_id and unidade == unidade_id
                if c.pedido_id == pedido_id and c.versao == versao
            ),
            None,
        )
