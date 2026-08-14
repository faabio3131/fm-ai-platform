"""Projeções canônicas e multi-tenant para consultas do Gerente IA V1."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.entrega.modelos_orm import EntregaORM
from core.estoque.modelos_orm import SaldoEstoqueORM
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import RegistroGerencial, ValorPrimitivo
from core.kds.modelos_orm import ProducaoItemORM
from core.pagamentos.modelos_orm import VendaFinanceiraORM
from core.pedidos.modelos_orm import PedidoORM
from core.salao.modelos_orm import MesaORM
from infra.integracoes.modelos_orm import ServicoExternoConfigORM


def _registro(tipo: str, **campos: ValorPrimitivo) -> RegistroGerencial:
    return RegistroGerencial(tipo, tuple(campos.items()))


class ConsultasGerenciaisSQLAlchemy:
    """Lê somente projeções canônicas, sempre limitadas ao escopo recebido."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _limite(filtros: dict[str, ValorPrimitivo]) -> int:
        bruto = filtros.get("limite", 50)
        if isinstance(bruto, bool) or not isinstance(bruto, (int, float)):
            raise ErroGerenteIA("limite_invalido")
        return max(1, min(int(bruto), 100))

    def consultar_pedidos(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        query = select(PedidoORM).where(
            PedidoORM.tenant_id == tenant_id, PedidoORM.unidade_id == unidade_id
        )
        status = filtros.get("status")
        if isinstance(status, str) and status:
            query = query.where(PedidoORM.status == status)
        rows = self._session.scalars(
            query.order_by(PedidoORM.criado_em.desc()).limit(self._limite(filtros))
        )
        return tuple(
            _registro(
                "pedido",
                pedido_id=row.id,
                status=row.status,
                canal=row.canal,
                total=float(Decimal(str(row.total))),
                versao=row.versao,
            )
            for row in rows
        )

    def consultar_atrasos(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        agora = datetime.now(timezone.utc)
        rows = self._session.scalars(
            select(ProducaoItemORM).where(
                ProducaoItemORM.tenant_id == tenant_id,
                ProducaoItemORM.unidade_id == unidade_id,
                ProducaoItemORM.status.not_in(("pronto", "retirado", "cancelado")),
            )
        )
        registros = []
        for row in rows:
            atualizado = cast(datetime, row.atualizado_em)
            if atualizado.tzinfo is None:
                atualizado = atualizado.replace(tzinfo=timezone.utc)
            minutos = max(0, int((agora - atualizado).total_seconds() // 60))
            registros.append(
                _registro(
                    "atraso",
                    pedido_id=row.pedido_id,
                    producao_item_id=row.id,
                    status=row.status,
                    minutos=minutos,
                    prioridade=row.prioridade,
                )
            )
        return tuple(registros)

    def consultar_mesas(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        rows = self._session.scalars(
            select(MesaORM).where(
                MesaORM.tenant_id == tenant_id,
                MesaORM.unidade_id == unidade_id,
                MesaORM.ativo.is_(True),
            )
        )
        return tuple(
            _registro("mesa", mesa_id=row.id, codigo=row.codigo, status=row.status)
            for row in rows
        )

    def consultar_cozinha(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        rows = self._session.execute(
            select(ProducaoItemORM.status, func.count())
            .where(
                ProducaoItemORM.tenant_id == tenant_id,
                ProducaoItemORM.unidade_id == unidade_id,
            )
            .group_by(ProducaoItemORM.status)
        )
        return tuple(
            _registro("cozinha", status=str(status), itens=int(total))
            for status, total in rows
        )

    def consultar_entregas(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        rows = self._session.scalars(
            select(EntregaORM).where(
                EntregaORM.tenant_id == tenant_id,
                EntregaORM.unidade_id == unidade_id,
            )
        )
        return tuple(
            _registro(
                "entrega",
                entrega_id=row.id,
                pedido_id=row.pedido_id,
                status=row.status,
                entregador_id=row.entregador_id,
            )
            for row in rows
        )

    def consultar_estoque(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        rows = self._session.scalars(
            select(SaldoEstoqueORM).where(
                SaldoEstoqueORM.tenant_id == tenant_id,
                SaldoEstoqueORM.unidade_id == unidade_id,
            )
        )
        return tuple(
            _registro(
                "estoque",
                insumo_id=row.insumo_id,
                saldo_fisico=float(Decimal(str(row.saldo_fisico))),
                saldo_reservado=float(Decimal(str(row.saldo_reservado))),
                disponivel=float(
                    Decimal(str(row.saldo_fisico)) - Decimal(str(row.saldo_reservado))
                ),
                versao=row.versao,
            )
            for row in rows
        )

    def sugerir_compra(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        return tuple(
            _registro(
                "sugestao_compra",
                insumo_id=registro.para_dict()["insumo_id"],
                motivo="saldo_disponivel_nao_positivo",
            )
            for registro in self.consultar_estoque(
                tenant_id=tenant_id, unidade_id=unidade_id, filtros={}
            )
            if float(registro.para_dict()["disponivel"] or 0) <= 0
        )

    def gerar_relatorio(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del filtros
        escopo_pedido = (PedidoORM.tenant_id == tenant_id, PedidoORM.unidade_id == unidade_id)
        pedidos = int(self._session.scalar(select(func.count()).select_from(PedidoORM).where(*escopo_pedido)) or 0)
        receita = self._session.scalar(
            select(func.coalesce(func.sum(VendaFinanceiraORM.valor), 0)).where(
                VendaFinanceiraORM.tenant_id == tenant_id,
                VendaFinanceiraORM.unidade_id == unidade_id,
            )
        )
        entregas_abertas = int(
            self._session.scalar(
                select(func.count()).select_from(EntregaORM).where(
                    EntregaORM.tenant_id == tenant_id,
                    EntregaORM.unidade_id == unidade_id,
                    EntregaORM.status.not_in(("entregue", "cancelada")),
                )
            )
            or 0
        )
        integracoes_prontas = int(
            self._session.scalar(
                select(func.count()).select_from(ServicoExternoConfigORM).where(
                    ServicoExternoConfigORM.tenant_id == tenant_id,
                    ServicoExternoConfigORM.unidade_id == unidade_id,
                    ServicoExternoConfigORM.habilitada.is_(True),
                    ServicoExternoConfigORM.homologada.is_(True),
                )
            )
            or 0
        )
        return (
            _registro(
                "visao_operacional_central",
                pedidos=pedidos,
                receita_confirmada=float(Decimal(str(receita))),
                entregas_abertas=entregas_abertas,
                itens_cozinha=sum(
                    int(item.para_dict()["itens"] or 0)
                    for item in self.consultar_cozinha(
                        tenant_id=tenant_id, unidade_id=unidade_id, filtros={}
                    )
                ),
                integracoes_prontas=integracoes_prontas,
            ),
        )

    def acompanhar_conversao(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        del tenant_id, unidade_id, filtros
        raise ErroGerenteIA("persistencia_crm_comercial_ainda_indisponivel")
