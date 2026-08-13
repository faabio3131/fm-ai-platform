"""Orquestrador comercial do KDS V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.ids import PedidoId, TenantId, UnidadeId
from core.kds.adaptador_sqlalchemy import RepositorioKDSSQLAlchemy
from core.kds.erros import ErroKDS
from core.kds.modelos import FilaKDS, ProducaoItem, SetorProducao
from core.kds.modelos_orm import ProducaoItemORM
from core.kds.servicos import ResultadoComandoKDS, ServicoKDS
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy

from .kds_runtime_support import (
    auditar_roteamento_kds,
    publicar_evento_kds,
    transicionar_pedido_por_kds,
)


@dataclass(frozen=True)
class ResultadoKDSCanonico:
    item: ProducaoItem
    pedido_status: PedidoStatus
    idempotente: bool = False


class ServicoKDSCanonico:
    """Produção detalha cozinha; Pedido mantém o estado macro autoritativo."""

    def __init__(self, session: Session, *, agora=None) -> None:
        self.session = session
        self.agora = agora or (lambda: datetime.now(timezone.utc))
        self.kds_repo = RepositorioKDSSQLAlchemy(session)
        self.pedido_repo = RepositorioPedidosSQLAlchemy(session)
        self.outbox = RepositorioOutboxSQLAlchemy(session)
        self.auditoria = RepositorioAuditoriaSQLAlchemy(session)
        self.kds = ServicoKDS(self.kds_repo, self.auditoria, agora=self.agora)

    def listar_setores(self, contexto: ContextoExecucao) -> tuple[SetorProducao, ...]:
        return self.kds.listar_setores(contexto)

    def listar_fila(
        self, contexto: ContextoExecucao, *, setor_id: str | None = None
    ) -> FilaKDS:
        return self.kds.listar_fila_tolerante(contexto, setor_id=setor_id)

    def _pedido(self, contexto: ContextoExecucao, pedido_id: str):
        pedido = self.pedido_repo.buscar(
            TenantId(contexto.tenant_id),
            UnidadeId(contexto.unidade_id),
            PedidoId(pedido_id),
        )
        if pedido is None:
            raise ErroKDS("pedido_indisponivel")
        return pedido

    def _transicionar_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        pedido,
        destino: PedidoStatus,
        chave: str,
        instante: datetime,
        motivo: str,
    ):
        return transicionar_pedido_por_kds(
            session=self.session,
            pedido_repo=self.pedido_repo,
            outbox=self.outbox,
            auditoria=self.auditoria,
            contexto=contexto,
            pedido=pedido,
            destino=destino,
            chave=chave,
            instante=instante,
            motivo=motivo,
        )

    def rotear_item(
        self,
        contexto: ContextoExecucao,
        *,
        pedido_id: str,
        pedido_item_id: str,
        setor_id: str,
        quantidade: Decimal,
        idempotency_key: str,
        prioridade: int = 0,
        tentativa: int = 1,
        producao_id: str | None = None,
    ) -> ResultadoKDSCanonico:
        instante = self.agora().astimezone(timezone.utc)
        pedido = self._pedido(contexto, pedido_id)
        if pedido.status not in {
            PedidoStatus.CONFIRMADO,
            PedidoStatus.ENVIADO_PRODUCAO,
            PedidoStatus.EM_PREPARO,
        }:
            raise ErroKDS("pedido_fora_fluxo_producao")
        if pedido.status is PedidoStatus.CONFIRMADO:
            pedido = self._transicionar_pedido(
                contexto=contexto,
                pedido=pedido,
                destino=PedidoStatus.ENVIADO_PRODUCAO,
                chave=f"{idempotency_key}:pedido-enviado-producao",
                instante=instante,
                motivo="roteamento autorizado de item confirmado para o KDS",
            )
        antes = self.session.scalar(
            select(ProducaoItemORM).where(
                ProducaoItemORM.tenant_id == contexto.tenant_id,
                ProducaoItemORM.unidade_id == contexto.unidade_id,
                ProducaoItemORM.idempotency_key == idempotency_key,
            )
        )
        item = self.kds.rotear_item(
            contexto,
            pedido_id=pedido_id,
            pedido_item_id=pedido_item_id,
            setor_id=setor_id,
            quantidade=quantidade,
            idempotency_key=idempotency_key,
            prioridade=prioridade,
            tentativa=tentativa,
            producao_id=producao_id,
        )
        idempotente = antes is not None
        if not idempotente:
            auditar_roteamento_kds(
                auditoria=self.auditoria,
                contexto=contexto,
                item=item,
                instante=instante,
            )
        publicar_evento_kds(
            outbox=self.outbox,
            contexto=contexto,
            item=item,
            event_type="producaoroteada.v1",
            chave=f"{idempotency_key}:core",
            instante=instante,
            payload={
                "pedido_id": item.pedido_id,
                "pedido_item_id": item.pedido_item_id,
                "setor_id": item.setor_id,
                "quantidade": str(item.quantidade),
                "impressao_setor_pendente": True,
            },
        )
        return ResultadoKDSCanonico(item, pedido.status, idempotente)

    def _todos_prontos(self, item: ProducaoItem) -> bool:
        rows = self.session.scalars(
            select(ProducaoItemORM).where(
                ProducaoItemORM.tenant_id == item.tenant_id,
                ProducaoItemORM.unidade_id == item.unidade_id,
                ProducaoItemORM.pedido_id == item.pedido_id,
            )
        ).all()
        return bool(rows) and all(row.status in {"pronta", "retirada"} for row in rows)

    def _sincronizar_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        item: ProducaoItem,
        destino: str,
        chave: str,
        instante: datetime,
    ):
        pedido = self._pedido(contexto, item.pedido_id)
        if pedido.status in {PedidoStatus.CANCELADO, PedidoStatus.CONCLUIDO}:
            raise ErroKDS("pedido_terminal")
        if destino == "em_preparo" and pedido.status is PedidoStatus.ENVIADO_PRODUCAO:
            pedido = self._transicionar_pedido(
                contexto=contexto,
                pedido=pedido,
                destino=PedidoStatus.EM_PREPARO,
                chave=f"{chave}:pedido-em-preparo",
                instante=instante,
                motivo="inicio de preparo confirmado pelo KDS",
            )
        if destino in {"pronta", "retirada"} and self._todos_prontos(item):
            if pedido.status is PedidoStatus.ENVIADO_PRODUCAO:
                pedido = self._transicionar_pedido(
                    contexto=contexto,
                    pedido=pedido,
                    destino=PedidoStatus.EM_PREPARO,
                    chave=f"{chave}:pedido-em-preparo",
                    instante=instante,
                    motivo="produção finalizada sem etapa explícita de início",
                )
            if pedido.status is PedidoStatus.EM_PREPARO:
                pedido = self._transicionar_pedido(
                    contexto=contexto,
                    pedido=pedido,
                    destino=PedidoStatus.PRONTO,
                    chave=f"{chave}:pedido-pronto",
                    instante=instante,
                    motivo="todos os itens de produção estão prontos",
                )
        return pedido

    def transicionar(
        self,
        contexto: ContextoExecucao,
        *,
        producao_id: str,
        destino: str,
        versao_esperada: int,
        idempotency_key: str,
        precondicoes: dict[str, bool] | None = None,
        motivo: str | None = None,
    ) -> ResultadoKDSCanonico:
        instante = self.agora().astimezone(timezone.utc)
        resultado: ResultadoComandoKDS = self.kds.transicionar(
            contexto,
            producao_id=producao_id,
            destino=destino,
            versao_esperada=versao_esperada,
            idempotency_key=idempotency_key,
            precondicoes=precondicoes,
            motivo=motivo,
        )
        item = resultado.item
        publicar_evento_kds(
            outbox=self.outbox,
            contexto=contexto,
            item=item,
            event_type=f"producao{destino.replace('_', '')}.v1",
            chave=f"{idempotency_key}:core",
            instante=instante,
            payload={
                "pedido_id": item.pedido_id,
                "pedido_item_id": item.pedido_item_id,
                "setor_id": item.setor_id,
                "status": item.status,
            },
        )
        pedido = self._sincronizar_pedido(
            contexto=contexto,
            item=item,
            destino=destino,
            chave=idempotency_key,
            instante=instante,
        )
        return ResultadoKDSCanonico(item, pedido.status, resultado.idempotente)
