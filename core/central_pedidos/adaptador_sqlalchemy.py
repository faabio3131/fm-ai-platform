"""Projecao SQL eficiente; Pedido V1 permanece a unica fonte operacional."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, and_, cast, exists, func, not_, or_, select
from sqlalchemy.orm import Session, selectinload

from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pdv.modelos_orm import ReconciliacaoPDVORM, VendaLegadaLinkORM
from core.pedidos.modelos_orm import (
    EventoPedidoPersistidoORM,
    ItemPedidoORM,
    PedidoORM,
)
from core.seguranca import AutorizarAcao, ContextoExecucao, Permissao

from .alertas import ConfiguracaoAlertas, calcular_alertas
from .modelos import (
    DetalhePedidoCentral,
    EventoTimelineCentral,
    FiltroCentralPedidos,
    ItemDetalheCentral,
    PaginaPedidosCentral,
    ResumoFinanceiroCentral,
    ResumoPedidoCentral,
)


def _utc(value: object) -> datetime:
    result = (
        value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    )
    return (
        result.replace(tzinfo=timezone.utc)
        if result.utcoffset() is None
        else result.astimezone(timezone.utc)
    )


def _decimal(value: object | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class CentralPedidosSQLAlchemy:
    def __init__(
        self, session: Session, *, agora=None, alertas=ConfiguracaoAlertas()
    ) -> None:
        self._session = session
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._config_alertas = alertas

    @staticmethod
    def _autorizar(contexto: ContextoExecucao) -> None:
        decisao = AutorizarAcao().executar(
            contexto=contexto,
            permissao=Permissao.PEDIDO_VISUALIZAR,
            recurso="central_pedidos",
            tenant_recurso=contexto.tenant_id,
            unidade_recurso=contexto.unidade_id,
        )
        if not decisao.autorizado:
            raise PermissionError(decisao.codigo)

    def _financeiros(
        self, contexto: ContextoExecucao, ids: list[str]
    ) -> dict[str, ResumoFinanceiroCentral]:
        if not ids:
            return {}
        escopo = (contexto.tenant_id, contexto.unidade_id)
        pagamentos = (
            self._session.execute(
                select(PagamentoORM).where(
                    PagamentoORM.tenant_id == escopo[0],
                    PagamentoORM.unidade_id == escopo[1],
                    PagamentoORM.pedido_id.in_(ids),
                )
            )
            .scalars()
            .all()
        )
        vendas = {
            v.pedido_id: v
            for v in self._session.execute(
                select(VendaFinanceiraORM).where(
                    VendaFinanceiraORM.tenant_id == escopo[0],
                    VendaFinanceiraORM.unidade_id == escopo[1],
                    VendaFinanceiraORM.pedido_id.in_(ids),
                )
            ).scalars()
        }
        links = {
            v.pedido_id: v
            for v in self._session.execute(
                select(VendaLegadaLinkORM).where(
                    VendaLegadaLinkORM.tenant_id == escopo[0],
                    VendaLegadaLinkORM.unidade_id == escopo[1],
                    VendaLegadaLinkORM.pedido_id.in_(ids),
                )
            ).scalars()
        }
        recs: dict[str, ReconciliacaoPDVORM] = {}
        for v in self._session.execute(
            select(ReconciliacaoPDVORM)
            .where(
                ReconciliacaoPDVORM.tenant_id == escopo[0],
                ReconciliacaoPDVORM.unidade_id == escopo[1],
                ReconciliacaoPDVORM.pedido_id.in_(ids),
            )
            .order_by(ReconciliacaoPDVORM.criado_em.desc())
        ).scalars():
            if v.pedido_id and v.pedido_id not in recs:
                recs[v.pedido_id] = v
        por_pedido: dict[str, list[PagamentoORM]] = {}
        for pagamento in pagamentos:
            por_pedido.setdefault(pagamento.pedido_id, []).append(pagamento)
        retorno = {}
        for pedido_id in ids:
            ps = por_pedido.get(pedido_id, [])
            pago = sum(
                (_decimal(p.valor_pago) - _decimal(p.valor_estornado) for p in ps),
                Decimal(),
            )
            previsto = max(
                (_decimal(p.valor_previsto) for p in ps), default=Decimal("0.00")
            )
            confirmados = [p for p in ps if p.status == "pago"]
            situacao = (
                "ausente"
                if not ps
                else (
                    "confirmado"
                    if confirmados and pago >= previsto
                    else "parcial"
                    if pago > 0
                    else "pendente"
                )
            )
            venda, link, rec = (
                vendas.get(pedido_id),
                links.get(pedido_id),
                recs.get(pedido_id),
            )
            retorno[pedido_id] = ResumoFinanceiroCentral(
                situacao,
                previsto,
                pago,
                tuple(p.id for p in ps),
                venda.id if venda else None,
                link.venda_legada_id if link else None,
                rec.id if rec else None,
                rec.status if rec else None,
            )
        return retorno

    def listar(
        self, contexto: ContextoExecucao, filtros: FiltroCentralPedidos
    ) -> PaginaPedidosCentral:
        self._autorizar(contexto)
        itens_count = (
            select(func.count(ItemPedidoORM.id))
            .where(
                ItemPedidoORM.tenant_id == PedidoORM.tenant_id,
                ItemPedidoORM.unidade_id == PedidoORM.unidade_id,
                ItemPedidoORM.pedido_id == PedidoORM.id,
            )
            .correlate(PedidoORM)
            .scalar_subquery()
        )
        stmt = select(PedidoORM, itens_count.label("quantidade")).where(
            PedidoORM.tenant_id == contexto.tenant_id,
            PedidoORM.unidade_id == contexto.unidade_id,
        )
        if filtros.status:
            stmt = stmt.where(PedidoORM.status.in_(filtros.status))
        if filtros.canal:
            stmt = stmt.where(PedidoORM.canal.in_(filtros.canal))
        if filtros.criado_de:
            stmt = stmt.where(PedidoORM.criado_em >= filtros.criado_de)
        if filtros.criado_ate:
            stmt = stmt.where(PedidoORM.criado_em <= filtros.criado_ate)
        if filtros.pedido_id:
            stmt = stmt.where(PedidoORM.id == filtros.pedido_id)
        if filtros.cliente_id:
            stmt = stmt.where(PedidoORM.cliente_id == filtros.cliente_id)
        if filtros.busca:
            termo = f"%{filtros.busca.replace('%', r'\%').replace('_', r'\_')}%"
            stmt = stmt.where(
                or_(
                    PedidoORM.id.ilike(termo, escape="\\"),
                    cast(PedidoORM.cliente_id, String).ilike(termo, escape="\\"),
                )
            )
        stmt = self._aplicar_filtros_derivados(stmt, contexto, filtros)
        total = (
            self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        stmt = (
            stmt.order_by(PedidoORM.criado_em.desc(), PedidoORM.id.desc())
            .offset((filtros.pagina - 1) * filtros.tamanho_pagina)
            .limit(filtros.tamanho_pagina)
        )
        rows = self._session.execute(stmt).all()
        financeiros = self._financeiros(contexto, [row.id for row, _ in rows])
        resumos = []
        for row, quantidade in rows:
            financeiro = financeiros[row.id]
            alertas = calcular_alertas(
                status=row.status,
                atualizado_em=_utc(row.atualizado_em),
                financeiro=financeiro,
                agora=self._agora(),
                configuracao=self._config_alertas,
            )
            resumo = ResumoPedidoCentral(
                row.id,
                row.canal,
                row.status,
                _utc(row.criado_em),
                _utc(row.atualizado_em),
                _decimal(row.total),
                quantidade,
                row.cliente_id,
                financeiro,
                bool(alertas),
                row.origem,
                row.versao,
            )
            resumos.append(resumo)
        return PaginaPedidosCentral(
            tuple(resumos), filtros.pagina, filtros.tamanho_pagina, total
        )

    def _aplicar_filtros_derivados(self, stmt, contexto, filtros):
        """Aplica financeiro/alertas ao conjunto SQL antes de contar e paginar."""
        pagamento_escopo = and_(
            PagamentoORM.tenant_id == contexto.tenant_id,
            PagamentoORM.unidade_id == contexto.unidade_id,
            PagamentoORM.pedido_id == PedidoORM.id,
        )
        tem_pagamento = exists(select(PagamentoORM.id).where(pagamento_escopo))
        valor_pago = (
            select(
                func.coalesce(
                    func.sum(PagamentoORM.valor_pago - PagamentoORM.valor_estornado),
                    0,
                )
            )
            .where(pagamento_escopo)
            .correlate(PedidoORM)
            .scalar_subquery()
        )
        valor_previsto = (
            select(func.coalesce(func.max(PagamentoORM.valor_previsto), 0))
            .where(pagamento_escopo)
            .correlate(PedidoORM)
            .scalar_subquery()
        )
        tem_pago = exists(
            select(PagamentoORM.id).where(
                pagamento_escopo, PagamentoORM.status == "pago"
            )
        )
        confirmado = and_(tem_pago, valor_pago >= valor_previsto)
        parcial = and_(tem_pagamento, valor_pago > 0, not_(confirmado))
        pendente = and_(tem_pagamento, valor_pago <= 0)
        situacoes = {
            "ausente": not_(tem_pagamento),
            "confirmado": confirmado,
            "parcial": parcial,
            "pendente": pendente,
        }
        if filtros.situacao_financeira:
            criterio = situacoes.get(filtros.situacao_financeira)
            if criterio is None:
                raise ValueError("Situacao financeira invalida")
            stmt = stmt.where(criterio)
        if filtros.somente_com_alertas:
            nao_terminal = PedidoORM.status.not_in(("concluido", "cancelado"))
            pagamento_pendente = and_(nao_terminal, or_(pendente, parcial))
            reconciliacao_divergente = exists(
                select(ReconciliacaoPDVORM.id).where(
                    ReconciliacaoPDVORM.tenant_id == contexto.tenant_id,
                    ReconciliacaoPDVORM.unidade_id == contexto.unidade_id,
                    ReconciliacaoPDVORM.pedido_id == PedidoORM.id,
                    ReconciliacaoPDVORM.status == "divergente",
                )
            )
            limite = self._agora() - self._config_alertas.sem_atualizacao_apos
            sem_atualizacao = and_(nao_terminal, PedidoORM.atualizado_em <= limite)
            stmt = stmt.where(
                or_(pagamento_pendente, reconciliacao_divergente, sem_atualizacao)
            )
        return stmt

    def detalhar(
        self, contexto: ContextoExecucao, pedido_id: str
    ) -> DetalhePedidoCentral | None:
        self._autorizar(contexto)
        row = self._session.scalar(
            select(PedidoORM)
            .options(
                selectinload(PedidoORM.itens).selectinload(ItemPedidoORM.adicionais),
                selectinload(PedidoORM.observacoes),
            )
            .where(
                PedidoORM.tenant_id == contexto.tenant_id,
                PedidoORM.unidade_id == contexto.unidade_id,
                PedidoORM.id == pedido_id,
            )
        )
        if row is None:
            return None
        financeiro = self._financeiros(contexto, [pedido_id])[pedido_id]
        alertas = calcular_alertas(
            status=row.status,
            atualizado_em=_utc(row.atualizado_em),
            financeiro=financeiro,
            agora=self._agora(),
            configuracao=self._config_alertas,
        )
        resumo = ResumoPedidoCentral(
            row.id,
            row.canal,
            row.status,
            _utc(row.criado_em),
            _utc(row.atualizado_em),
            _decimal(row.total),
            len(row.itens),
            row.cliente_id,
            financeiro,
            bool(alertas),
            row.origem,
            row.versao,
        )
        eventos = self._session.scalars(
            select(EventoPedidoPersistidoORM)
            .where(
                EventoPedidoPersistidoORM.tenant_id == contexto.tenant_id,
                EventoPedidoPersistidoORM.unidade_id == contexto.unidade_id,
                EventoPedidoPersistidoORM.pedido_id == pedido_id,
            )
            .order_by(
                EventoPedidoPersistidoORM.occurred_at, EventoPedidoPersistidoORM.version
            )
        ).all()
        itens = tuple(
            ItemDetalheCentral(
                i.id,
                i.nome_produto,
                i.quantidade,
                _decimal(i.preco_unitario),
                _decimal(i.subtotal),
                i.observacao,
                tuple(
                    (
                        a.nome,
                        a.quantidade,
                        _decimal(a.preco_unitario),
                        _decimal(a.subtotal),
                    )
                    for a in i.adicionais
                ),
            )
            for i in row.itens
        )
        timeline = tuple(
            EventoTimelineCentral(
                e.event_id,
                e.event_type,
                _utc(e.occurred_at),
                e.version,
                e.correlation_id,
            )
            for e in eventos
        )
        return DetalhePedidoCentral(
            resumo,
            _decimal(row.subtotal),
            _decimal(row.descontos),
            _decimal(row.taxas),
            itens,
            tuple(o.texto for o in row.observacoes),
            timeline,
            financeiro,
            alertas,
        )
