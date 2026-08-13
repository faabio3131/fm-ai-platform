"""Casos de uso puros para reserva e movimentos do estoque V1."""

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

from .erros import (
    ConflitoIdempotenciaEstoque,
    OperacaoEstoqueNaoAutorizada,
    ReservaInvalida,
)
from .modelos import (
    MovimentoEstoque,
    ReservaEstoque,
    ResultadoMovimento,
    ResultadoReserva,
    SnapshotFichaEstoque,
    StatusReserva,
    TipoMovimento,
    quantidade,
)
from .repositorios import RepositorioEstoque

PERMISSOES = {
    TipoMovimento.RESERVA: Permissao.ESTOQUE_RESERVAR,
    TipoMovimento.CONSUMO: Permissao.ESTOQUE_BAIXAR,
    TipoMovimento.LIBERACAO_RESERVA: Permissao.ESTOQUE_LIBERAR,
    TipoMovimento.PERDA: Permissao.ESTOQUE_PERDA_REGISTRAR,
    TipoMovimento.AJUSTE_POSITIVO: Permissao.ESTOQUE_AJUSTAR,
    TipoMovimento.AJUSTE_NEGATIVO: Permissao.ESTOQUE_AJUSTAR,
    TipoMovimento.DEVOLUCAO: Permissao.ESTOQUE_DEVOLVER,
    TipoMovimento.COMPENSACAO: Permissao.ESTOQUE_AJUSTAR,
    TipoMovimento.ENTRADA: Permissao.ESTOQUE_AJUSTAR,
}


def _autorizar(contexto: ContextoExecucao, tipo: TipoMovimento) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=PERMISSOES[tipo],
        recurso="estoque",
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise OperacaoEstoqueNaoAutorizada(decisao.codigo)


def _hash_snapshot(snapshot: SnapshotFichaEstoque, pedido_versao: int) -> str:
    dados = [
        (
            i.produto_id,
            i.item_pedido_id,
            i.insumo_id,
            str(i.quantidade_total),
            i.unidade_medida,
        )
        for i in snapshot.itens
    ]
    return hashlib.sha256(
        json.dumps(
            [snapshot.pedido_id, snapshot.versao_ficha, pedido_versao, dados],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _movimento(
    *,
    contexto: ContextoExecucao,
    insumo_id: str,
    tipo: TipoMovimento,
    quantidade_movimento: Decimal,
    unidade_medida: str,
    origem_tipo: str,
    origem_id: str,
    origem_versao: int,
    chave: str,
    motivo: str | None = None,
    metadata: dict[str, Any] | None = None,
    agora: datetime | None = None,
) -> MovimentoEstoque:
    return MovimentoEstoque(
        str(uuid4()),
        contexto.tenant_id,
        contexto.unidade_id,
        insumo_id,
        tipo,
        quantidade_movimento,
        unidade_medida,
        origem_tipo,
        origem_id,
        origem_versao,
        chave,
        agora or datetime.now(timezone.utc),
        contexto.correlation_id,
        contexto.causation_id,
        contexto.usuario_id,
        motivo,
        metadata or {},
    )


def _efeitos(
    contexto: ContextoExecucao,
    movimentos: tuple[MovimentoEstoque, ...],
    evento_tipo: str,
    acao: str,
    motivo: str = "operacao_solicitada",
) -> tuple[tuple[EnvelopeMensagem, ...], tuple[EventoAuditoria, ...]]:
    eventos: list[EnvelopeMensagem] = []
    auditorias: list[EventoAuditoria] = []
    papel = next(iter(sorted(contexto.papeis, key=str)), None)
    for m in movimentos:
        eventos.append(
            EnvelopeMensagem(
                EventoId(str(uuid4())),
                evento_tipo,
                m.origem_id,
                "estoque",
                TenantId(m.tenant_id),
                UnidadeId(m.unidade_id),
                CorrelationId(m.correlation_id),
                CausationId(m.causation_id) if m.causation_id else None,
                IdempotencyKey(m.idempotency_key),
                m.occurred_at,
                {
                    "insumo_id": m.insumo_id,
                    "quantidade": str(m.quantidade),
                    "origem_tipo": m.origem_tipo,
                    "origem_id": m.origem_id,
                },
                1,
            )
        )
        auditorias.append(
            EventoAuditoria(
                str(uuid4()),
                m.tenant_id,
                m.unidade_id,
                contexto.usuario_id,
                papel,
                acao,
                "insumo_estoque",
                m.insumo_id,
                "sucesso",
                motivo,
                m.correlation_id,
                m.occurred_at,
                contexto.origem,
                "estoque_v1",
                metadata=sanitizar_metadata(
                    {"quantidade": str(m.quantidade), "origem_id": m.origem_id}
                ),
            )
        )
    return tuple(eventos), tuple(auditorias)


def reservar_estoque(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioEstoque,
    pedido_id: str,
    pedido_version: int,
    snapshot_ficha: SnapshotFichaEstoque,
    idempotency_key: str,
    versoes_esperadas: dict[str, int] | None = None,
) -> ResultadoReserva:
    _autorizar(contexto, TipoMovimento.RESERVA)
    if snapshot_ficha.pedido_id != pedido_id:
        raise ReservaInvalida("snapshot_fora_do_pedido")
    conteudo = _hash_snapshot(snapshot_ficha, pedido_version)

    def operacao() -> ResultadoReserva:
        existente = repositorio.buscar_reserva(
            contexto.tenant_id, contexto.unidade_id, pedido_id
        )
        if existente:
            if (
                existente.idempotency_key == idempotency_key
                and _hash_snapshot(existente.snapshot, existente.pedido_versao)
                == conteudo
            ):
                movimentos = tuple(
                    m
                    for m in repositorio.por_origem(
                        contexto.tenant_id, contexto.unidade_id, "pedido", pedido_id
                    )
                    if m.tipo_movimento == TipoMovimento.RESERVA
                )
                return ResultadoReserva(
                    movimentos,
                    tuple(
                        repositorio.consultar_saldo(
                            contexto.tenant_id, contexto.unidade_id, m.insumo_id
                        )
                        for m in movimentos
                    ),
                    True,
                    reserva=existente,
                )
            raise ConflitoIdempotenciaEstoque("conflito_idempotencia")
        agregados: dict[tuple[str, str], Decimal] = {}
        for item in snapshot_ficha.itens:
            chave = (item.insumo_id, item.unidade_medida)
            agregados[chave] = agregados.get(chave, Decimal(0)) + item.quantidade_total
        movimentos = tuple(
            _movimento(
                contexto=contexto,
                insumo_id=insumo,
                tipo=TipoMovimento.RESERVA,
                quantidade_movimento=qtd,
                unidade_medida=unidade,
                origem_tipo="pedido",
                origem_id=pedido_id,
                origem_versao=pedido_version,
                chave=idempotency_key,
                metadata={
                    "snapshot_hash": conteudo,
                    "versao_ficha": snapshot_ficha.versao_ficha,
                },
            )
            for (insumo, unidade), qtd in sorted(agregados.items())
        )
        # Uma chave de comando pode produzir N movimentos; sufixos internos preservam idempotencia.
        movimentos = tuple(
            replace(m, idempotency_key=f"{idempotency_key}:{m.insumo_id}")
            if len(movimentos) > 1
            else m
            for m in movimentos
        )
        for m in movimentos:
            repositorio.append(
                m, versao_esperada=(versoes_esperadas or {}).get(m.insumo_id)
            )
        reserva = ReservaEstoque(
            str(uuid4()),
            contexto.tenant_id,
            contexto.unidade_id,
            pedido_id,
            pedido_version,
            snapshot_ficha,
            StatusReserva.ATIVA,
            idempotency_key,
            contexto.solicitado_em,
        )
        repositorio.salvar_reserva(reserva)
        saldos = tuple(
            repositorio.consultar_saldo(
                contexto.tenant_id, contexto.unidade_id, m.insumo_id
            )
            for m in movimentos
        )
        eventos, auditorias = _efeitos(
            contexto, movimentos, "estoque.reservado", "estoque.reservar"
        )
        return ResultadoReserva(movimentos, saldos, False, eventos, auditorias, reserva)

    return repositorio.executar_atomicamente(operacao)


def _resolver_reserva(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioEstoque,
    pedido_id: str,
    pedido_version: int,
    idempotency_key: str,
    tipo: TipoMovimento,
    evento: str,
    motivo: str,
) -> ResultadoMovimento:
    _autorizar(contexto, tipo)

    def operacao() -> ResultadoMovimento:
        existente = tuple(
            m
            for m in repositorio.por_origem(
                contexto.tenant_id, contexto.unidade_id, "pedido", pedido_id
            )
            if m.tipo_movimento == tipo
            and (
                m.idempotency_key == idempotency_key
                or m.idempotency_key.startswith(f"{idempotency_key}:")
            )
        )
        if existente:
            return ResultadoMovimento(
                existente,
                tuple(
                    repositorio.consultar_saldo(
                        contexto.tenant_id, contexto.unidade_id, m.insumo_id
                    )
                    for m in existente
                ),
                True,
            )
        reserva = repositorio.buscar_reserva(
            contexto.tenant_id, contexto.unidade_id, pedido_id
        )
        if reserva is None or reserva.status != StatusReserva.ATIVA:
            raise ReservaInvalida("reserva_indisponivel")
        originais = repositorio.por_origem(
            contexto.tenant_id, contexto.unidade_id, "pedido", pedido_id
        )
        reservas = tuple(
            m for m in originais if m.tipo_movimento == TipoMovimento.RESERVA
        )
        movimentos = tuple(
            _movimento(
                contexto=contexto,
                insumo_id=m.insumo_id,
                tipo=tipo,
                quantidade_movimento=m.quantidade,
                unidade_medida=m.unidade_medida,
                origem_tipo="pedido",
                origem_id=pedido_id,
                origem_versao=pedido_version,
                chave=f"{idempotency_key}:{m.insumo_id}"
                if len(reservas) > 1
                else idempotency_key,
                motivo=motivo,
                metadata={"reserva_id": reserva.reserva_id},
            )
            for m in reservas
        )
        for m in movimentos:
            repositorio.append(m)
        repositorio.salvar_reserva(
            replace(
                reserva,
                status=StatusReserva.CONSUMIDA
                if tipo == TipoMovimento.CONSUMO
                else StatusReserva.LIBERADA,
                resolvida_em=contexto.solicitado_em,
            )
        )
        saldos = tuple(
            repositorio.consultar_saldo(
                contexto.tenant_id, contexto.unidade_id, m.insumo_id
            )
            for m in movimentos
        )
        eventos, auditorias = _efeitos(
            contexto, movimentos, evento, f"estoque.{tipo.value}", motivo
        )
        return ResultadoMovimento(movimentos, saldos, False, eventos, auditorias)

    return repositorio.executar_atomicamente(operacao)


def consumir_reserva(**kwargs: Any) -> ResultadoMovimento:
    return _resolver_reserva(
        tipo=TipoMovimento.CONSUMO,
        evento="estoque.baixado",
        motivo="inicio_producao",
        **kwargs,
    )


def liberar_reserva(*, motivo: str, **kwargs: Any) -> ResultadoMovimento:
    if not motivo.strip():
        raise ValueError("motivo obrigatorio")
    return _resolver_reserva(
        tipo=TipoMovimento.LIBERACAO_RESERVA,
        evento="estoque.liberado",
        motivo=motivo,
        **kwargs,
    )


def registrar_movimento(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioEstoque,
    insumo_id: str,
    tipo: TipoMovimento,
    quantidade_movimento: Decimal | str | int,
    unidade_medida: str,
    origem_tipo: str,
    origem_id: str,
    origem_versao: int,
    idempotency_key: str,
    motivo: str,
    metadata: dict[str, Any] | None = None,
    permitir_negativo: bool = False,
) -> ResultadoMovimento:
    if tipo in {
        TipoMovimento.RESERVA,
        TipoMovimento.CONSUMO,
        TipoMovimento.LIBERACAO_RESERVA,
    }:
        raise ValueError("use o servico especifico")
    if not motivo.strip():
        raise ValueError("motivo obrigatorio")
    _autorizar(contexto, tipo)
    movimento = _movimento(
        contexto=contexto,
        insumo_id=insumo_id,
        tipo=tipo,
        quantidade_movimento=quantidade(quantidade_movimento),
        unidade_medida=unidade_medida,
        origem_tipo=origem_tipo,
        origem_id=origem_id,
        origem_versao=origem_versao,
        chave=idempotency_key,
        motivo=motivo,
        metadata=metadata,
    )
    existente = repositorio.por_idempotencia(
        contexto.tenant_id, contexto.unidade_id, idempotency_key
    )
    if existente:
        if (
            existente[0].chave_logica != movimento.chave_logica
            or existente[0].quantidade != movimento.quantidade
        ):
            raise ConflitoIdempotenciaEstoque("conflito_idempotencia")
        return ResultadoMovimento(
            existente,
            (
                repositorio.consultar_saldo(
                    contexto.tenant_id, contexto.unidade_id, insumo_id
                ),
            ),
            True,
        )
    repositorio.append(movimento, permitir_negativo=permitir_negativo)
    saldo = repositorio.consultar_saldo(
        contexto.tenant_id, contexto.unidade_id, insumo_id
    )
    nomes = {
        TipoMovimento.PERDA: "estoque.perda_registrada",
        TipoMovimento.DEVOLUCAO: "estoque.devolvido",
    }
    evento = nomes.get(tipo, "estoque.ajustado")
    eventos, auditorias = _efeitos(
        contexto, (movimento,), evento, f"estoque.{tipo.value}", motivo
    )
    return ResultadoMovimento((movimento,), (saldo,), False, eventos, auditorias)


def registrar_devolucao(
    *, elegivel: bool, inspecionada: bool, politica_permite: bool, **kwargs: Any
) -> ResultadoMovimento:
    if not (elegivel and inspecionada and politica_permite):
        raise ReservaInvalida("devolucao_nao_elegivel_registre_perda")
    return registrar_movimento(tipo=TipoMovimento.DEVOLUCAO, **kwargs)
