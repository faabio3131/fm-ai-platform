"""Porta e adapter em memória para o spool de impressão V1."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock
from typing import Protocol

from .erros import ErroImpressao
from .modelos import JobImpressao


class RepositorioSpoolImpressao(Protocol):
    def buscar(
        self, tenant_id: str, unidade_id: str, job_id: str
    ) -> JobImpressao | None: ...

    def buscar_por_dedup(
        self, tenant_id: str, unidade_id: str, dedup_key: str
    ) -> JobImpressao | None: ...

    def adicionar(self, job: JobImpressao) -> JobImpressao: ...

    def atualizar(self, job: JobImpressao, *, versao_esperada: int) -> JobImpressao: ...

    def listar(self, tenant_id: str, unidade_id: str) -> tuple[JobImpressao, ...]: ...


class RepositorioSpoolEmMemoria:
    """Adapter determinístico com unicidade de dedup e CAS por versão."""

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str, str], JobImpressao] = {}
        self._dedup: dict[tuple[str, str, str], str] = {}
        self._lock = RLock()

    def buscar(
        self, tenant_id: str, unidade_id: str, job_id: str
    ) -> JobImpressao | None:
        with self._lock:
            job = self._jobs.get((tenant_id, unidade_id, job_id))
            return replace(job) if job else None

    def buscar_por_dedup(
        self, tenant_id: str, unidade_id: str, dedup_key: str
    ) -> JobImpressao | None:
        with self._lock:
            job_id = self._dedup.get((tenant_id, unidade_id, dedup_key))
            if not job_id:
                return None
            job = self._jobs.get((tenant_id, unidade_id, job_id))
            return replace(job) if job else None

    def adicionar(self, job: JobImpressao) -> JobImpressao:
        with self._lock:
            chave = (job.tenant_id, job.unidade_id, job.job_id)
            chave_dedup = (job.tenant_id, job.unidade_id, job.dedup_key)
            if chave in self._jobs:
                raise ErroImpressao("job_impressao_ja_existe")
            if chave_dedup in self._dedup:
                raise ErroImpressao("conflito_idempotencia_impressao")
            self._jobs[chave] = replace(job)
            self._dedup[chave_dedup] = job.job_id
            return replace(job)

    def atualizar(self, job: JobImpressao, *, versao_esperada: int) -> JobImpressao:
        with self._lock:
            chave = (job.tenant_id, job.unidade_id, job.job_id)
            atual = self._jobs.get(chave)
            if not atual:
                raise ErroImpressao("job_impressao_indisponivel")
            if atual.versao != versao_esperada:
                raise ErroImpressao("job_impressao_concorrente")
            if job.versao != versao_esperada + 1:
                raise ErroImpressao("versao_impressao_invalida")
            self._jobs[chave] = replace(job)
            return replace(job)

    def listar(self, tenant_id: str, unidade_id: str) -> tuple[JobImpressao, ...]:
        with self._lock:
            jobs = [
                replace(job)
                for (tenant, unidade, _), job in self._jobs.items()
                if tenant == tenant_id and unidade == unidade_id
            ]
        jobs.sort(key=lambda job: (job.criado_em, job.job_id))
        return tuple(jobs)
