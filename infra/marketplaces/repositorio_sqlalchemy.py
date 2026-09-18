"""Adapters persistentes mínimos do WP-012 sobre autoridades V1 existentes."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.central_pedidos.servicos import ServicoComandosCentral
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.ids import (
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.marketplaces.erros import ErroMarketplace
from core.marketplaces.modelos import (
    PedidoExterno,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
)
from core.marketplaces.repositorios import RepositorioPedidosExternos
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.servicos import registrar_novo_pedido
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import ConsumidorEventosCoreSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy

from .modelos_orm import PedidoExternoMarketplaceORM


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RepositorioPedidosExternosSQLAlchemy(RepositorioPedidosExternos):
    """Repositório implicitamente escopado; o protocolo legado não recebe tenant/unidade."""

    def __init__(self, session: Session, *, tenant_id: str, unidade_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._unidade_id = unidade_id

    def obter(self, *, integracao_id: str, id_externo: str) -> PedidoExterno | None:
        row = self._session.get(
            PedidoExternoMarketplaceORM,
            (self._tenant_id, self._unidade_id, integracao_id, id_externo),
        )
        return self._dominio(row) if row else None

    def salvar(self, pedido: PedidoExterno) -> PedidoExterno:
        row = self._session.get(
            PedidoExternoMarketplaceORM,
            (
                self._tenant_id,
                self._unidade_id,
                pedido.integracao_id,
                pedido.id_externo,
            ),
        )
        dados = {
            "pedido_id": pedido.pedido_id,
            "status_externo": pedido.status_externo.value,
            "status_interno": pedido.status_interno,
            "payload_hash": pedido.payload_hash,
            "recebido_em": pedido.recebido_em,
            "ultima_ocorrencia_em": pedido.ultima_ocorrencia_em,
            "ultimo_evento_id": pedido.ultimo_evento_id,
            "versao_externa": pedido.versao_externa,
        }
        if row is None:
            row = PedidoExternoMarketplaceORM(
                tenant_id=self._tenant_id,
                unidade_id=self._unidade_id,
                integracao_id=pedido.integracao_id,
                id_externo=pedido.id_externo,
                **dados,
            )
            self._session.add(row)
        else:
            for key, value in dados.items():
                setattr(row, key, value)
        self._session.flush()
        return pedido

    def listar_integracao(self, integracao_id: str) -> tuple[PedidoExterno, ...]:
        rows = self._session.scalars(
            select(PedidoExternoMarketplaceORM)
            .where(
                PedidoExternoMarketplaceORM.tenant_id == self._tenant_id,
                PedidoExternoMarketplaceORM.unidade_id == self._unidade_id,
                PedidoExternoMarketplaceORM.integracao_id == integracao_id,
            )
            .order_by(PedidoExternoMarketplaceORM.ultima_ocorrencia_em.desc())
        ).all()
        return tuple(self._dominio(row) for row in rows)

    @staticmethod
    def _dominio(row: PedidoExternoMarketplaceORM) -> PedidoExterno:
        return PedidoExterno(
            integracao_id=row.integracao_id,
            id_externo=row.id_externo,
            pedido_id=row.pedido_id,
            status_externo=StatusPedidoExterno(row.status_externo),
            status_interno=row.status_interno,
            payload_hash=row.payload_hash,
            recebido_em=_utc(row.recebido_em),
            ultima_ocorrencia_em=_utc(row.ultima_ocorrencia_em),
            ultimo_evento_id=row.ultimo_evento_id,
            versao_externa=row.versao_externa,
        )


class PedidosInternosMarketplaceSQLAlchemy:
    """Porta Marketplace -> Pedido V1. Não possui máquina de estados própria."""

    def __init__(
        self,
        session: Session,
        *,
        plataforma: PlataformaMarketplace,
    ) -> None:
        self._session = session
        self._plataforma = plataforma
        self._pedidos = RepositorioPedidosSQLAlchemy(session)
        self._auditoria = RepositorioAuditoriaSQLAlchemy(session)
        self._outbox = RepositorioOutboxSQLAlchemy(
            session,
            ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir,
        )

    @staticmethod
    def _id(prefix: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}-{digest}"

    def _contexto(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        idempotency_key: str,
    ) -> ContextoExecucao:
        return ContextoExecucao.sistema(
            identidade=f"marketplace:{self._plataforma.value}",
            motivo="sincronizacao de pedido externo homologado",
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            correlation_id=self._id("mkt-corr", idempotency_key),
            solicitado_em=datetime.now(timezone.utc),
        )

    def criar_ou_obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> tuple[str, bool]:
        del integracao_id
        tenant = TenantId(tenant_id)
        unidade = UnidadeId(unidade_id)
        chave = IdempotencyKey(idempotency_key)
        existente = self._pedidos.buscar_por_idempotencia(tenant, unidade, chave)
        if existente is not None:
            return str(existente.id), True

        itens: list[ItemPedido] = []
        subtotal = Decimal("0")
        for item in snapshot.itens:
            quantidade_decimal = Decimal(item.quantidade)
            if quantidade_decimal != quantidade_decimal.to_integral_value():
                raise ErroMarketplace("quantidade_fracionaria_nao_suportada")
            quantidade = int(quantidade_decimal)
            subtotal_item = item.preco_unitario * quantidade_decimal
            subtotal += subtotal_item
            item_key = f"{snapshot.id_externo}:{item.item_id_externo}"
            itens.append(
                ItemPedido(
                    id=PedidoItemId(self._id("mkt-item", item_key)),
                    tenant_id=tenant,
                    unidade_id=unidade,
                    produto_id=None,
                    nome_produto=item.nome,
                    quantidade=QuantidadeItem(quantidade),
                    preco_unitario=Dinheiro(item.preco_unitario),
                    subtotal=Dinheiro(subtotal_item),
                )
            )

        total = Decimal(snapshot.total)
        descontos = max(subtotal - total, Decimal("0"))
        taxas = max(total - subtotal, Decimal("0"))
        origem = {
            PlataformaMarketplace.IFOOD: OrigemPedido.IFOOD,
            PlataformaMarketplace.FOOD99: OrigemPedido.FOOD99,
            PlataformaMarketplace.KEETA: OrigemPedido.KEETA,
        }[self._plataforma]
        canal = {
            PlataformaMarketplace.IFOOD: CanalAtendimento.IFOOD,
            PlataformaMarketplace.FOOD99: CanalAtendimento.FOOD99,
            PlataformaMarketplace.KEETA: CanalAtendimento.KEETA,
        }[self._plataforma]
        agora = datetime.now(timezone.utc)
        pedido = Pedido.novo(
            id=PedidoId(self._id("mkt-ped", f"{tenant_id}:{unidade_id}:{idempotency_key}")),
            tenant_id=tenant,
            unidade_id=unidade,
            origem=origem,
            canal=canal,
            status=PedidoStatus.RASCUNHO,
            cliente_id=None,
            criado_em=agora,
            atualizado_em=agora,
            versao=1,
            correlation_id=CorrelationId(self._id("mkt-corr", idempotency_key)),
            idempotency_key=chave,
            subtotal=Dinheiro(subtotal),
            descontos=Dinheiro(descontos),
            taxas=Dinheiro(taxas),
            total=Dinheiro(total),
            itens=tuple(itens),
        )
        resultado = registrar_novo_pedido(
            pedido=pedido,
            contexto=self._contexto(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                idempotency_key=idempotency_key,
            ),
            repositorio=self._pedidos,
            outbox=self._outbox,
            auditoria=self._auditoria,
        )
        return str(resultado.pedido.id), resultado.idempotente

    def _transicionar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        destino: str,
        idempotency_key: str,
        precondicoes: dict[str, bool],
        motivo: str | None = None,
    ) -> str:
        atual = self._pedidos.buscar(
            TenantId(tenant_id),
            UnidadeId(unidade_id),
            PedidoId(pedido_id),
        )
        if atual is None:
            raise ErroMarketplace("pedido_interno_nao_encontrado")
        if atual.status.value == destino:
            return atual.status.value
        resultado = ServicoComandosCentral(self._session).transicionar(
            contexto=self._contexto(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                idempotency_key=idempotency_key,
            ),
            pedido_id=pedido_id,
            destino=destino,
            versao_esperada=atual.versao,
            idempotency_key=idempotency_key,
            precondicoes=precondicoes,
            motivo=motivo,
            metadata={"origem": "marketplace", "plataforma": self._plataforma.value},
        )
        return resultado.status.value

    def atualizar_status_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> str:
        atual = self._pedidos.buscar(
            TenantId(tenant_id), UnidadeId(unidade_id), PedidoId(pedido_id)
        )
        if atual is None:
            raise ErroMarketplace("pedido_interno_nao_encontrado")

        if status in {StatusPedidoExterno.RECEBIDO, StatusPedidoExterno.CONFIRMADO}:
            if atual.status is PedidoStatus.RASCUNHO:
                self._transicionar(
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    pedido_id=pedido_id,
                    destino=PedidoStatus.AGUARDANDO_CONFIRMACAO.value,
                    idempotency_key=f"{idempotency_key}:recebido",
                    precondicoes={"itens_validos": True, "precos_calculados": True},
                )
                atual = self._pedidos.buscar(
                    TenantId(tenant_id), UnidadeId(unidade_id), PedidoId(pedido_id)
                )
                if atual is None:
                    raise ErroMarketplace("pedido_interno_nao_encontrado")
            if (
                status is StatusPedidoExterno.CONFIRMADO
                and atual.status is PedidoStatus.AGUARDANDO_CONFIRMACAO
            ):
                return self._transicionar(
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    pedido_id=pedido_id,
                    destino=PedidoStatus.CONFIRMADO.value,
                    idempotency_key=f"{idempotency_key}:confirmado",
                    precondicoes={"dados_confirmados": True},
                )

        if status is StatusPedidoExterno.CANCELADO and atual.status not in {
            PedidoStatus.CONCLUIDO,
            PedidoStatus.CANCELADO,
        }:
            return self._transicionar(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                pedido_id=pedido_id,
                destino=PedidoStatus.CANCELADO.value,
                idempotency_key=f"{idempotency_key}:cancelado",
                precondicoes={},
                motivo="cancelamento confirmado pelo marketplace",
            )

        atual = self._pedidos.buscar(
            TenantId(tenant_id), UnidadeId(unidade_id), PedidoId(pedido_id)
        )
        if atual is None:
            raise ErroMarketplace("pedido_interno_nao_encontrado")
        return atual.status.value

    def reconciliar_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido: PedidoExterno,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> str:
        return self.atualizar_status_marketplace(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            pedido_id=pedido.pedido_id,
            status=snapshot.status,
            idempotency_key=idempotency_key,
        )
