"""Suporte transacional do KDS canônico V1."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from core.dominio.enums import PedidoStatus
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.kds.erros import ErroKDS
from core.kds.modelos import ProducaoItem
from core.pedidos.servicos import transicionar_pedido
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

from .kds_decisao import decidir_cozinha


def contexto_sistema_kds(contexto: ContextoExecucao, *, motivo: str, instante: datetime) -> ContextoExecucao:
    tecnico = ContextoExecucao.sistema(identidade="kds-orquestrador-v1", motivo=motivo, tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id, correlation_id=contexto.correlation_id, solicitado_em=instante)
    return replace(tecnico, permissoes=frozenset({Permissao.PEDIDO_ALTERAR}))


def precondicoes_pedido_kds(destino: PedidoStatus) -> dict[str, bool]:
    mapa = {PedidoStatus.ENVIADO_PRODUCAO: {"itens_roteados": True}, PedidoStatus.EM_PREPARO: {"producao_iniciada": True}, PedidoStatus.PRONTO: {"itens_resolvidos": True}}
    try:
        return mapa[destino]
    except KeyError as exc:
        raise ErroKDS("transicao_pedido_derivada_nao_suportada") from exc


def transicionar_pedido_por_kds(*, session, pedido_repo, outbox, auditoria, contexto: ContextoExecucao, pedido, destino: PedidoStatus, chave: str, instante: datetime, motivo: str):
    if pedido.status is destino:
        return pedido
    decisao = None
    metadata: dict[str, object] = {"origem_derivada": "kds"}
    if destino is PedidoStatus.ENVIADO_PRODUCAO:
        decisao = decidir_cozinha(session, contexto.tenant_id, contexto.unidade_id, str(pedido.id), instante)
        metadata.update({"decisao_cozinha": decisao.codigo_decisao.value, "risco_cozinha": decisao.risco.value})
    resultado = transicionar_pedido(tenant_id=pedido.tenant_id, unidade_id=pedido.unidade_id, pedido_id=pedido.id, destino=destino, versao_esperada=pedido.versao, idempotency_key=IdempotencyKey(chave), contexto=contexto_sistema_kds(contexto, motivo=motivo, instante=instante), repositorio=pedido_repo, outbox=outbox, auditoria=auditoria, timestamp=instante, precondicoes=precondicoes_pedido_kds(destino), motivo=motivo, decisao_cozinha=decisao, metadata=metadata)
    return resultado.pedido


def publicar_evento_kds(*, outbox, contexto: ContextoExecucao, item: ProducaoItem, event_type: str, chave: str, instante: datetime, payload: dict[str, object]) -> None:
    tenant, unidade, idem = TenantId(contexto.tenant_id), UnidadeId(contexto.unidade_id), IdempotencyKey(chave)
    existente = outbox.consultar(tenant_id=tenant, unidade_id=unidade, idempotency_key=idem)
    if existente is not None:
        if existente.aggregate_id != item.producao_id or existente.event_type != event_type:
            raise ErroKDS("conflito_evento_core")
        return
    outbox.adicionar(EnvelopeMensagem(event_id=EventoId(str(uuid5(NAMESPACE_URL, f"{contexto.tenant_id}:{contexto.unidade_id}:{chave}"))), event_type=event_type, aggregate_id=item.producao_id, aggregate_type="producao", tenant_id=tenant, unidade_id=unidade, correlation_id=CorrelationId(contexto.correlation_id), causation_id=None, idempotency_key=idem, occurred_at=instante, payload=payload, version=item.versao))


def auditar_roteamento_kds(*, auditoria, contexto: ContextoExecucao, item: ProducaoItem, instante: datetime) -> None:
    papel = next(iter(sorted(contexto.papeis, key=str)), None)
    auditoria.adicionar(EventoAuditoria(audit_id=str(uuid4()), tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id, usuario_id=contexto.usuario_id, papel_efetivo=papel, acao="producao.rotear", recurso_tipo="producao", recurso_id=item.producao_id, resultado="permitido", motivo="roteamento_kds_canonico", correlation_id=contexto.correlation_id, timestamp=instante, origem=contexto.origem, politica="producao_atualizar", causation_id=contexto.causation_id, depois_resumido=(("estado", item.status), ("setor_id", item.setor_id)), metadata=sanitizar_metadata({"pedido_id": item.pedido_id, "pedido_item_id": item.pedido_item_id})))
