"""Casos de uso da Impressão opcional por Setor V1."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from core.kds.modelos import ProducaoItem, SetorProducao
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

from .adapters import PortaImpressora
from .erros import ErroImpressao
from .modelos import (
    DestinoImpressao,
    JobImpressao,
    ResultadoEnfileiramento,
    ResultadoProcessamento,
    StatusImpressao,
)
from .repositorios import RepositorioSpoolImpressao

TEMPLATE_VERSAO = "ticket_setor_v1"


def _utc(instante: datetime) -> datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ErroImpressao("timestamp_invalido")
    return instante.astimezone(timezone.utc)


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _texto_operacional(valor: str | None, limite: int = 180) -> str:
    if not valor:
        return ""
    return " ".join(valor.replace("\x00", "").split())[:limite]


def _quantidade(valor: Decimal) -> str:
    texto = format(valor.normalize(), "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def renderizar_ticket_setor(
    *,
    producao: ProducaoItem,
    setor: SetorProducao,
    descricao_item: str,
    observacao: str | None = None,
) -> str:
    """Renderiza somente dados operacionais; não inclui contato/endereço/pagamento."""
    descricao = _texto_operacional(descricao_item) or producao.pedido_item_id
    nota = _texto_operacional(observacao)
    linhas = [
        "=== PRODUCAO ===",
        f"SETOR: {_texto_operacional(setor.nome, 80)}",
        f"PEDIDO: {producao.pedido_id}",
        f"ITEM: {descricao}",
        f"QTD: {_quantidade(producao.quantidade)}",
        f"PRODUCAO: {producao.producao_id}",
    ]
    if nota:
        linhas.append(f"OBS: {nota}")
    linhas.append(f"TEMPLATE: {TEMPLATE_VERSAO}")
    return "\n".join(linhas)


class ServicoSpoolImpressao:
    """Spool opcional: qualquer falha termina no domínio de impressão, nunca no KDS."""

    def __init__(
        self,
        *,
        repositorio: RepositorioSpoolImpressao,
        impressora: PortaImpressora,
        destinos: tuple[DestinoImpressao, ...],
    ) -> None:
        self.repositorio = repositorio
        self.impressora = impressora
        self._destinos = {
            (destino.tenant_id, destino.unidade_id, destino.setor_id): destino
            for destino in destinos
            if destino.ativo
        }

    def enfileirar_item_kds(
        self,
        *,
        contexto: ContextoExecucao,
        producao: ProducaoItem,
        setor: SetorProducao,
        idempotency_key: str,
        descricao_item: str,
        timestamp: datetime,
        observacao: str | None = None,
    ) -> ResultadoEnfileiramento:
        agora = _utc(timestamp)
        if not idempotency_key.strip():
            raise ErroImpressao("idempotency_key_obrigatoria")
        if producao.tenant_id != contexto.tenant_id or producao.unidade_id != contexto.unidade_id:
            raise ErroImpressao("recurso_indisponivel")
        if setor.tenant_id != contexto.tenant_id or setor.unidade_id != contexto.unidade_id:
            raise ErroImpressao("recurso_indisponivel")
        if producao.setor_id != setor.setor_id:
            raise ErroImpressao("setor_producao_divergente")
        destino = self._destinos.get((contexto.tenant_id, contexto.unidade_id, setor.setor_id))
        if not destino:
            return ResultadoEnfileiramento(None, False, False, "sem_destino_ativo")

        conteudo = renderizar_ticket_setor(
            producao=producao,
            setor=setor,
            descricao_item=descricao_item,
            observacao=observacao,
        )
        documento_hash = _hash(conteudo)
        dedup_key = _hash(
            "|".join(
                (
                    contexto.tenant_id,
                    contexto.unidade_id,
                    setor.setor_id,
                    idempotency_key,
                    TEMPLATE_VERSAO,
                )
            )
        )
        existente = self.repositorio.buscar_por_dedup(
            contexto.tenant_id, contexto.unidade_id, dedup_key
        )
        if existente:
            return ResultadoEnfileiramento(existente, False, True, "deduplicado")

        job = JobImpressao(
            job_id=str(uuid4()),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            setor_id=setor.setor_id,
            producao_id=producao.producao_id,
            pedido_id=producao.pedido_id,
            pedido_item_id=producao.pedido_item_id,
            impressora_id=destino.impressora_id,
            dedup_key=dedup_key,
            documento_hash=documento_hash,
            conteudo=conteudo,
            status=StatusImpressao.PENDENTE,
            tentativa=0,
            max_tentativas=destino.max_tentativas,
            versao=1,
            criado_em=agora,
            atualizado_em=agora,
        )
        salvo = self.repositorio.adicionar(job)
        return ResultadoEnfileiramento(salvo, True, False, "enfileirado")

    def processar(self, *, contexto: ContextoExecucao, job_id: str, timestamp: datetime) -> ResultadoProcessamento:
        agora = _utc(timestamp)
        job = self.repositorio.buscar(contexto.tenant_id, contexto.unidade_id, job_id)
        if not job:
            raise ErroImpressao("job_impressao_indisponivel")
        if job.status is StatusImpressao.IMPRESSO:
            return ResultadoProcessamento(job, True, False)
        if job.status is StatusImpressao.CONTINGENCIA:
            return ResultadoProcessamento(job, False, True)

        tentativa = job.tentativa + 1
        try:
            self.impressora.imprimir(
                impressora_id=job.impressora_id,
                job_id=job.job_id,
                conteudo=job.conteudo,
            )
        except Exception:
            contingencia = tentativa >= job.max_tentativas
            novo = replace(
                job,
                status=(StatusImpressao.CONTINGENCIA if contingencia else StatusImpressao.FALHOU),
                tentativa=tentativa,
                versao=job.versao + 1,
                atualizado_em=agora,
                ultimo_erro="impressora_indisponivel",
            )
            salvo = self.repositorio.atualizar(novo, versao_esperada=job.versao)
            return ResultadoProcessamento(salvo, False, contingencia)

        novo = replace(
            job,
            status=StatusImpressao.IMPRESSO,
            tentativa=tentativa,
            versao=job.versao + 1,
            atualizado_em=agora,
            ultimo_erro=None,
        )
        salvo = self.repositorio.atualizar(novo, versao_esperada=job.versao)
        return ResultadoProcessamento(salvo, True, False)

    def reimprimir(
        self,
        *,
        contexto: ContextoExecucao,
        job_id: str,
        motivo: str,
        timestamp: datetime,
    ) -> tuple[JobImpressao, EventoAuditoria]:
        agora = _utc(timestamp)
        motivo_seguro = _texto_operacional(motivo, 120)
        if len(motivo_seguro) < 5:
            raise ErroImpressao("motivo_reimpressao_obrigatorio")
        original = self.repositorio.buscar(contexto.tenant_id, contexto.unidade_id, job_id)
        if not original:
            raise ErroImpressao("job_impressao_indisponivel")
        decisao = AutorizarAcao().executar(
            contexto=contexto,
            permissao=Permissao.IMPRESSAO_REIMPRIMIR,
            recurso="job_impressao",
            tenant_recurso=original.tenant_id,
            unidade_recurso=original.unidade_id,
        )
        if not decisao.autorizado:
            raise ErroImpressao(decisao.codigo)

        novo = JobImpressao(
            job_id=str(uuid4()),
            tenant_id=original.tenant_id,
            unidade_id=original.unidade_id,
            setor_id=original.setor_id,
            producao_id=original.producao_id,
            pedido_id=original.pedido_id,
            pedido_item_id=original.pedido_item_id,
            impressora_id=original.impressora_id,
            dedup_key=_hash(f"reprint|{original.job_id}|{uuid4()}"),
            documento_hash=original.documento_hash,
            conteudo=original.conteudo,
            status=StatusImpressao.PENDENTE,
            tentativa=0,
            max_tentativas=original.max_tentativas,
            versao=1,
            criado_em=agora,
            atualizado_em=agora,
            reimpressao_de=original.job_id,
            motivo_reimpressao=motivo_seguro,
        )
        salvo = self.repositorio.adicionar(novo)
        papel = next(iter(sorted(contexto.papeis, key=str)), None)
        auditoria = EventoAuditoria(
            audit_id=str(uuid4()),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            usuario_id=contexto.usuario_id,
            papel_efetivo=papel,
            acao="impressao.reimprimir",
            recurso_tipo="job_impressao",
            recurso_id=salvo.job_id,
            resultado="sucesso",
            motivo="reimpressao_solicitada",
            correlation_id=contexto.correlation_id,
            timestamp=agora,
            origem=contexto.origem,
            politica="impressao_por_setor_v1",
            causation_id=contexto.causation_id,
            metadata=sanitizar_metadata(
                {
                    "job_original": original.job_id,
                    "setor_id": original.setor_id,
                    "motivo": motivo_seguro,
                }
            ),
        )
        return salvo, auditoria
