"""Casos de uso do KDS V1: roteamento, fila, SLA e transicoes normativas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from json import dumps
from typing import Mapping
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from core.estados import ComandoTransicao, ErroTransicao, SnapshotEstado, transicionar
from core.seguranca import AutorizarAcao, ContextoExecucao, Permissao
from core.seguranca.auditoria import RepositorioAuditoria

from .adaptador_sqlalchemy import RepositorioKDSSQLAlchemy
from .erros import ErroKDS
from .modelos import (
    EstadoSLA,
    FilaKDS,
    IndicadorSLA,
    ItemFilaKDS,
    ProducaoItem,
    SetorProducao,
)
from .observabilidade import ColetorMetricasKDS


@dataclass(frozen=True)
class ConfiguracaoSLAKDS:
    limiar_atencao: float = 0.80
    pausa_suspende_sla: bool = True

    def __post_init__(self) -> None:
        if not 0 < self.limiar_atencao < 1:
            raise ValueError("limiar_sla_invalido")


@dataclass(frozen=True)
class ResultadoComandoKDS:
    item: ProducaoItem
    idempotente: bool = False


class CacheFilaKDS:
    """Ultima leitura boa para degradacao offline somente leitura."""

    def __init__(self) -> None:
        self._filas: dict[tuple[str, str, str], FilaKDS] = {}

    @staticmethod
    def _chave(tenant_id: str, unidade_id: str, setor_id: str | None) -> tuple[str, str, str]:
        return tenant_id, unidade_id, setor_id or "*"

    def guardar(
        self, tenant_id: str, unidade_id: str, setor_id: str | None, fila: FilaKDS
    ) -> None:
        self._filas[self._chave(tenant_id, unidade_id, setor_id)] = fila

    def obter(
        self, tenant_id: str, unidade_id: str, setor_id: str | None
    ) -> FilaKDS | None:
        return self._filas.get(self._chave(tenant_id, unidade_id, setor_id))


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _autorizar(
    contexto: ContextoExecucao,
    permissao: Permissao,
    recurso: str,
    recurso_id: str | None = None,
) -> None:
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=permissao,
        recurso=recurso,
        recurso_id=recurso_id,
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise ErroKDS(decisao.codigo)


def calcular_sla(
    item: ProducaoItem,
    setor: SetorProducao,
    agora: datetime,
    configuracao: ConfiguracaoSLAKDS = ConfiguracaoSLAKDS(),
) -> IndicadorSLA:
    if agora.tzinfo is None:
        raise ValueError("timestamp_invalido")
    agora = agora.astimezone(timezone.utc)
    if setor.sla_segundos is None:
        return IndicadorSLA(EstadoSLA.SEM_SLA, 0, None, None)

    decorrido = max(0, int((agora - item.criado_em).total_seconds()))
    pausa = item.pausa_acumulada_segundos
    if (
        configuracao.pausa_suspende_sla
        and item.status == "pausada"
        and item.pausa_iniciada_em is not None
    ):
        pausa += max(0, int((agora - item.pausa_iniciada_em).total_seconds()))
    if configuracao.pausa_suspende_sla:
        decorrido = max(0, decorrido - pausa)

    restante = setor.sla_segundos - decorrido
    percentual = decorrido / setor.sla_segundos
    estado = (
        EstadoSLA.ESTOURADO
        if restante < 0
        else EstadoSLA.ATENCAO
        if percentual >= configuracao.limiar_atencao
        else EstadoSLA.DENTRO
    )
    return IndicadorSLA(estado, decorrido, restante, percentual)


class ServicoKDS:
    def __init__(
        self,
        repositorio: RepositorioKDSSQLAlchemy,
        auditoria: RepositorioAuditoria,
        *,
        cache: CacheFilaKDS | None = None,
        metricas: ColetorMetricasKDS | None = None,
        agora=_agora_utc,
        configuracao_sla: ConfiguracaoSLAKDS = ConfiguracaoSLAKDS(),
    ) -> None:
        self.repositorio = repositorio
        self.auditoria = auditoria
        self.cache = cache or CacheFilaKDS()
        self.metricas = metricas or ColetorMetricasKDS()
        self.agora = agora
        self.configuracao_sla = configuracao_sla

    def criar_setor(
        self,
        contexto: ContextoExecucao,
        *,
        codigo: str,
        nome: str,
        ordem: int = 0,
        sla_segundos: int | None = None,
        setor_id: str | None = None,
    ) -> SetorProducao:
        _autorizar(contexto, Permissao.CONFIGURACAO_ALTERAR, "setor_producao")
        instante = self.agora().astimezone(timezone.utc)
        setor = SetorProducao(
            setor_id=setor_id or str(uuid4()),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            codigo=codigo.strip(),
            nome=nome.strip(),
            ordem=ordem,
            sla_segundos=sla_segundos,
            ativo=True,
            criado_em=instante,
            atualizado_em=instante,
        )
        criado = self.repositorio.criar_setor(setor)
        self.metricas.incrementar("kds_setor_criado")
        return criado

    def listar_setores(self, contexto: ContextoExecucao) -> tuple[SetorProducao, ...]:
        _autorizar(contexto, Permissao.PRODUCAO_VISUALIZAR, "kds")
        return self.repositorio.listar_setores(contexto.tenant_id, contexto.unidade_id)

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
    ) -> ProducaoItem:
        _autorizar(contexto, Permissao.PRODUCAO_ATUALIZAR, "producao")
        if not idempotency_key.strip():
            raise ErroKDS("idempotency_key_obrigatoria")
        payload = {
            "pedido_id": pedido_id,
            "pedido_item_id": pedido_item_id,
            "setor_id": setor_id,
            "quantidade": str(quantidade),
            "prioridade": prioridade,
            "tentativa": tentativa,
        }
        request_hash = sha256(
            dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        instante = self.agora().astimezone(timezone.utc)
        producao = ProducaoItem(
            producao_id=producao_id or str(uuid4()),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            pedido_id=pedido_id,
            pedido_item_id=pedido_item_id,
            setor_id=setor_id,
            status="aguardando",
            prioridade=prioridade,
            quantidade=quantidade,
            tentativa=tentativa,
            versao=1,
            criado_em=instante,
            atualizado_em=instante,
        )
        roteado = self.repositorio.rotear(
            producao,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        self.metricas.incrementar("kds_item_roteado")
        return roteado

    def listar_fila(
        self, contexto: ContextoExecucao, *, setor_id: str | None = None
    ) -> FilaKDS:
        _autorizar(contexto, Permissao.PRODUCAO_VISUALIZAR, "kds")
        instante = self.agora().astimezone(timezone.utc)
        pares = self.repositorio.listar_fila(
            contexto.tenant_id, contexto.unidade_id, setor_id=setor_id
        )
        fila = FilaKDS(
            tuple(
                ItemFilaKDS(
                    producao=item,
                    setor=setor,
                    sla=calcular_sla(item, setor, instante, self.configuracao_sla),
                )
                for item, setor in pares
            ),
            atualizado_em=instante,
        )
        self.cache.guardar(contexto.tenant_id, contexto.unidade_id, setor_id, fila)
        self.metricas.incrementar("kds_fila_leitura")
        self.metricas.incrementar("kds_fila_itens", len(fila.itens))
        return fila

    def listar_fila_tolerante(
        self, contexto: ContextoExecucao, *, setor_id: str | None = None
    ) -> FilaKDS:
        try:
            return self.listar_fila(contexto, setor_id=setor_id)
        except SQLAlchemyError:
            self.metricas.incrementar("kds_modo_degradado")
            anterior = self.cache.obter(
                contexto.tenant_id, contexto.unidade_id, setor_id
            )
            return FilaKDS(
                itens=anterior.itens if anterior else (),
                atualizado_em=self.agora().astimezone(timezone.utc),
                degradado=True,
                somente_leitura=True,
                motivo_degradacao="persistencia_indisponivel",
            )

    @staticmethod
    def _validar_precondicoes(
        atual: ProducaoItem,
        destino: str,
        precondicoes: Mapping[str, bool],
        motivo: str | None,
    ) -> None:
        exigidas: tuple[str, ...] = ()
        if destino == "aceita":
            exigidas = ("setor_correto",)
        elif destino == "em_preparo" and atual.status == "pausada":
            exigidas = ("impedimento_resolvido",)
        elif destino == "em_preparo":
            exigidas = ("estoque_resolvido", "estacao_apta")
        elif destino == "pronta":
            exigidas = ("quantidade_concluida", "checklist_concluido")
        elif destino == "retirada":
            exigidas = ("conferencia_realizada", "posse_transferida")
        for nome in exigidas:
            if not precondicoes.get(nome):
                raise ErroKDS("precondicao_nao_atendida", nome)
        if destino in {"pausada", "cancelada"} and not (motivo or "").strip():
            raise ErroKDS("motivo_obrigatorio")

    def transicionar(
        self,
        contexto: ContextoExecucao,
        *,
        producao_id: str,
        destino: str,
        versao_esperada: int,
        idempotency_key: str,
        precondicoes: Mapping[str, bool] | None = None,
        motivo: str | None = None,
    ) -> ResultadoComandoKDS:
        if not idempotency_key.strip():
            raise ErroKDS("idempotency_key_obrigatoria")
        atual = self.repositorio.obter_producao(
            contexto.tenant_id, contexto.unidade_id, producao_id
        )
        if atual is None:
            raise ErroKDS("producao_indisponivel")
        precondicoes_efetivas = dict(precondicoes or {})
        self._validar_precondicoes(
            atual, destino, precondicoes_efetivas, motivo
        )
        fingerprint = sha256(
            dumps(
                {
                    "producao_id": producao_id,
                    "destino": destino,
                    "versao": versao_esperada,
                    "motivo": motivo,
                    "precondicoes": sorted(precondicoes_efetivas.items()),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        repetido = self.repositorio.evento_por_chave(
            contexto.tenant_id, contexto.unidade_id, idempotency_key
        )
        if repetido is not None:
            if (
                repetido.producao_item_id != producao_id
                or repetido.payload.get("_kds_fingerprint") != fingerprint
            ):
                raise ErroKDS("conflito_idempotencia")
            atual_repetido = self.repositorio.obter_producao(
                contexto.tenant_id, contexto.unidade_id, producao_id
            )
            if atual_repetido is None:
                raise ErroKDS("producao_indisponivel")
            return ResultadoComandoKDS(atual_repetido, True)

        instante = self.agora().astimezone(timezone.utc)
        try:
            resultado = transicionar(
                SnapshotEstado(
                    "producao",
                    atual.producao_id,
                    atual.tenant_id,
                    atual.unidade_id,
                    atual.status,
                    atual.versao,
                ),
                ComandoTransicao(
                    destino=destino,
                    versao_esperada=versao_esperada,
                    idempotency_key=idempotency_key,
                    timestamp=instante,
                    contexto=contexto,
                    precondicoes=precondicoes_efetivas,
                    motivo=motivo,
                    metadata={"setor_id": atual.setor_id},
                ),
            )
        except ErroTransicao as exc:
            raise ErroKDS(exc.codigo) from exc

        payload = dict(resultado.evento.payload)
        payload.update(
            {
                "_kds_fingerprint": fingerprint,
                "status_anterior": atual.status,
                "status_resultante": destino,
            }
        )
        try:
            novo = self.repositorio.aplicar_transicao(
                atual=atual,
                destino=destino,
                instante=instante,
                responsavel_id=contexto.usuario_id,
                event_id=resultado.evento.event_id,
                event_type=resultado.evento.event_type,
                correlation_id=contexto.correlation_id,
                causation_id=contexto.causation_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        except SQLAlchemyError as exc:
            self.metricas.incrementar("kds_escrita_indisponivel")
            raise ErroKDS("kds_offline_somente_leitura") from exc
        self.auditoria.adicionar(resultado.auditoria)
        self.metricas.incrementar(f"kds_transicao_{destino}")
        return ResultadoComandoKDS(novo)
