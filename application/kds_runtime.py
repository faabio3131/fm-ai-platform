"""Composição comercial do KDS V1 sobre Pedido/Outbox/Auditoria autoritativos."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    PedidoId,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.kds.adaptador_sqlalchemy import RepositorioKDSSQLAlchemy
from core.kds.erros import ErroKDS
from core.kds.modelos import FilaKDS, ProducaoItem, SetorProducao
from core.kds.modelos_orm import ProducaoItemORM
from core.kds.servicos import ResultadoComandoKDS, ServicoKDS
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.servicos import transicionar_pedido
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


@dataclass(frozen=True)
class ResultadoKDSCanonico:
    item: ProducaoItem
    pedido_status: PedidoStatus
    idempotente: bool = False


class ServicoKDSCanonico:
    """Mantém Produção como detalhe de cozinha e Pedido como estado macro oficial."""

    def __init__(self, session: Session, *, agora=None) -> None:
        self.session = session
        self.agora = agora or (lambda: datetime.now(timezone.utc))
        self.kds_repo = RepositorioKDSSQLAlchemy(session)
        self.pedido_repo = RepositorioPedidosSQLAlchemy(session)
        self.outbox = RepositorioOutboxSQLAlchemy(session)
        self.auditoria = RepositorioAuditoriaSQLAlchemy(session)
        self.kds = ServicoKDS(
            self.kds_repo,
            self.auditoria,
            agora=self.agora,
        )

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

    @staticmethod
    def _contexto_sistema(
        contexto: ContextoExecucao, *, motivo: str, instante: datetime
    ) -> ContextoExecucao:
        tecnico = ContextoExecucao.sistema(
            identidade="kds-orquestrador-v1",
            motivo=motivo,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            correlation_id=contexto.correlation_id,
            solicitado_em=instante,
        )
        return replace(tecnico, permissoes=frozenset({Permissao.PEDIDO_ALTERAR}))

    def _transicionar_pedido_derivado(
        self,
        *,
        contexto: ContextoExecucao,
        pedido,
        destino: PedidoStatus,
        chave: str,
        instante: datetime,
        motivo: str,
    ):
        if pedido.status is destino:
            return pedido
        resultado = transicionar_pedido(
            tenant_id=pedido.tenant_id,
            unidade_id=pedido.unidade_id,
            pedido_id=pedido.id,
            destino=destino,
            versao_esperada=pedido.versao,
            idempotency_key=IdempotencyKey(chave),
            contexto=self._contexto_sistema(
                contexto,
                motivo=motivo,
                instante=instante,
            ),
            repositorio=self.pedido_repo,
            outbox=self.outbox,
            auditoria=self.auditoria,
            timestamp=instante,
            metadata={"origem_derivada": "kds"},
        )
        return resultado.pedido

    def _publicar_evento_kds(
        self,
        *,
        contexto: ContextoExecucao,
        item: ProducaoItem,
        event_type: str,
        chave: str,
        instante: datetime,
        payload: dict[str, object],
    ) -> None:
        tenant = TenantId(contexto.tenant_id)
        unidade = UnidadeId(contexto.unidade_id)
        idem = IdempotencyKey(chave)
        existente = self.outbox.consultar(
            tenant_id=tenant,
            unidade_id=unidade,
            idempotency_key=idem,
        )
        if existente is not None:
            if existente.aggregate_id != item.producao_id or existente.event_type != event_type:
                raise ErroKDS("conflito_evento_core")
            return
        self.outbox.adicionar(
            EnvelopeMensagem(
                event_id=EventoId(
                    str(
                        uuid5(
                            NAMESPACE_URL,
                            f"{contexto.tenant_id}:{contexto.unidade_id}:{chave}",
                        )
                    )
                ),
                event_type=event_type,
                aggregate_id=item.producao_id,
                aggregate_type="producao",
                tenant_id=tenant,
                unidade_id=unidade,
                correlation_id=CorrelationId(contexto.correlation_id),
                causation_id=None,
                idempotency_key=idem,
                occurred_at=instante,
                payload=payload,
                version=item.versao,
            )
        )

    def _auditar_roteamento(
        self,
        *,
        contexto: ContextoExecucao,
        item: ProducaoItem,
        instante: datetime,
    ) -> None:
        papel = next(iter(sorted(contexto.papeis, key=str)), None)
        self.auditoria.adicionar(
            EventoAuditoria(
                audit_id=str(uuid4()),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                usuario_id=contexto.usuario_id,
                papel_efetivo=papel,
                acao="producao.rotear",
                recurso_tipo="producao",
                recurso_id=item.producao_id,
                resultado="permitido",
                motivo="roteamento_kds_canonico",
                correlation_id=contexto.correlation_id,
                timestamp=instante,
                origem=contexto.origem,
                politica="producao_atualizar",
                causation_id=contexto.causation_id,
                depois_resumido=(("estado", item.status), ("setor_id", item.setor_id)),
                metadata=sanitizar_metadata(
                    {
                        "pedido_id": item.pedido_id,
                        "pedido_item_id": item.pedido_item_id,
                    }
                ),
            )
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
            pedido = self._transicionar_pedido_derivado(
                contexto=contexto,
                pedido=pedido,
                destino=PedidoStatus.ENVIADO_PRODUCAO,
                chave=f"{idempotency_key}:pedido-enviado-producao",
                instante=instante,
                motivo="roteamento autorizado de item confirmado para o KDS",
            )

        antes = self.kds_repo.session.scalar(
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
            self._auditar_roteamento(contexto=contexto, item=item, instante=instante)
        self._publicar_evento_kds(
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

    def _sincronizar_pedido_pos_transicao(
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
            pedido = self._transicionar_pedido_derivado(
                contexto=contexto,
                pedido=pedido,
                destino=PedidoStatus.EM_PREPARO,
                chave=f"{chave}:pedido-em-preparo",
                instante=instante,
                motivo="inicio de preparo confirmado pelo KDS",
            )

        if destino in {"pronta", "retirada"} and self._todos_prontos(item):
            if pedido.status is PedidoStatus.ENVIADO_PRODUCAO:
                pedido = self._transicionar_pedido_derivado(
                    contexto=contexto,
                    pedido=pedido,
                    destino=PedidoStatus.EM_PREPARO,
                    chave=f"{chave}:pedido-em-preparo",
                    instante=instante,
                    motivo="produção finalizada sem etapa explícita de início",
                )
            if pedido.status is PedidoStatus.EM_PREPARO:
                pedido = self._transicionar_pedido_derivado(
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
        self._publicar_evento_kds(
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
        pedido = self._sincronizar_pedido_pos_transicao(
            contexto=contexto,
            item=item,
            destino=destino,
            chave=idempotency_key,
            instante=instante,
        )
        return ResultadoKDSCanonico(item, pedido.status, resultado.idempotente)
