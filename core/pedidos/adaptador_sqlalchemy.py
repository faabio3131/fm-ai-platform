"""Adapter SQLAlchemy transacional e sempre escopado por tenant/unidade."""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.erros import ConflitoIdempotencia
from core.dominio.eventos import EventoDominio
from core.dominio.ids import (
    ClienteId,
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import (
    AdicionalItemPedido,
    ItemPedido,
    ObservacaoPedido,
    Pedido,
)
from core.dominio.serializacao import para_primitivo
from core.dominio.tipos import QuantidadeItem

from .erros import EscopoPedidoInvalido, PedidoConcorrente
from .modelos_orm import (
    AdicionalItemPedidoORM,
    EventoPedidoPersistidoORM,
    ItemPedidoORM,
    ObservacaoPedidoORM,
    PedidoORM,
)


def _hash(pedido: Pedido) -> str:
    dados = pedido.para_dict()
    for campo in ("id", "criado_em", "atualizado_em", "versao"):
        dados.pop(campo, None)
    return hashlib.sha256(
        json.dumps(dados, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _dinheiro(valor: object) -> Dinheiro:
    return Dinheiro(Decimal(str(valor)))


def _utc(valor: object) -> datetime:
    instante = (
        valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    )
    return (
        instante.replace(tzinfo=timezone.utc) if instante.tzinfo is None else instante
    )


def _para_dominio(row: PedidoORM) -> Pedido:
    itens = tuple(
        ItemPedido(
            id=PedidoItemId(i.id),
            tenant_id=TenantId(i.tenant_id),
            unidade_id=UnidadeId(i.unidade_id),
            produto_id=ProdutoId(i.produto_id) if i.produto_id else None,
            nome_produto=i.nome_produto,
            quantidade=QuantidadeItem(i.quantidade),
            preco_unitario=_dinheiro(i.preco_unitario),
            subtotal=_dinheiro(i.subtotal),
            observacao=i.observacao,
            ficha_versao=i.ficha_versao,
            adicionais=tuple(
                AdicionalItemPedido(
                    id=a.id,
                    tenant_id=TenantId(a.tenant_id),
                    unidade_id=UnidadeId(a.unidade_id),
                    nome=a.nome,
                    quantidade=QuantidadeItem(a.quantidade),
                    preco_unitario=_dinheiro(a.preco_unitario),
                    subtotal=_dinheiro(a.subtotal),
                )
                for a in i.adicionais
            ),
        )
        for i in row.itens
    )
    return Pedido(
        id=PedidoId(row.id),
        tenant_id=TenantId(row.tenant_id),
        unidade_id=UnidadeId(row.unidade_id),
        origem=OrigemPedido(row.origem),
        canal=CanalAtendimento(row.canal),
        status=PedidoStatus(row.status),
        cliente_id=ClienteId(row.cliente_id) if row.cliente_id else None,
        criado_em=_utc(row.criado_em),
        atualizado_em=_utc(row.atualizado_em),
        versao=row.versao,
        correlation_id=CorrelationId(row.correlation_id),
        idempotency_key=IdempotencyKey(row.idempotency_key),
        subtotal=_dinheiro(row.subtotal),
        descontos=_dinheiro(row.descontos),
        taxas=_dinheiro(row.taxas),
        total=_dinheiro(row.total),
        itens=itens,
        observacoes=tuple(
            ObservacaoPedido(
                id=o.id,
                tenant_id=TenantId(o.tenant_id),
                unidade_id=UnidadeId(o.unidade_id),
                texto=o.texto,
                criado_em=_utc(o.criado_em),
            )
            for o in row.observacoes
        ),
    )


class RepositorioPedidosSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _stmt(self, tenant_id: TenantId, unidade_id: UnidadeId):
        return select(PedidoORM).where(
            PedidoORM.tenant_id == str(tenant_id),
            PedidoORM.unidade_id == str(unidade_id),
        )

    def buscar(
        self, tenant_id: TenantId, unidade_id: UnidadeId, pedido_id: PedidoId
    ) -> Pedido | None:
        row = self._session.scalar(
            self._stmt(tenant_id, unidade_id).where(PedidoORM.id == str(pedido_id))
        )
        return _para_dominio(row) if row else None

    def listar(self, tenant_id: TenantId, unidade_id: UnidadeId) -> tuple[Pedido, ...]:
        rows = self._session.scalars(
            self._stmt(tenant_id, unidade_id).order_by(
                PedidoORM.criado_em, PedidoORM.id
            )
        ).all()
        return tuple(_para_dominio(row) for row in rows)

    def buscar_por_idempotencia(
        self, tenant_id: TenantId, unidade_id: UnidadeId, chave: IdempotencyKey
    ) -> Pedido | None:
        row = self._session.scalar(
            self._stmt(tenant_id, unidade_id).where(
                PedidoORM.idempotency_key == str(chave)
            )
        )
        return _para_dominio(row) if row else None

    def obter_versao(
        self, tenant_id: TenantId, unidade_id: UnidadeId, pedido_id: PedidoId
    ) -> int | None:
        return self._session.scalar(
            select(PedidoORM.versao).where(
                PedidoORM.tenant_id == str(tenant_id),
                PedidoORM.unidade_id == str(unidade_id),
                PedidoORM.id == str(pedido_id),
            )
        )

    def salvar(self, pedido: Pedido, *, versao_esperada: int | None = None) -> Pedido:
        atual = self.buscar(pedido.tenant_id, pedido.unidade_id, pedido.id)
        if atual is None:
            if pedido.status is not PedidoStatus.RASCUNHO:
                raise EscopoPedidoInvalido("Pedido novo deve comecar em rascunho")
            existente_chave = self._session.scalar(
                self._stmt(pedido.tenant_id, pedido.unidade_id).where(
                    PedidoORM.idempotency_key == str(pedido.idempotency_key)
                )
            )
            if existente_chave:
                if existente_chave.request_hash == _hash(pedido):
                    return _para_dominio(existente_chave)
                raise ConflitoIdempotencia(
                    "idempotency_key reutilizada com conteudo diferente"
                )
            if versao_esperada not in (None, 0):
                raise PedidoConcorrente("pedido_concorrente")
            row = PedidoORM(
                id=str(pedido.id),
                tenant_id=str(pedido.tenant_id),
                unidade_id=str(pedido.unidade_id),
                origem=pedido.origem.value,
                canal=pedido.canal.value,
                status=pedido.status.value,
                cliente_id=str(pedido.cliente_id) if pedido.cliente_id else None,
                criado_em=pedido.criado_em,
                atualizado_em=pedido.atualizado_em,
                versao=pedido.versao,
                correlation_id=str(pedido.correlation_id),
                idempotency_key=str(pedido.idempotency_key),
                request_hash=_hash(pedido),
                subtotal=pedido.subtotal.valor,
                descontos=pedido.descontos.valor,
                taxas=pedido.taxas.valor,
                total=pedido.total.valor,
            )
            row.itens = [
                ItemPedidoORM(
                    id=str(i.id),
                    tenant_id=str(i.tenant_id),
                    unidade_id=str(i.unidade_id),
                    pedido_id=str(pedido.id),
                    ordem=n,
                    produto_id=str(i.produto_id) if i.produto_id else None,
                    nome_produto=i.nome_produto,
                    quantidade=i.quantidade.valor,
                    preco_unitario=i.preco_unitario.valor,
                    subtotal=i.subtotal.valor,
                    observacao=i.observacao,
                    ficha_versao=i.ficha_versao,
                    adicionais=[
                        AdicionalItemPedidoORM(
                            id=a.id,
                            tenant_id=str(a.tenant_id),
                            unidade_id=str(a.unidade_id),
                            item_id=str(i.id),
                            ordem=m,
                            nome=a.nome,
                            quantidade=a.quantidade.valor,
                            preco_unitario=a.preco_unitario.valor,
                            subtotal=a.subtotal.valor,
                        )
                        for m, a in enumerate(i.adicionais)
                    ],
                )
                for n, i in enumerate(pedido.itens)
            ]
            row.observacoes = [
                ObservacaoPedidoORM(
                    id=o.id,
                    tenant_id=str(o.tenant_id),
                    unidade_id=str(o.unidade_id),
                    pedido_id=str(pedido.id),
                    ordem=n,
                    texto=o.texto,
                    criado_em=o.criado_em,
                )
                for n, o in enumerate(pedido.observacoes)
            ]
            self._session.add(row)
            try:
                self._session.flush()
            except IntegrityError as exc:
                raise ConflitoIdempotencia(
                    "conflito de idempotencia ou identidade"
                ) from exc
            return _para_dominio(row)
        row_atual = self._session.scalar(
            self._stmt(pedido.tenant_id, pedido.unidade_id).where(
                PedidoORM.id == str(pedido.id)
            )
        )
        if (
            row_atual is not None
            and row_atual.versao == pedido.versao
            and row_atual.idempotency_key == str(pedido.idempotency_key)
            and row_atual.request_hash == _hash(pedido)
        ):
            return atual
        if atual.tenant_id != pedido.tenant_id or atual.unidade_id != pedido.unidade_id:
            raise EscopoPedidoInvalido("escopo_pedido_invalido")
        esperada = versao_esperada if versao_esperada is not None else pedido.versao - 1
        resultado = self._session.execute(
            update(PedidoORM)
            .where(
                PedidoORM.tenant_id == str(pedido.tenant_id),
                PedidoORM.unidade_id == str(pedido.unidade_id),
                PedidoORM.id == str(pedido.id),
                PedidoORM.versao == esperada,
            )
            .values(
                status=pedido.status.value,
                atualizado_em=pedido.atualizado_em,
                versao=pedido.versao,
                subtotal=pedido.subtotal.valor,
                descontos=pedido.descontos.valor,
                taxas=pedido.taxas.valor,
                total=pedido.total.valor,
            )
        )
        if not isinstance(resultado, CursorResult) or resultado.rowcount != 1:
            raise PedidoConcorrente("pedido_concorrente")
        self._session.flush()
        return pedido

    def salvar_eventos(
        self,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        pedido_id: PedidoId,
        eventos: tuple[EventoDominio, ...],
    ) -> None:
        if self.buscar(tenant_id, unidade_id, pedido_id) is None:
            raise EscopoPedidoInvalido("Pedido nao pertence ao escopo informado")
        for e in eventos:
            if (
                e.tenant_id != tenant_id
                or e.unidade_id != unidade_id
                or e.aggregate_id != str(pedido_id)
            ):
                raise EscopoPedidoInvalido("Evento fora do escopo do pedido")
            self._session.add(
                EventoPedidoPersistidoORM(
                    event_id=str(e.event_id),
                    tenant_id=str(tenant_id),
                    unidade_id=str(unidade_id),
                    pedido_id=str(pedido_id),
                    event_type=e.event_type,
                    correlation_id=str(e.correlation_id),
                    causation_id=str(e.causation_id) if e.causation_id else None,
                    idempotency_key=str(e.idempotency_key),
                    occurred_at=e.occurred_at,
                    payload=para_primitivo(e.payload),
                    version=e.version,
                )
            )
        self._session.flush()
