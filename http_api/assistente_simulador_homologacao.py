"""Simulador diagnóstico isolado: desativado por padrão, sem side effects comerciais."""
from __future__ import annotations

import logging
from pathlib import Path
from traceback import extract_tb
import os
from collections.abc import Callable
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from application.assistente_simulador_transacao import confirmar_auditoria_simulador
from core.ai_router import (
    CapabilityIA,
    FalhaRotaDefinitiva,
    FalhaRotaTransitoria,
    SemRotaCompativel,
    SolicitacaoIA,
)
from core.seguranca.erros import ErroSeguranca
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional
from infra.transacoes.uow import UnitOfWorkV1


logger = logging.getLogger(__name__)

class MensagemSimulador(BaseModel):
    mensagem: str = Field(min_length=1, max_length=500)
    testar_gemini: bool = False


def build_assistente_simulador_router(
    *, session_factory: Callable[[], Session],
    auth_runtime: AuthSessionRuntime,
    secret_store_factory: Callable[[Session], SecretStore],
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/assistente-atendimento", tags=["homologacao"])

    @router.post("/simulador")
    def diagnosticar(payload: MensagemSimulador, request: Request) -> JSONResponse:
        # Flag desligada em todos os ambientes até liberação explícita de homologação.
        if os.getenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "").lower() != "true":
            return JSONResponse(status_code=404, content={"erro": "simulador.desabilitado"})
        try:
            with session_factory() as session:
                acesso = obter_identidade_operacional(
                    request, session, auth_runtime=auth_runtime
                )
            # Sessão web + step-up; Basic legado não autoriza diagnóstico.
            if acesso.modo != "session":
                return JSONResponse(status_code=403, content={"erro": "simulador.sessao_exigida"})
            identidade = acesso.identidade
            if (
                Permissao.ADMIN_ACESSAR not in identidade.permissoes
                or Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes
            ):
                return JSONResponse(status_code=403, content={"erro": "simulador.permissao_insuficiente"})
            _, elevado, _ = auth_runtime.admin_status(request)
            if not elevado:
                return JSONResponse(status_code=403, content={"erro": "seguranca.admin_step_up_exigido"})
            contexto = identidade.contexto(
                origem="assistente_simulador_diagnostico",
                correlation_id=str(uuid4()),
            )
            with UnitOfWorkV1(session_factory) as uow:
                if uow.session is None:
                    raise RuntimeError("uow_indisponivel")
                router_ia = construir_ai_model_router(
                    session=uow.session,
                    contexto=contexto,
                    secret_store=secret_store_factory(uow.session),
                )
                resposta = router_ia.executar(SolicitacaoIA(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    request_id=str(uuid4()),
                    correlation_id=contexto.correlation_id,
                    capability=(
                        CapabilityIA.ATENDIMENTO_DIAGNOSTICO_GEMINI
                        if payload.testar_gemini
                        else CapabilityIA.ATENDIMENTO_INTERPRETACAO
                    ),
                    conteudo=(
                        "MODO DIAGNÓSTICO SEM EFEITOS EXTERNOS. Responda à mensagem "
                        "em português como atendente de restaurante. Nunca execute "
                        "ferramentas nem alegue ter criado pedidos, pagamentos ou mensagens. "
                        "Não invente produtos ou preços. Mensagem do teste: " + payload.mensagem
                    ),
                ))
                if payload.testar_gemini and resposta.provider != "gemini":
                    return JSONResponse(status_code=503, content={"erro": "simulador.gemini_nao_utilizado"})
                confirmar_auditoria_simulador(uow)
                return JSONResponse(content={
                    "resposta": str(resposta.conteudo)[:2000],
                    "provedor": resposta.provider,
                    "modelo": resposta.model,
                    "fallback": resposta.fallback_used,
                    "correlation_id": contexto.correlation_id,
                })
        except SemRotaCompativel:
            return JSONResponse(status_code=503, content={"erro": "simulador.rota_nao_configurada"})
        except FalhaRotaTransitoria:
            return JSONResponse(status_code=503, content={"erro": "simulador.provedor_temporariamente_indisponivel"})
        except FalhaRotaDefinitiva:
            return JSONResponse(status_code=502, content={"erro": "simulador.provedor_rejeitou"})
        except ErroSeguranca:
            return JSONResponse(status_code=401, content={"erro": "simulador.nao_autenticado"})
        except Exception as exc:
            logger.error(
                "simulador.falhou exception_type=%s origin=%s",
                type(exc).__name__,
                [
                    (Path(frame.filename).name, frame.name, frame.lineno)
                    for frame in extract_tb(exc.__traceback__)[-3:]
                ],
            )
            # Nunca expor detalhes da configuração, segredos ou mensagens do provider.
            return JSONResponse(status_code=503, content={"erro": "simulador.ia_indisponivel"})

    return router
