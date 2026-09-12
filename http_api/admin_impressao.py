"""DTOs HTTP da Impressão Operacional V1; reutiliza autoridade Application existente."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from application.impressao_transacoes import AplicacaoImpressaoV1
from core.impressao import (
    ErroImpressao,
    JobImpressao,
    PortaImpressora,
    ResultadoProcessamento,
)
from core.seguranca.erros import ErroSeguranca
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime
from infra.impressao import ImpressoraTCPRaw, ResolverDestinosImpressaoSQLAlchemy


class JobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    tenant_id: str
    unidade_id: str
    setor_id: str
    producao_id: str
    pedido_id: str
    pedido_item_id: str
    impressora_id: str
    dedup_key: str
    documento_hash: str
    conteudo: str
    status: str
    tentativa: int
    max_tentativas: int
    versao: int
    criado_em: str
    atualizado_em: str
    ultimo_erro: str | None = None
    reimpressao_de: str | None = None
    motivo_reimpressao: str | None = None


def _job_out(job: JobImpressao) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "unidade_id": job.unidade_id,
        "setor_id": job.setor_id,
        "producao_id": job.producao_id,
        "pedido_id": job.pedido_id,
        "pedido_item_id": job.pedido_item_id,
        "impressora_id": job.impressora_id,
        "dedup_key": job.dedup_key,
        "documento_hash": job.documento_hash,
        "conteudo": job.conteudo,
        "status": job.status.value,
        "tentativa": job.tentativa,
        "max_tentativas": job.max_tentativas,
        "versao": job.versao,
        "criado_em": job.criado_em.isoformat(),
        "atualizado_em": job.atualizado_em.isoformat(),
        "ultimo_erro": job.ultimo_erro,
        "reimpressao_de": job.reimpressao_de,
        "motivo_reimpressao": job.motivo_reimpressao,
    }


class ProcessarOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job: JobOut
    impresso: bool
    contingencia: bool


def _processar_out(resultado: ResultadoProcessamento) -> dict[str, Any]:
    return {
        "job": _job_out(resultado.job),
        "impresso": resultado.impresso,
        "contingencia": resultado.contingencia,
    }


class ReimprimirIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=5, max_length=120)
    idempotency_key: str = Field(min_length=1)


def _erro_impressao(exc: Exception) -> JSONResponse:
    if isinstance(exc, ErroSeguranca):
        return _tratar_erro(exc)
    if isinstance(exc, PermissionError):
        return _tratar_erro(exc)
    if isinstance(exc, ErroImpressao):
        return JSONResponse(status_code=400, content={"erro": exc.codigo})
    return _tratar_erro(exc)


def _criar_aplicacao_impressao(
    session_factory: Callable[[], Session],
    contexto,
    *,
    impressora: PortaImpressora | None = None,
) -> AplicacaoImpressaoV1:
    """Cria aplicação de impressão com destinos resolvidos da configuração administrativa.

    A impressora pode ser injetada explicitamente (para testes). Default: ImpressoraTCPRaw.
    """
    with session_factory() as session:
        destinos = ResolverDestinosImpressaoSQLAlchemy(session).listar(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )

    if impressora is None:
        impressora = ImpressoraTCPRaw()

    return AplicacaoImpressaoV1(session_factory, impressora=impressora, destinos=destinos)


def build_admin_impressao_router(
    *,
    session_factory: Callable[[], Session],
    auth_runtime: AuthSessionRuntime,
    impressora: PortaImpressora | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin-impressao"])

    @router.get("/impressao/jobs", response_model=None)
    def listar_jobs(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_impressao_http_v1.listar",
            )
            app = _criar_aplicacao_impressao(session_factory, contexto, impressora=impressora)
            jobs = app.listar(contexto=contexto)
            return {"jobs": [_job_out(job) for job in jobs]}
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_impressao(exc)

    @router.post("/impressao/jobs/{job_id}/processar", response_model=None)
    def processar_job(job_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_impressao_http_v1.processar",
            )
            app = _criar_aplicacao_impressao(session_factory, contexto, impressora=impressora)
            resultado = app.processar(contexto=contexto, job_id=job_id)
            return _processar_out(resultado)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_impressao(exc)

    @router.post("/impressao/jobs/{job_id}/reimprimir", response_model=None)
    def reimprimir_job(job_id: str, payload: ReimprimirIn, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_impressao_http_v1.reimprimir",
            )
            app = _criar_aplicacao_impressao(session_factory, contexto, impressora=impressora)
            job = app.reimprimir(
                contexto=contexto,
                job_id=job_id,
                motivo=payload.motivo,
                idempotency_key=payload.idempotency_key,
            )
            return _job_out(job)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_impressao(exc)

    return router