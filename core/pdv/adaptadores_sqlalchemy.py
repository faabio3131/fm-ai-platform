"""Adapters concretos para os modelos legados injetados pela composition root."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any, Self
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .modelos import EntradaPDV, ResultadoPDV
from .modelos_orm import EfeitoCompatPDVORM, ReconciliacaoPDVORM, VendaLegadaLinkORM


class TipoEfeitoCompat(StrEnum):
    VENDA_LEGADA = "VENDA_LEGADA"
    ESTOQUE_LEGADO = "ESTOQUE_LEGADO"
    CASHBACK_USADO = "CASHBACK_USADO"
    CASHBACK_GANHO = "CASHBACK_GANHO"


_MENSAGENS_ERRO_PDV: dict[str, str] = {
    "estoque_insuficiente": "Estoque insuficiente para finalizar a venda.",
    "saldo_cashback_concorrente": "Saldo de cashback insuficiente ou alterado. Atualize os dados e tente novamente.",
    "cliente_indisponivel": "Cliente indisponível para concluir a operação.",
}


def mensagem_publica_erro_pdv(codigo: str) -> str:
    """Traduz código operacional estável em mensagem segura para o operador."""
    return _MENSAGENS_ERRO_PDV.get(
        codigo, "Não foi possível concluir a operação do PDV."
    )


class ErroOperacaoLegada(RuntimeError):
    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(mensagem_publica_erro_pdv(codigo))


class SQLAlchemyPDVUnitOfWork(AbstractContextManager["SQLAlchemyPDVUnitOfWork"]):
    """Dono exclusivo do commit/rollback; repositories recebem a mesma Session."""

    def __init__(
        self,
        fabrica: sessionmaker[Session],
        *,
        fechar: bool = True,
        fault: FaultInjector | None = None,
        session: Session | None = None,
    ) -> None:
        self._fabrica = fabrica
        self._fechar = fechar
        self.session: Session | None = session
        self.commits = 0
        self._fault = fault or (lambda _ponto: None)

    def __enter__(self) -> Self:
        if self.session is None:
            self.session = self._fabrica()
        return self

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("uow_nao_iniciado")
        self._fault("before_commit")
        self.session.commit()
        self.commits += 1

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.rollback()
        if self._fechar and self.session is not None:
            self.session.close()


class RepositorioPDVSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self.session = session

    def buscar_efeito(
        self, tenant: str, unidade: str, pedido_id: str, tipo: TipoEfeitoCompat
    ) -> EfeitoCompatPDVORM | None:
        return self.session.scalar(
            select(EfeitoCompatPDVORM).where(
                EfeitoCompatPDVORM.tenant_id == tenant,
                EfeitoCompatPDVORM.unidade_id == unidade,
                EfeitoCompatPDVORM.pedido_id == pedido_id,
                EfeitoCompatPDVORM.tipo_efeito == tipo.value,
            )
        )

    def contar_efeitos(
        self, tenant: str, unidade: str, pedido_id: str
    ) -> dict[str, int]:
        linhas = self.session.execute(
            select(EfeitoCompatPDVORM.tipo_efeito, func.count())
            .where(
                EfeitoCompatPDVORM.tenant_id == tenant,
                EfeitoCompatPDVORM.unidade_id == unidade,
                EfeitoCompatPDVORM.pedido_id == pedido_id,
            )
            .group_by(EfeitoCompatPDVORM.tipo_efeito)
        ).all()
        return {str(tipo): int(total) for tipo, total in linhas}

    def registrar_efeito(
        self,
        *,
        tenant: str,
        unidade: str,
        pedido_id: str,
        tipo: TipoEfeitoCompat,
        chave: str,
        referencia: str | None = None,
        instante: datetime,
    ) -> EfeitoCompatPDVORM:
        existente = self.buscar_efeito(tenant, unidade, pedido_id, tipo)
        if existente:
            return existente
        row = EfeitoCompatPDVORM(
            id=str(uuid5(NAMESPACE_URL, f"{tenant}:{unidade}:{chave}")),
            tenant_id=tenant,
            unidade_id=unidade,
            pedido_id=pedido_id,
            tipo_efeito=tipo.value,
            idempotency_key=chave,
            referencia_legada=referencia,
            criado_em=instante,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def criar_link(
        self,
        *,
        tenant: str,
        unidade: str,
        pedido_id: str,
        venda_financeira_id: str,
        venda_legada_id: str,
        instante: datetime,
    ) -> VendaLegadaLinkORM:
        existente = self.session.scalar(
            select(VendaLegadaLinkORM).where(
                VendaLegadaLinkORM.tenant_id == tenant,
                VendaLegadaLinkORM.unidade_id == unidade,
                VendaLegadaLinkORM.pedido_id == pedido_id,
            )
        )
        if existente:
            return existente
        row = VendaLegadaLinkORM(
            id=str(uuid5(NAMESPACE_URL, f"link:{tenant}:{unidade}:{pedido_id}")),
            tenant_id=tenant,
            unidade_id=unidade,
            pedido_id=pedido_id,
            venda_financeira_id=venda_financeira_id,
            venda_legada_id=venda_legada_id,
            criado_em=instante,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def reconciliar(self, **valores: Any) -> ReconciliacaoPDVORM:
        tenant = str(valores["tenant_id"])
        unidade = str(valores["unidade_id"])
        chave = str(valores["idempotency_key"])
        existente = self.session.scalar(
            select(ReconciliacaoPDVORM).where(
                ReconciliacaoPDVORM.tenant_id == tenant,
                ReconciliacaoPDVORM.unidade_id == unidade,
                ReconciliacaoPDVORM.idempotency_key == chave,
            )
        )
        if existente:
            return existente
        row = ReconciliacaoPDVORM(
            id=str(uuid5(NAMESPACE_URL, f"reconciliacao:{tenant}:{unidade}:{chave}")),
            **valores,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def buscar_reconciliacao(
        self, tenant: str, unidade: str, chave: str
    ) -> ReconciliacaoPDVORM | None:
        return self.session.scalar(
            select(ReconciliacaoPDVORM).where(
                ReconciliacaoPDVORM.tenant_id == tenant,
                ReconciliacaoPDVORM.unidade_id == unidade,
                ReconciliacaoPDVORM.idempotency_key == chave,
            )
        )


class LegacyPDVSQLAlchemyAdapter:
    """Uma unica fonte para Venda, baixa e cashback legados."""

    def __init__(
        self,
        *,
        session: Session,
        venda_cls: type[Any],
        cliente_cls: type[Any],
        insumo_cls: type[Any],
        ficha_tecnica_cls: type[Any],
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        rastrear_efeitos: bool,
        repositorio_pdv: RepositorioPDVSQLAlchemy | None = None,
        resolver_insumo: Callable[[int], Any | None] | None = None,
    ) -> None:
        self.session = session
        self.Venda = venda_cls
        self.Cliente = cliente_cls
        self.Insumo = insumo_cls
        self.Ficha = ficha_tecnica_cls
        self.tenant = tenant_id
        self.unidade = unidade_id
        self.pedido_id = pedido_id
        self.rastrear = rastrear_efeitos
        self.repo = repositorio_pdv or RepositorioPDVSQLAlchemy(session)
        self._resolver_insumo = resolver_insumo

    def _feito(self, tipo: TipoEfeitoCompat) -> EfeitoCompatPDVORM | None:
        return (
            self.repo.buscar_efeito(self.tenant, self.unidade, self.pedido_id, tipo)
            if self.rastrear
            else None
        )

    def _obter_insumo_no_escopo(self, insumo_id: int) -> Any | None:
        if self._resolver_insumo is not None:
            return self._resolver_insumo(insumo_id)
        return (
            self.session.query(self.Insumo)
            .filter(self.Insumo.id == insumo_id)
            .with_for_update()
            .first()
        )

    def validar_estoque(self, entrada: EntradaPDV) -> list[tuple[Any, Decimal]]:
        fichas = (
            self.session.query(self.Ficha)
            .filter(self.Ficha.produto_id == entrada.produto_id)
            .all()
        )
        consumos: list[tuple[Any, Decimal]] = []
        for ficha in fichas:
            insumo = self._obter_insumo_no_escopo(int(ficha.insumo_id))
            necessario = Decimal(str(ficha.quantidade_utilizada)) * entrada.quantidade
            if insumo is None or Decimal(str(insumo.saldo_atual or 0)) < necessario:
                raise ErroOperacaoLegada("estoque_insuficiente")
            consumos.append((insumo, necessario))
        return consumos

    def criar_venda_uma_vez(
        self, entrada: EntradaPDV, *, instante: datetime, status: str = "Aprovado"
    ) -> Any:
        existente = self._feito(TipoEfeitoCompat.VENDA_LEGADA)
        if existente and existente.referencia_legada:
            return self.session.get(self.Venda, int(existente.referencia_legada))
        venda = self.Venda(
            produto_id=entrada.produto_id,
            cliente_id=entrada.cliente_id,
            quantidade=entrada.quantidade,
            valor_total=float(entrada.total.valor),
            custo_total=float(entrada.custo_total.valor),
            forma_pagamento=entrada.forma_pagamento,
            status_pagamento=status,
            data_venda=instante.replace(tzinfo=None),
        )
        self.session.add(venda)
        self.session.flush()
        if self.rastrear:
            self.repo.registrar_efeito(
                tenant=self.tenant,
                unidade=self.unidade,
                pedido_id=self.pedido_id,
                tipo=TipoEfeitoCompat.VENDA_LEGADA,
                chave=f"{entrada.idempotency_key}:legacy_sale",
                referencia=str(venda.id),
                instante=instante,
            )
        return venda

    def baixar_estoque_uma_vez(
        self,
        entrada: EntradaPDV,
        consumos: list[tuple[Any, Decimal]],
        instante: datetime,
    ) -> None:
        if self._feito(TipoEfeitoCompat.ESTOQUE_LEGADO):
            return
        for insumo, necessario in consumos:
            insumo.saldo_atual = float(Decimal(str(insumo.saldo_atual)) - necessario)
        if self.rastrear:
            self.repo.registrar_efeito(
                tenant=self.tenant,
                unidade=self.unidade,
                pedido_id=self.pedido_id,
                tipo=TipoEfeitoCompat.ESTOQUE_LEGADO,
                chave=f"{entrada.idempotency_key}:legacy_stock",
                instante=instante,
            )

    def aplicar_cashback_uma_vez(self, entrada: EntradaPDV, instante: datetime) -> None:
        if entrada.cliente_id is None:
            return
        cliente = (
            self.session.query(self.Cliente)
            .filter(self.Cliente.id == entrada.cliente_id)
            .with_for_update()
            .first()
        )
        if cliente is None:
            raise ErroOperacaoLegada("cliente_indisponivel")
        efeito_usado = self._feito(TipoEfeitoCompat.CASHBACK_USADO)
        efeito_ganho = self._feito(TipoEfeitoCompat.CASHBACK_GANHO)
        if (
            self.rastrear
            and efeito_ganho
            and (not entrada.usar_cashback or efeito_usado)
        ):
            return
        saldo = Decimal(str(cliente.saldo_cashback or 0))
        if entrada.usar_cashback and not efeito_usado:
            if saldo < entrada.desconto_cashback.valor:
                raise ErroOperacaoLegada("saldo_cashback_concorrente")
            saldo -= entrada.desconto_cashback.valor
            if self.rastrear:
                self.repo.registrar_efeito(
                    tenant=self.tenant,
                    unidade=self.unidade,
                    pedido_id=self.pedido_id,
                    tipo=TipoEfeitoCompat.CASHBACK_USADO,
                    chave=f"{entrada.idempotency_key}:cashback_use",
                    instante=instante,
                )
        ganho = (entrada.total.valor * Decimal("0.05")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if not efeito_ganho:
            saldo += ganho
            if self.rastrear:
                self.repo.registrar_efeito(
                    tenant=self.tenant,
                    unidade=self.unidade,
                    pedido_id=self.pedido_id,
                    tipo=TipoEfeitoCompat.CASHBACK_GANHO,
                    chave=f"{entrada.idempotency_key}:cashback_gain",
                    instante=instante,
                )
        cliente.saldo_cashback = float(saldo)
        cliente.total_gasto = float(
            Decimal(str(cliente.total_gasto or 0)) + entrada.total.valor
        )
        cliente.ultima_compra = instante.replace(tzinfo=None)
        cliente.status = "Ativo"

    def executar(self, entrada: EntradaPDV) -> ResultadoPDV:
        instante = datetime.now(timezone.utc)
        consumos = self.validar_estoque(entrada)
        venda = self.criar_venda_uma_vez(entrada, instante=instante)
        self.baixar_estoque_uma_vez(entrada, consumos, instante)
        self.aplicar_cashback_uma_vez(entrada, instante)
        return ResultadoPDV("legacy", True, venda_legada_id=str(venda.id))


FaultInjector = Callable[[str], None]


class RegistroFalhaShadowSQLAlchemy:
    """Falha shadow e registrada numa terceira transacao curta e independente."""

    def __init__(
        self,
        fabrica: sessionmaker[Session],
        tenant_id: str,
        unidade_id: str,
        correlation_id: str,
    ) -> None:
        self.fabrica = fabrica
        self.tenant = tenant_id
        self.unidade = unidade_id
        self.correlation = correlation_id

    def registrar_falha_shadow(
        self, entrada: EntradaPDV, venda_legada_id: str | None, motivo: str
    ) -> None:
        with self.fabrica() as session:
            RepositorioPDVSQLAlchemy(session).reconciliar(
                tenant_id=self.tenant,
                unidade_id=self.unidade,
                modo="shadow",
                pedido_id=None,
                pagamento_id=None,
                venda_financeira_id=None,
                venda_legada_id=venda_legada_id,
                idempotency_key=f"{entrada.idempotency_key}:reconciliacao",
                valor_pedido=entrada.total.valor,
                valor_pagamento=None,
                valor_venda_financeira=None,
                valor_venda_legada=entrada.total.valor,
                estoque_estrategia="legado",
                cashback_usado=entrada.desconto_cashback.valor,
                cashback_ganho=(entrada.total.valor * Decimal(".05")).quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP
                ),
                status="reparo_necessario",
                divergencias=[
                    f"shadow_falhou:{motivo}",
                    f"correlation:{self.correlation}",
                ],
                criado_em=datetime.now(timezone.utc),
            )
            session.commit()
