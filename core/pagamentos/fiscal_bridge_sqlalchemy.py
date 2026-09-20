"""Adapter SQLAlchemy do bridge fiscal dentro da autoridade financeira V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeVar, cast

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kordena_fiscal.domain import ExecutionScope, FiscalEnvironment

from .erros import (
    ConcorrenciaPagamento,
    ConflitoIdempotenciaPagamento,
    EfeitoFinanceiroFiscalBloqueado,
    ValorPagamentoInvalido,
)
from .fiscal_bridge import (
    AjusteObrigacaoCompra,
    DecisaoCreditoTributario,
    ObrigacaoCompraFiscal,
    ResultadoCreditoTributario,
    StatusObrigacaoCompra,
    StatusReconciliacaoCompra,
    TipoAjusteObrigacaoCompra,
)
from .modelos_orm import (
    AjusteObrigacaoCompraORM,
    DecisaoCreditoTributarioORM,
    ObrigacaoCompraFiscalORM,
)

T = TypeVar("T")


def _utc(valor: object) -> datetime:
    instante = cast(datetime, valor)
    return (
        instante.replace(tzinfo=timezone.utc)
        if instante.tzinfo is None
        else instante.astimezone(timezone.utc)
    )


def _scope(row: ObrigacaoCompraFiscalORM) -> ExecutionScope:
    return ExecutionScope(
        row.tenant_id,
        row.unidade_id,
        FiscalEnvironment(row.environment),
        row.correlation_id,
    )


class RepositorioBridgeFinanceiroFiscalSQLAlchemy:
    """Participa da Session/Unit of Work do chamador; nunca executa commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def unit_of_work_token(self) -> object:
        return self._session

    def atomicamente(self, operacao: Callable[[], T]) -> T:
        return operacao()

    def salvar_obrigacao(
        self, obrigacao: ObrigacaoCompraFiscal
    ) -> tuple[ObrigacaoCompraFiscal, bool]:
        existente = self._session.scalar(
            select(ObrigacaoCompraFiscalORM).where(
                ObrigacaoCompraFiscalORM.tenant_id == obrigacao.scope.tenant_id,
                ObrigacaoCompraFiscalORM.unidade_id == obrigacao.scope.unit_id,
                ObrigacaoCompraFiscalORM.environment
                == obrigacao.scope.environment.value,
                ObrigacaoCompraFiscalORM.recebimento_id == obrigacao.recebimento_id,
            )
        )
        if existente:
            atual = self._obrigacao(existente)
            if existente.request_hash != obrigacao.fingerprint:
                raise ConflitoIdempotenciaPagamento(
                    "recebimento_financeiro_divergente"
                )
            return atual, False
        self._session.add(
            ObrigacaoCompraFiscalORM(
                obrigacao_id=obrigacao.obrigacao_id,
                tenant_id=obrigacao.scope.tenant_id,
                unidade_id=obrigacao.scope.unit_id,
                environment=obrigacao.scope.environment.value,
                fornecedor_id=obrigacao.fornecedor_id,
                pedido_id=obrigacao.pedido_id,
                recebimento_id=obrigacao.recebimento_id,
                inbound_id=obrigacao.inbound_id,
                chave_acesso=obrigacao.chave_acesso,
                valor_original=obrigacao.valor_original,
                valor_ajustado=obrigacao.valor_ajustado,
                saldo=obrigacao.saldo,
                moeda=obrigacao.moeda,
                status=obrigacao.status.value,
                reconciliacao=obrigacao.reconciliacao.value,
                idempotency_key=obrigacao.idempotency_key,
                request_hash=obrigacao.fingerprint,
                criado_por=obrigacao.criado_por,
                criado_em=obrigacao.criado_em,
                correlation_id=obrigacao.correlation_id,
                versao=obrigacao.versao,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConcorrenciaPagamento("obrigacao_compra_concorrente") from exc
        return obrigacao, True

    def obrigacao_por_recebimento(
        self, scope: ExecutionScope, recebimento_id: str
    ) -> ObrigacaoCompraFiscal | None:
        row = self._session.scalar(
            select(ObrigacaoCompraFiscalORM).where(
                ObrigacaoCompraFiscalORM.tenant_id == scope.tenant_id,
                ObrigacaoCompraFiscalORM.unidade_id == scope.unit_id,
                ObrigacaoCompraFiscalORM.environment == scope.environment.value,
                ObrigacaoCompraFiscalORM.recebimento_id == recebimento_id,
            )
        )
        return self._obrigacao(row) if row else None

    def obrigacoes_por_pedido(
        self, scope: ExecutionScope, pedido_id: str
    ) -> tuple[ObrigacaoCompraFiscal, ...]:
        rows = self._session.scalars(
            select(ObrigacaoCompraFiscalORM).where(
                ObrigacaoCompraFiscalORM.tenant_id == scope.tenant_id,
                ObrigacaoCompraFiscalORM.unidade_id == scope.unit_id,
                ObrigacaoCompraFiscalORM.environment == scope.environment.value,
                ObrigacaoCompraFiscalORM.pedido_id == pedido_id,
            )
        ).all()
        return tuple(self._obrigacao(row) for row in rows)

    def salvar_ajuste(
        self, ajuste: AjusteObrigacaoCompra
    ) -> tuple[AjusteObrigacaoCompra, ObrigacaoCompraFiscal, bool]:
        existente = self._session.scalar(
            select(AjusteObrigacaoCompraORM).where(
                AjusteObrigacaoCompraORM.tenant_id == ajuste.scope.tenant_id,
                AjusteObrigacaoCompraORM.unidade_id == ajuste.scope.unit_id,
                AjusteObrigacaoCompraORM.environment == ajuste.scope.environment.value,
                AjusteObrigacaoCompraORM.idempotency_key == ajuste.idempotency_key,
            )
        )
        row = self._session.scalar(
            select(ObrigacaoCompraFiscalORM).where(
                ObrigacaoCompraFiscalORM.tenant_id == ajuste.scope.tenant_id,
                ObrigacaoCompraFiscalORM.unidade_id == ajuste.scope.unit_id,
                ObrigacaoCompraFiscalORM.environment == ajuste.scope.environment.value,
                ObrigacaoCompraFiscalORM.obrigacao_id == ajuste.obrigacao_id,
            )
        )
        if row is None:
            raise EfeitoFinanceiroFiscalBloqueado("obrigacao_compra_inexistente")
        obrigacao = self._obrigacao(row)
        if existente:
            atual = self._ajuste(existente, obrigacao.scope)
            if existente.request_hash != ajuste.fingerprint:
                raise ConflitoIdempotenciaPagamento("ajuste_financeiro_divergente")
            return atual, obrigacao, False
        if ajuste.valor > obrigacao.saldo:
            raise ValorPagamentoInvalido("ajuste_supera_saldo_obrigacao")
        novo_ajustado = obrigacao.valor_ajustado + ajuste.valor
        novo_saldo = obrigacao.valor_original - novo_ajustado
        novo_status = (
            StatusObrigacaoCompra.CANCELADA
            if novo_saldo == 0
            else StatusObrigacaoCompra.AJUSTADA
        )
        resultado = self._session.execute(
            update(ObrigacaoCompraFiscalORM)
            .where(
                ObrigacaoCompraFiscalORM.tenant_id == ajuste.scope.tenant_id,
                ObrigacaoCompraFiscalORM.unidade_id == ajuste.scope.unit_id,
                ObrigacaoCompraFiscalORM.environment == ajuste.scope.environment.value,
                ObrigacaoCompraFiscalORM.obrigacao_id == ajuste.obrigacao_id,
                ObrigacaoCompraFiscalORM.versao == obrigacao.versao,
            )
            .values(
                valor_ajustado=novo_ajustado,
                saldo=novo_saldo,
                status=novo_status.value,
                versao=obrigacao.versao + 1,
            )
        )
        if getattr(resultado, "rowcount", 0) != 1:
            raise ConcorrenciaPagamento("compare_and_swap_obrigacao_compra_falhou")
        self._session.add(
            AjusteObrigacaoCompraORM(
                ajuste_id=ajuste.ajuste_id,
                tenant_id=ajuste.scope.tenant_id,
                unidade_id=ajuste.scope.unit_id,
                environment=ajuste.scope.environment.value,
                obrigacao_id=ajuste.obrigacao_id,
                tipo=ajuste.tipo.value,
                valor=ajuste.valor,
                motivo=ajuste.motivo,
                origem_id=ajuste.origem_id,
                idempotency_key=ajuste.idempotency_key,
                request_hash=ajuste.fingerprint,
                criado_por=ajuste.criado_por,
                criado_em=ajuste.criado_em,
                correlation_id=ajuste.correlation_id,
            )
        )
        self._session.flush()
        return (
            ajuste,
            replace_obrigacao(
                obrigacao,
                valor_ajustado=novo_ajustado,
                saldo=novo_saldo,
                status=novo_status,
            ),
            True,
        )

    def ajuste_por_idempotencia(
        self, scope: ExecutionScope, idempotency_key: str
    ) -> AjusteObrigacaoCompra | None:
        row = self._session.scalar(
            select(AjusteObrigacaoCompraORM).where(
                AjusteObrigacaoCompraORM.tenant_id == scope.tenant_id,
                AjusteObrigacaoCompraORM.unidade_id == scope.unit_id,
                AjusteObrigacaoCompraORM.environment == scope.environment.value,
                AjusteObrigacaoCompraORM.idempotency_key == idempotency_key,
            )
        )
        return self._ajuste(row, scope) if row else None

    def salvar_decisao(
        self, decisao: DecisaoCreditoTributario
    ) -> tuple[DecisaoCreditoTributario, bool]:
        existente = self._session.scalar(
            select(DecisaoCreditoTributarioORM).where(
                DecisaoCreditoTributarioORM.tenant_id == decisao.scope.tenant_id,
                DecisaoCreditoTributarioORM.unidade_id == decisao.scope.unit_id,
                DecisaoCreditoTributarioORM.environment
                == decisao.scope.environment.value,
                DecisaoCreditoTributarioORM.idempotency_key
                == decisao.idempotency_key,
            )
        )
        if existente:
            atual = self._decisao(existente, decisao.scope)
            if existente.request_hash != decisao.fingerprint:
                raise ConflitoIdempotenciaPagamento("decisao_tributaria_divergente")
            return atual, False
        self._session.add(
            DecisaoCreditoTributarioORM(
                decisao_id=decisao.decisao_id,
                tenant_id=decisao.scope.tenant_id,
                unidade_id=decisao.scope.unit_id,
                environment=decisao.scope.environment.value,
                obrigacao_id=decisao.obrigacao_id,
                obrigacao_versao=decisao.obrigacao_versao,
                tributo=decisao.tributo,
                resultado=decisao.resultado.value,
                base_calculo=decisao.base_calculo,
                valor_destacado=decisao.valor_destacado,
                valor_credito=decisao.valor_credito,
                cfop=decisao.cfop,
                cst=decisao.cst,
                regra_id=decisao.regra_id,
                regra_versao=decisao.regra_versao,
                motivo=decisao.motivo,
                idempotency_key=decisao.idempotency_key,
                request_hash=decisao.fingerprint,
                decidido_por=decisao.decidido_por,
                decidido_em=decisao.decidido_em,
                correlation_id=decisao.correlation_id,
            )
        )
        self._session.flush()
        return decisao, True

    def listar_obrigacoes(
        self, scope: ExecutionScope
    ) -> tuple[ObrigacaoCompraFiscal, ...]:
        rows = self._session.scalars(
            select(ObrigacaoCompraFiscalORM).where(
                ObrigacaoCompraFiscalORM.tenant_id == scope.tenant_id,
                ObrigacaoCompraFiscalORM.unidade_id == scope.unit_id,
                ObrigacaoCompraFiscalORM.environment == scope.environment.value,
            )
        ).all()
        return tuple(self._obrigacao(row) for row in rows)

    def listar_decisoes(
        self, scope: ExecutionScope
    ) -> tuple[DecisaoCreditoTributario, ...]:
        rows = self._session.scalars(
            select(DecisaoCreditoTributarioORM).where(
                DecisaoCreditoTributarioORM.tenant_id == scope.tenant_id,
                DecisaoCreditoTributarioORM.unidade_id == scope.unit_id,
                DecisaoCreditoTributarioORM.environment == scope.environment.value,
            )
        ).all()
        return tuple(self._decisao(row, scope) for row in rows)

    @staticmethod
    def _obrigacao(row: ObrigacaoCompraFiscalORM) -> ObrigacaoCompraFiscal:
        return ObrigacaoCompraFiscal(
            row.obrigacao_id,
            _scope(row),
            row.fornecedor_id,
            row.pedido_id,
            row.recebimento_id,
            row.inbound_id,
            row.chave_acesso,
            Decimal(str(row.valor_original)),
            Decimal(str(row.valor_ajustado)),
            Decimal(str(row.saldo)),
            row.moeda,
            StatusObrigacaoCompra(row.status),
            StatusReconciliacaoCompra(row.reconciliacao),
            row.idempotency_key,
            row.criado_por,
            _utc(row.criado_em),
            row.correlation_id,
            row.versao,
        )

    @staticmethod
    def _ajuste(
        row: AjusteObrigacaoCompraORM, scope: ExecutionScope
    ) -> AjusteObrigacaoCompra:
        return AjusteObrigacaoCompra(
            row.ajuste_id,
            scope,
            row.obrigacao_id,
            TipoAjusteObrigacaoCompra(row.tipo),
            Decimal(str(row.valor)),
            row.motivo,
            row.origem_id,
            row.idempotency_key,
            row.criado_por,
            _utc(row.criado_em),
            row.correlation_id,
        )

    @staticmethod
    def _decisao(
        row: DecisaoCreditoTributarioORM, scope: ExecutionScope
    ) -> DecisaoCreditoTributario:
        return DecisaoCreditoTributario(
            row.decisao_id,
            scope,
            row.obrigacao_id,
            row.obrigacao_versao,
            row.tributo,
            ResultadoCreditoTributario(row.resultado),
            Decimal(str(row.base_calculo)),
            Decimal(str(row.valor_destacado)),
            Decimal(str(row.valor_credito)),
            row.cfop,
            row.cst,
            row.regra_id,
            row.regra_versao,
            row.motivo,
            row.idempotency_key,
            row.decidido_por,
            _utc(row.decidido_em),
            row.correlation_id,
        )


def replace_obrigacao(
    obrigacao: ObrigacaoCompraFiscal,
    *,
    valor_ajustado: Decimal,
    saldo: Decimal,
    status: StatusObrigacaoCompra,
) -> ObrigacaoCompraFiscal:
    return ObrigacaoCompraFiscal(
        obrigacao.obrigacao_id,
        obrigacao.scope,
        obrigacao.fornecedor_id,
        obrigacao.pedido_id,
        obrigacao.recebimento_id,
        obrigacao.inbound_id,
        obrigacao.chave_acesso,
        obrigacao.valor_original,
        valor_ajustado,
        saldo,
        obrigacao.moeda,
        status,
        obrigacao.reconciliacao,
        obrigacao.idempotency_key,
        obrigacao.criado_por,
        obrigacao.criado_em,
        obrigacao.correlation_id,
        obrigacao.versao + 1,
    )
