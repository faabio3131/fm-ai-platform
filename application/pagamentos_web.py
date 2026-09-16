"""Façade Web de observabilidade e reconciliação do ledger financeiro canônico."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from application.pagbank_reconciliacao import reconciliar_order_pagbank_em_transacao
from core.pagamentos.modelos import Pagamento, TipoTransacao, TransacaoPagamento
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from infra.pagamentos.pagbank_runtime import PagBankAdapterFactory
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class TransacaoPagamentoWeb:
    transacao_id: str
    tipo: str
    status: str
    valor: str
    metodo: str
    provedor: str | None
    id_externo: str | None
    occurred_at: datetime
    correlation_id: str
    erro_normalizado: str | None


@dataclass(frozen=True)
class PagamentoWeb:
    pagamento_id: str
    pedido_id: str
    status: str
    metodo: str
    valor_previsto: str
    valor_pago: str
    valor_estornado: str
    saldo: str
    moeda: str
    provedor: str | None
    versao: int
    atualizado_em: datetime
    transacoes: tuple[TransacaoPagamentoWeb, ...]


def _dinheiro(valor: Decimal) -> str:
    return format(valor.quantize(Decimal("0.01")), "f")


def _snapshot(pagamento: Pagamento, transacoes: tuple[TransacaoPagamento, ...]) -> PagamentoWeb:
    return PagamentoWeb(
        pagamento_id=pagamento.id,
        pedido_id=pagamento.pedido_id,
        status=pagamento.status.value,
        metodo=pagamento.metodo.value,
        valor_previsto=_dinheiro(pagamento.valor_previsto.valor),
        valor_pago=_dinheiro(pagamento.valor_pago.valor),
        valor_estornado=_dinheiro(pagamento.valor_estornado.valor),
        saldo=_dinheiro(pagamento.saldo.valor),
        moeda=pagamento.moeda,
        provedor=pagamento.provedor,
        versao=pagamento.versao,
        atualizado_em=pagamento.atualizado_em,
        transacoes=tuple(
            TransacaoPagamentoWeb(
                transacao_id=item.transacao_id,
                tipo=item.tipo.value,
                status=item.status.value,
                valor=_dinheiro(item.valor.valor),
                metodo=item.metodo.value,
                provedor=item.provedor,
                id_externo=item.id_externo,
                occurred_at=item.occurred_at,
                correlation_id=item.correlation_id,
                erro_normalizado=item.erro_normalizado,
            )
            for item in transacoes
        ),
    )


class AplicacaoPagamentosWebV1:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._secret_store = secret_store

    @staticmethod
    def _exigir(contexto: ContextoExecucao, permissao: Permissao) -> None:
        if permissao not in contexto.permissoes:
            raise PermissionError("seguranca.pagamentos_permissao_exigida")

    def obter(self, *, contexto: ContextoExecucao, pagamento_id: str) -> PagamentoWeb:
        self._exigir(contexto, Permissao.FINANCEIRO_VISUALIZAR)
        pagamento_id = pagamento_id.strip()
        if not pagamento_id:
            raise ValueError("pagamento_id_invalido")
        with UnitOfWorkV1(self._session_factory) as uow:
            pagamento = uow.pagamentos.buscar_pagamento(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            if pagamento is None:
                raise LookupError("pagamento_nao_encontrado")
            transacoes = uow.pagamentos.listar_transacoes(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            return _snapshot(pagamento, transacoes)

    def reconciliar_pagbank(
        self,
        *,
        contexto: ContextoExecucao,
        pagamento_id: str,
    ) -> PagamentoWeb:
        self._exigir(contexto, Permissao.FINANCEIRO_VISUALIZAR)
        self._exigir(contexto, Permissao.PAGAMENTO_CONFIRMAR)
        pagamento_id = pagamento_id.strip()
        if not pagamento_id:
            raise ValueError("pagamento_id_invalido")

        with UnitOfWorkV1(self._session_factory) as uow:
            pagamento = uow.pagamentos.buscar_pagamento(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            if pagamento is None:
                raise LookupError("pagamento_nao_encontrado")

            transacoes = uow.pagamentos.listar_transacoes(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            iniciacao = next(
                (
                    item
                    for item in transacoes
                    if item.provedor == "pagbank"
                    and item.tipo is TipoTransacao.INICIACAO
                    and item.id_externo
                ),
                None,
            )
            if iniciacao is None or not iniciacao.id_externo:
                raise ValueError("pagamento_sem_order_pagbank")

            adapter = PagBankAdapterFactory(secret_store=self._secret_store).construir(
                session=uow.recursos.session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
            )
            resultado = reconciliar_order_pagbank_em_transacao(
                recursos=uow.recursos,
                adapter=adapter,
                order_id=iniciacao.id_externo,
                timestamp=datetime.now(timezone.utc),
            )
            if resultado is not None:
                uow.commit()

            atualizado = uow.pagamentos.buscar_pagamento(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            if atualizado is None:
                raise RuntimeError("pagamento_desapareceu_apos_reconciliacao")
            transacoes_atualizadas = uow.pagamentos.listar_transacoes(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            return _snapshot(atualizado, transacoes_atualizadas)
