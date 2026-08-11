"""Serviços de aplicação da Expedição e Entrega V1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from core.seguranca import AutorizarAcao, ContextoExecucao, Papel, Permissao

from .adaptador_sqlalchemy import RepositorioEntregaSQLAlchemy
from .erros import ErroEntrega
from .modelos import (
    ChecklistExpedicao,
    Entrega,
    ProvaEntrega,
    StatusEntrega,
    TentativaEntrega,
)

FinanceiroResolvido = Callable[[str, str, str], bool]
PedidoCancelado = Callable[[str, str, str], bool]
Agora = Callable[[], datetime]


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hash_comando(nome: str, ator_id: str, dados: Mapping[str, object]) -> str:
    bruto = json.dumps(
        {"comando": nome, "ator_id": ator_id, "dados": dados},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(bruto).hexdigest()


def _elevado(contexto: ContextoExecucao) -> bool:
    return contexto.identidade_sistema or bool(
        contexto.papeis.intersection({Papel.ADMINISTRADOR, Papel.GERENTE})
    )


def _autorizar_expedicao(contexto: ContextoExecucao, recurso: str) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=Permissao.EXPEDICAO_OPERAR,
        recurso=recurso,
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise ErroEntrega(decisao.codigo)


def _autorizar_entregador(entrega: Entrega, contexto: ContextoExecucao) -> None:
    _autorizar_expedicao(contexto, f"entrega:{entrega.entrega_id}")
    if _elevado(contexto) or Papel.EXPEDICAO in contexto.papeis:
        return
    if Papel.ENTREGADOR not in contexto.papeis:
        raise ErroEntrega("papel_sem_alcada_entrega")
    if entrega.entregador_id != contexto.usuario_id:
        raise ErroEntrega("entrega_fora_alcada")


class ServicoEntrega:
    """Máquina logística com CAS, idempotência, RBAC e limite financeiro."""

    def __init__(
        self,
        repositorio: RepositorioEntregaSQLAlchemy,
        *,
        financeiro_resolvido: FinanceiroResolvido,
        pedido_cancelado: PedidoCancelado,
        agora: Agora = _agora_utc,
    ) -> None:
        self.repositorio = repositorio
        self.financeiro_resolvido = financeiro_resolvido
        self.pedido_cancelado = pedido_cancelado
        self.agora = agora

    def listar(self, contexto: ContextoExecucao) -> tuple[Entrega, ...]:
        _autorizar_expedicao(contexto, "entrega:listar")
        entregas = self.repositorio.listar(contexto.tenant_id, contexto.unidade_id)
        if _elevado(contexto) or Papel.EXPEDICAO in contexto.papeis:
            return entregas
        if Papel.ENTREGADOR in contexto.papeis:
            return tuple(e for e in entregas if e.entregador_id == contexto.usuario_id)
        return ()

    def criar(
        self,
        entrega: Entrega,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        _autorizar_expedicao(contexto, f"entrega:{entrega.entrega_id}")
        self._validar_escopo(entrega, contexto)
        if entrega.status is not StatusEntrega.AGUARDANDO_PRODUCAO or entrega.versao != 1:
            raise ErroEntrega("entrega_nova_invalida")
        dados = {
            "entrega_id": entrega.entrega_id,
            "pedido_id": entrega.pedido_id,
            "endereco_id": entrega.endereco_id,
            "modalidade": entrega.modalidade.value,
        }
        fingerprint = _hash_comando("criar", contexto.usuario_id, dados)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        instante = self._agora()
        criada = self.repositorio.salvar_nova(entrega, atualizado_em=instante)
        self._evento(
            criada,
            contexto=contexto,
            tipo="entrega.criada",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"modalidade": criada.modalidade.value},
        )
        return criada

    def marcar_pedido_pronto(
        self,
        entrega_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        if not contexto.identidade_sistema:
            raise ErroEntrega("transicao_exige_sistema")
        atual = self._obter(entrega_id, contexto)
        fingerprint = self._fingerprint(
            "pedido_pronto", contexto, entrega_id, versao_esperada
        )
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        if atual.status not in {
            StatusEntrega.AGUARDANDO_PRODUCAO,
            StatusEntrega.ATRIBUIDA,
        }:
            raise ErroEntrega("transicao_entrega_invalida")
        instante = self._agora()
        nova = replace(
            atual,
            status=(
                StatusEntrega.AGUARDANDO_EXPEDICAO
                if atual.status is StatusEntrega.AGUARDANDO_PRODUCAO
                else atual.status
            ),
            producao_pronta_em=instante,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.aguardando_expedicao",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"producao_pronta": True},
        )

    def concluir_checklist(
        self,
        entrega_id: str,
        checklist: ChecklistExpedicao,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        _autorizar_expedicao(contexto, f"entrega:{entrega_id}")
        if Papel.ENTREGADOR in contexto.papeis and not _elevado(contexto):
            raise ErroEntrega("checklist_exige_expedicao")
        if not checklist.completo:
            raise ErroEntrega("checklist_incompleto")
        atual = self._obter(entrega_id, contexto)
        dados = {
            "entrega_id": entrega_id,
            "versao_esperada": versao_esperada,
            "itens": checklist.itens_conferidos,
            "embalagem": checklist.embalagem_conferida,
            "identificacao": checklist.identificacao_conferida,
        }
        fingerprint = _hash_comando("checklist", contexto.usuario_id, dados)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        if atual.producao_pronta_em is None:
            raise ErroEntrega("producao_ainda_nao_pronta")
        if atual.status not in {
            StatusEntrega.AGUARDANDO_EXPEDICAO,
            StatusEntrega.ATRIBUIDA,
        }:
            raise ErroEntrega("transicao_entrega_invalida")
        instante = self._agora()
        nova = replace(
            atual,
            status=(
                StatusEntrega.AGUARDANDO_ENTREGADOR
                if atual.status is StatusEntrega.AGUARDANDO_EXPEDICAO
                else atual.status
            ),
            checklist_concluido_em=instante,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.aguardando_entregador",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"checklist_completo": True},
        )

    def atribuir(
        self,
        entrega_id: str,
        entregador_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        _autorizar_expedicao(contexto, f"entrega:{entrega_id}")
        if Papel.ENTREGADOR in contexto.papeis and not _elevado(contexto):
            raise ErroEntrega("atribuicao_exige_expedicao")
        entregador = entregador_id.strip()
        if not entregador:
            raise ErroEntrega("entregador_invalido")
        atual = self._obter(entrega_id, contexto)
        dados = {
            "entrega_id": entrega_id,
            "entregador_id": entregador,
            "versao_esperada": versao_esperada,
        }
        fingerprint = _hash_comando("atribuir", contexto.usuario_id, dados)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        permitidos = {
            StatusEntrega.AGUARDANDO_PRODUCAO,
            StatusEntrega.AGUARDANDO_EXPEDICAO,
            StatusEntrega.AGUARDANDO_ENTREGADOR,
            StatusEntrega.TENTATIVA_FALHOU,
        }
        if atual.status not in permitidos:
            raise ErroEntrega("transicao_entrega_invalida")
        instante = self._agora()
        reatribuicao = atual.status is StatusEntrega.TENTATIVA_FALHOU
        nova = replace(
            atual,
            status=StatusEntrega.ATRIBUIDA,
            entregador_id=entregador,
            atribuida_em=instante,
            tentativa=atual.tentativa + (1 if reatribuicao else 0),
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.reatribuida" if reatribuicao else "entrega.atribuida",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"entregador_id": entregador, "tentativa": nova.tentativa},
        )

    def coletar(
        self,
        entrega_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        atual = self._obter(entrega_id, contexto)
        _autorizar_entregador(atual, contexto)
        fingerprint = self._fingerprint("coletar", contexto, entrega_id, versao_esperada)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        if atual.status is not StatusEntrega.ATRIBUIDA:
            raise ErroEntrega("transicao_entrega_invalida")
        if atual.producao_pronta_em is None or atual.checklist_concluido_em is None:
            raise ErroEntrega("custodia_sem_conferencia")
        instante = self._agora()
        nova = replace(
            atual,
            status=StatusEntrega.COLETADA,
            coletada_em=instante,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.coletada",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"custodia_transferida": True},
        )

    def sair_em_rota(
        self,
        entrega_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        atual = self._obter(entrega_id, contexto)
        _autorizar_entregador(atual, contexto)
        fingerprint = self._fingerprint(
            "sair_em_rota", contexto, entrega_id, versao_esperada
        )
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        if atual.status is not StatusEntrega.COLETADA:
            raise ErroEntrega("transicao_entrega_invalida")
        instante = self._agora()
        nova = replace(
            atual,
            status=StatusEntrega.EM_ROTA,
            saiu_em=instante,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.em_rota",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"tracking_habilitado": False},
        )

    def registrar_tentativa_falha(
        self,
        entrega_id: str,
        motivo: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        atual = self._obter(entrega_id, contexto)
        _autorizar_entregador(atual, contexto)
        tentativa = TentativaEntrega(atual.tentativa, motivo, self._agora())
        dados = {
            "entrega_id": entrega_id,
            "versao_esperada": versao_esperada,
            "tentativa": tentativa.numero,
            "motivo": tentativa.motivo,
        }
        fingerprint = _hash_comando("tentativa_falhou", contexto.usuario_id, dados)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        if atual.status is not StatusEntrega.EM_ROTA:
            raise ErroEntrega("transicao_entrega_invalida")
        nova = replace(
            atual,
            status=StatusEntrega.TENTATIVA_FALHOU,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.tentativa_falhou",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=tentativa.registrada_em,
            payload={"tentativa": tentativa.numero, "motivo": tentativa.motivo},
        )

    def confirmar_entrega(
        self,
        entrega_id: str,
        prova: ProvaEntrega,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        atual = self._obter(entrega_id, contexto)
        _autorizar_entregador(atual, contexto)
        dados = {
            "entrega_id": entrega_id,
            "versao_esperada": versao_esperada,
            "prova_referencia": prova.referencia,
            "prova_tipo": prova.tipo,
        }
        fingerprint = _hash_comando("confirmar_entrega", contexto.usuario_id, dados)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        if atual.status not in {StatusEntrega.COLETADA, StatusEntrega.EM_ROTA}:
            raise ErroEntrega("transicao_entrega_invalida")
        if not self.financeiro_resolvido(
            atual.tenant_id,
            atual.unidade_id,
            atual.pedido_id,
        ):
            raise ErroEntrega("criterio_financeiro_pendente")
        nova = replace(
            atual,
            status=StatusEntrega.ENTREGUE,
            entregue_em=prova.registrada_em,
            prova_entrega_ref=prova.referencia,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.concluida",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=prova.registrada_em,
            payload={"prova_tipo": prova.tipo, "prova_ref": prova.referencia},
        )

    def cancelar(
        self,
        entrega_id: str,
        motivo: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        atual = self._obter(entrega_id, contexto)
        permitido = contexto.identidade_sistema or bool(
            contexto.papeis.intersection(
                {Papel.ADMINISTRADOR, Papel.GERENTE, Papel.ATENDIMENTO}
            )
        )
        if not permitido:
            raise ErroEntrega("cancelamento_sem_alcada")
        texto = motivo.strip()
        if not texto or len(texto) > 200:
            raise ErroEntrega("motivo_cancelamento_invalido")
        dados = {
            "entrega_id": entrega_id,
            "versao_esperada": versao_esperada,
            "motivo": texto,
        }
        fingerprint = _hash_comando("cancelar", contexto.usuario_id, dados)
        repetida = self._repeticao(contexto, idempotency_key, fingerprint)
        if repetida is not None:
            return repetida
        self._validar_versao(atual, versao_esperada)
        permitidos = {
            StatusEntrega.AGUARDANDO_PRODUCAO,
            StatusEntrega.AGUARDANDO_EXPEDICAO,
            StatusEntrega.AGUARDANDO_ENTREGADOR,
            StatusEntrega.ATRIBUIDA,
            StatusEntrega.TENTATIVA_FALHOU,
        }
        if atual.status not in permitidos:
            raise ErroEntrega("transicao_entrega_invalida")
        if not self.pedido_cancelado(
            atual.tenant_id,
            atual.unidade_id,
            atual.pedido_id,
        ):
            raise ErroEntrega("pedido_ainda_ativo")
        instante = self._agora()
        nova = replace(
            atual,
            status=StatusEntrega.CANCELADA,
            versao=atual.versao + 1,
        )
        return self._persistir_evento(
            atual,
            nova,
            contexto=contexto,
            tipo="entrega.cancelada",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload={"motivo": texto},
        )

    def _persistir_evento(
        self,
        anterior: Entrega,
        nova: Entrega,
        *,
        contexto: ContextoExecucao,
        tipo: str,
        idempotency_key: str,
        fingerprint: str,
        instante: datetime,
        payload: dict[str, object],
    ) -> Entrega:
        self.repositorio.salvar(
            nova,
            versao_esperada=anterior.versao,
            atualizado_em=instante,
        )
        self._evento(
            nova,
            contexto=contexto,
            tipo=tipo,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            instante=instante,
            payload=payload,
        )
        return nova

    def _evento(
        self,
        entrega: Entrega,
        *,
        contexto: ContextoExecucao,
        tipo: str,
        idempotency_key: str,
        fingerprint: str,
        instante: datetime,
        payload: dict[str, object],
    ) -> None:
        self.repositorio.append_evento(
            event_id=str(uuid4()),
            entrega=entrega,
            tipo=tipo,
            ator_id=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            ocorrido_em=instante,
            payload_seguro=payload,
        )

    def _repeticao(
        self,
        contexto: ContextoExecucao,
        idempotency_key: str,
        fingerprint: str,
    ) -> Entrega | None:
        chave = idempotency_key.strip()
        if not chave or len(chave) > 128:
            raise ErroEntrega("idempotency_key_invalida")
        evento = self.repositorio.buscar_evento_idempotente(
            contexto.tenant_id,
            contexto.unidade_id,
            chave,
        )
        if evento is None:
            return None
        if evento.request_hash != fingerprint:
            raise ErroEntrega("conflito_idempotencia")
        entrega = self.repositorio.buscar(
            contexto.tenant_id,
            contexto.unidade_id,
            evento.entrega_id,
        )
        if entrega is None:
            raise ErroEntrega("idempotencia_sem_agregado")
        return entrega

    def _obter(self, entrega_id: str, contexto: ContextoExecucao) -> Entrega:
        entrega = self.repositorio.buscar(
            contexto.tenant_id,
            contexto.unidade_id,
            entrega_id,
        )
        if entrega is None:
            raise ErroEntrega("entrega_nao_encontrada")
        self._validar_escopo(entrega, contexto)
        return entrega

    @staticmethod
    def _fingerprint(
        nome: str,
        contexto: ContextoExecucao,
        entrega_id: str,
        versao_esperada: int,
    ) -> str:
        return _hash_comando(
            nome,
            contexto.usuario_id,
            {"entrega_id": entrega_id, "versao_esperada": versao_esperada},
        )

    @staticmethod
    def _validar_escopo(entrega: Entrega, contexto: ContextoExecucao) -> None:
        if (
            entrega.tenant_id != contexto.tenant_id
            or entrega.unidade_id != contexto.unidade_id
        ):
            raise ErroEntrega("escopo_entrega_invalido")

    @staticmethod
    def _validar_versao(entrega: Entrega, versao_esperada: int) -> None:
        if entrega.versao != versao_esperada:
            raise ErroEntrega("compare_and_swap_falhou")

    def _agora(self) -> datetime:
        instante = self.agora()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ErroEntrega("timestamp_invalido")
        return instante.astimezone(timezone.utc)
