"""Repository financeiro SQLAlchemy, escopado e sem APIs destrutivas."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, TypeVar, cast
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus

from .erros import ConflitoIdempotenciaPagamento, ConcorrenciaPagamento
from .modelos import (
    CodigoCriterioFinanceiro,
    CriterioFinanceiro,
    MetodoPagamento,
    ObrigacaoPagamento,
    Pagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
    VendaFinanceira,
)
from .modelos_orm import (
    CriterioFinanceiroORM,
    ObrigacaoPagamentoORM,
    PagamentoORM,
    TransacaoPagamentoORM,
    VendaFinanceiraORM,
)

T = TypeVar("T")


def _utc(valor: object) -> datetime:
    instante = cast(datetime, valor)
    return (
        instante.replace(tzinfo=timezone.utc)
        if instante.tzinfo is None
        else instante.astimezone(timezone.utc)
    )


def _dinheiro(valor: object, moeda: str = "BRL") -> Dinheiro:
    return Dinheiro(Decimal(str(valor)), moeda)


class RepositorioPagamentosSQLAlchemy:
    """A transacao/commit pertence ao unit-of-work chamador."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def executar_atomicamente(self, operacao: Callable[[], T]) -> T:
        return operacao()

    def salvar_obrigacao(
        self, obrigacao: ObrigacaoPagamento, chave: str, fingerprint: str
    ) -> ObrigacaoPagamento:
        existente = self._session.scalar(
            select(ObrigacaoPagamentoORM).where(
                ObrigacaoPagamentoORM.tenant_id == obrigacao.tenant_id,
                ObrigacaoPagamentoORM.unidade_id == obrigacao.unidade_id,
                ObrigacaoPagamentoORM.idempotency_key == chave,
            )
        )
        if existente:
            if existente.request_hash != fingerprint:
                raise ConflitoIdempotenciaPagamento("conflito_idempotencia")
            return self._obrigacao(existente)
        row = ObrigacaoPagamentoORM(
            id=obrigacao.id,
            tenant_id=obrigacao.tenant_id,
            unidade_id=obrigacao.unidade_id,
            pedido_id=obrigacao.pedido_id,
            comanda_id=obrigacao.comanda_id,
            valor_previsto=obrigacao.valor_previsto.valor,
            moeda=obrigacao.valor_previsto.moeda,
            criado_em=obrigacao.criado_em,
            versao=obrigacao.versao,
            correlation_id=obrigacao.correlation_id,
            idempotency_key=chave,
            request_hash=fingerprint,
        )
        self._session.add(row)
        self._session.flush()
        return obrigacao

    def buscar_obrigacao(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> ObrigacaoPagamento | None:
        row = self._session.scalar(
            select(ObrigacaoPagamentoORM).where(
                ObrigacaoPagamentoORM.tenant_id == tenant_id,
                ObrigacaoPagamentoORM.unidade_id == unidade_id,
                ObrigacaoPagamentoORM.id == pagamento_id,
            )
        )
        return self._obrigacao(row) if row else None

    @staticmethod
    def _obrigacao(row: ObrigacaoPagamentoORM) -> ObrigacaoPagamento:
        return ObrigacaoPagamento(
            row.id,
            row.tenant_id,
            row.unidade_id,
            row.pedido_id,
            _dinheiro(row.valor_previsto, row.moeda),
            _utc(row.criado_em),
            row.versao,
            row.correlation_id,
            row.comanda_id,
        )

    def salvar_pagamento(self, pagamento: Pagamento, versao_esperada: int) -> None:
        if versao_esperada == 0:
            self._session.add(
                PagamentoORM(
                    id=pagamento.id,
                    tenant_id=pagamento.tenant_id,
                    unidade_id=pagamento.unidade_id,
                    pedido_id=pagamento.pedido_id,
                    comanda_id=pagamento.comanda_id,
                    status=pagamento.status.value,
                    metodo=pagamento.metodo.value,
                    valor_previsto=pagamento.valor_previsto.valor,
                    valor_pago=pagamento.valor_pago.valor,
                    valor_estornado=pagamento.valor_estornado.valor,
                    saldo=pagamento.saldo.valor,
                    moeda=pagamento.moeda,
                    recebimento_posterior=pagamento.recebimento_posterior,
                    provedor=pagamento.provedor,
                    criado_em=pagamento.criado_em,
                    atualizado_em=pagamento.atualizado_em,
                    versao=pagamento.versao,
                    correlation_id=pagamento.correlation_id,
                    idempotency_key=f"pagamento:{pagamento.id}",
                    request_hash=f"pagamento:{pagamento.id}",
                )
            )
            try:
                self._session.flush()
            except IntegrityError as exc:
                raise ConcorrenciaPagamento("pagamento_ja_existente") from exc
            return
        resultado = self._session.execute(
            update(PagamentoORM)
            .where(
                PagamentoORM.tenant_id == pagamento.tenant_id,
                PagamentoORM.unidade_id == pagamento.unidade_id,
                PagamentoORM.id == pagamento.id,
                PagamentoORM.versao == versao_esperada,
            )
            .values(
                status=pagamento.status.value,
                metodo=pagamento.metodo.value,
                valor_pago=pagamento.valor_pago.valor,
                valor_estornado=pagamento.valor_estornado.valor,
                saldo=pagamento.saldo.valor,
                atualizado_em=pagamento.atualizado_em,
                versao=pagamento.versao,
                correlation_id=pagamento.correlation_id,
            )
        )
        if getattr(resultado, "rowcount", 0) != 1:
            raise ConcorrenciaPagamento("compare_and_swap_falhou")

    def buscar_pagamento(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> Pagamento | None:
        row = self._session.scalar(
            select(PagamentoORM).where(
                PagamentoORM.tenant_id == tenant_id,
                PagamentoORM.unidade_id == unidade_id,
                PagamentoORM.id == pagamento_id,
            )
        )
        return self._pagamento(row) if row else None

    @staticmethod
    def _pagamento(row: PagamentoORM) -> Pagamento:
        return Pagamento(
            row.id,
            row.tenant_id,
            row.unidade_id,
            row.pedido_id,
            PagamentoStatus(row.status),
            MetodoPagamento(row.metodo),
            _dinheiro(row.valor_previsto, row.moeda),
            _dinheiro(row.valor_pago, row.moeda),
            _dinheiro(row.valor_estornado, row.moeda),
            _dinheiro(row.saldo, row.moeda),
            row.moeda,
            row.recebimento_posterior,
            _utc(row.criado_em),
            _utc(row.atualizado_em),
            row.versao,
            row.correlation_id,
            row.comanda_id,
            row.provedor,
        )

    def append_transacao(
        self, transacao: TransacaoPagamento, fingerprint: str
    ) -> TransacaoPagamento:
        existente = self._session.scalar(
            select(TransacaoPagamentoORM).where(
                TransacaoPagamentoORM.tenant_id == transacao.tenant_id,
                TransacaoPagamentoORM.unidade_id == transacao.unidade_id,
                TransacaoPagamentoORM.idempotency_key == transacao.idempotency_key,
            )
        )
        if existente:
            if existente.request_hash != fingerprint:
                raise ConflitoIdempotenciaPagamento("conflito_idempotencia")
            return self._transacao(existente)
        self._session.add(
            TransacaoPagamentoORM(
                transacao_id=transacao.transacao_id,
                tenant_id=transacao.tenant_id,
                unidade_id=transacao.unidade_id,
                pagamento_id=transacao.pagamento_id,
                tipo=transacao.tipo.value,
                status=transacao.status.value,
                valor=transacao.valor.valor,
                metodo=transacao.metodo.value,
                provedor=transacao.provedor,
                id_externo=transacao.id_externo,
                idempotency_key=transacao.idempotency_key,
                request_hash=fingerprint,
                occurred_at=transacao.occurred_at,
                processada_em=transacao.processada_em,
                correlation_id=transacao.correlation_id,
                causation_id=transacao.causation_id,
                payload_resumo=dict(transacao.payload_resumo),
                erro_normalizado=transacao.erro_normalizado,
            )
        )
        self._session.flush()
        return transacao

    def listar_transacoes(
        self, tenant_id: str, unidade_id: str, pagamento_id: str
    ) -> tuple[TransacaoPagamento, ...]:
        rows = self._session.scalars(
            select(TransacaoPagamentoORM)
            .where(
                TransacaoPagamentoORM.tenant_id == tenant_id,
                TransacaoPagamentoORM.unidade_id == unidade_id,
                TransacaoPagamentoORM.pagamento_id == pagamento_id,
            )
            .order_by(
                TransacaoPagamentoORM.occurred_at,
                TransacaoPagamentoORM.transacao_id,
            )
        ).all()
        return tuple(self._transacao(row) for row in rows)

    @staticmethod
    def _transacao(row: TransacaoPagamentoORM) -> TransacaoPagamento:
        return TransacaoPagamento(
            row.transacao_id,
            row.pagamento_id,
            row.tenant_id,
            row.unidade_id,
            TipoTransacao(row.tipo),
            StatusTransacao(row.status),
            _dinheiro(row.valor),
            MetodoPagamento(row.metodo),
            row.provedor,
            row.id_externo,
            row.idempotency_key,
            _utc(row.occurred_at),
            _utc(row.processada_em) if row.processada_em else None,
            row.correlation_id,
            row.causation_id,
            tuple(sorted(row.payload_resumo.items())),
            row.erro_normalizado,
        )

    def salvar_criterio(
        self,
        tenant_id: str,
        unidade_id: str,
        criterio: CriterioFinanceiro,
        chave: str,
        fingerprint: str,
    ) -> CriterioFinanceiro:
        existente = self._session.scalar(
            select(CriterioFinanceiroORM).where(
                CriterioFinanceiroORM.tenant_id == tenant_id,
                CriterioFinanceiroORM.unidade_id == unidade_id,
                CriterioFinanceiroORM.idempotency_key == chave,
            )
        )
        if existente:
            if dict(existente.metadata_segura).get("request_hash") != fingerprint:
                raise ConflitoIdempotenciaPagamento("conflito_idempotencia")
            return self._criterio(existente)
        metadata = dict(criterio.metadata)
        metadata["request_hash"] = fingerprint
        self._session.add(
            CriterioFinanceiroORM(
                id=str(uuid5(NAMESPACE_URL, f"{tenant_id}:{unidade_id}:{chave}")),
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                pedido_id=criterio.pedido_id,
                pagamento_id=criterio.pagamento_id,
                comanda_id=criterio.comanda_id,
                elegivel=criterio.elegivel,
                codigo=criterio.codigo.value,
                motivo=criterio.motivo,
                valor_reconhecivel=criterio.valor_reconhecivel.valor,
                policy=criterio.policy,
                versao=criterio.versao,
                ator=criterio.ator,
                timestamp=criterio.timestamp,
                correlation_id=criterio.correlation_id,
                metadata_segura=metadata,
                idempotency_key=chave,
            )
        )
        self._session.flush()
        return criterio

    def buscar_criterio(
        self, tenant_id: str, unidade_id: str, pedido_id: str, versao: int
    ) -> CriterioFinanceiro | None:
        row = self._session.scalar(
            select(CriterioFinanceiroORM).where(
                CriterioFinanceiroORM.tenant_id == tenant_id,
                CriterioFinanceiroORM.unidade_id == unidade_id,
                CriterioFinanceiroORM.pedido_id == pedido_id,
                CriterioFinanceiroORM.versao == versao,
            )
        )
        return self._criterio(row) if row else None

    @staticmethod
    def _criterio(row: CriterioFinanceiroORM) -> CriterioFinanceiro:
        metadata = dict(row.metadata_segura)
        metadata.pop("request_hash", None)
        return CriterioFinanceiro(
            row.elegivel,
            CodigoCriterioFinanceiro(row.codigo),
            row.motivo,
            row.pedido_id,
            _dinheiro(row.valor_reconhecivel),
            row.policy,
            row.versao,
            row.ator,
            _utc(row.timestamp),
            row.correlation_id,
            row.pagamento_id,
            row.comanda_id,
            tuple(sorted(metadata.items())),
        )

    def salvar_venda(self, venda: VendaFinanceira, fingerprint: str) -> VendaFinanceira:
        por_chave = self._session.scalar(
            select(VendaFinanceiraORM).where(
                VendaFinanceiraORM.tenant_id == venda.tenant_id,
                VendaFinanceiraORM.unidade_id == venda.unidade_id,
                VendaFinanceiraORM.idempotency_key == venda.idempotency_key,
            )
        )
        if por_chave:
            if por_chave.request_hash != fingerprint:
                raise ConflitoIdempotenciaPagamento("conflito_idempotencia")
            return self._venda(por_chave)
        equivalente = self.buscar_venda_pedido(
            venda.tenant_id,
            venda.unidade_id,
            venda.pedido_id,
            venda.criterio_versao,
        )
        if equivalente:
            raise ConflitoIdempotenciaPagamento("venda_equivalente_existente")
        self._session.add(
            VendaFinanceiraORM(
                id=venda.id,
                tenant_id=venda.tenant_id,
                unidade_id=venda.unidade_id,
                pedido_id=venda.pedido_id,
                pagamento_id=venda.pagamento_id,
                comanda_id=venda.comanda_id,
                criterio_codigo=venda.criterio_codigo.value,
                criterio_versao=venda.criterio_versao,
                valor=venda.valor.valor,
                moeda=venda.valor.moeda,
                metodo=venda.metodo.value,
                reconhecida_em=venda.reconhecida_em,
                correlation_id=venda.correlation_id,
                idempotency_key=venda.idempotency_key,
                request_hash=fingerprint,
            )
        )
        self._session.flush()
        return venda

    def buscar_venda_pedido(
        self, tenant_id: str, unidade_id: str, pedido_id: str, criterio_versao: int
    ) -> VendaFinanceira | None:
        row = self._session.scalar(
            select(VendaFinanceiraORM).where(
                VendaFinanceiraORM.tenant_id == tenant_id,
                VendaFinanceiraORM.unidade_id == unidade_id,
                VendaFinanceiraORM.pedido_id == pedido_id,
                VendaFinanceiraORM.criterio_versao == criterio_versao,
            )
        )
        return self._venda(row) if row else None

    def listar_vendas(
        self, tenant_id: str, unidade_id: str
    ) -> tuple[VendaFinanceira, ...]:
        rows = self._session.scalars(
            select(VendaFinanceiraORM).where(
                VendaFinanceiraORM.tenant_id == tenant_id,
                VendaFinanceiraORM.unidade_id == unidade_id,
            )
        ).all()
        return tuple(self._venda(row) for row in rows)

    @staticmethod
    def _venda(row: VendaFinanceiraORM) -> VendaFinanceira:
        return VendaFinanceira(
            row.id,
            row.tenant_id,
            row.unidade_id,
            row.pedido_id,
            row.pagamento_id,
            row.comanda_id,
            CodigoCriterioFinanceiro(row.criterio_codigo),
            row.criterio_versao,
            _dinheiro(row.valor, row.moeda),
            MetodoPagamento(row.metodo),
            _utc(row.reconhecida_em),
            row.correlation_id,
            row.idempotency_key,
        )
