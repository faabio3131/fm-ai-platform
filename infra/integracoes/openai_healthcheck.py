"""Healthcheck real e escopado da OpenAI antes da homologação formal.

Executa uma chamada mínima com a credencial já salva no control plane, produz
somente evidência sanitizada e não altera o estado de homologação.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from .transportes import OpenAIChatTenantGateway

_PROMPT = "Responda exatamente com KORDENA_OPENAI_OK e nada mais."
_EXPECTED = "KORDENA_OPENAI_OK"


def _classificar_falha_openai(exc: Exception) -> str:
    cadeia: list[BaseException] = []
    atual: BaseException | None = exc
    for _ in range(6):
        if atual is None or atual in cadeia:
            break
        cadeia.append(atual)
        atual = atual.__cause__ or atual.__context__

    textos = " ".join(str(item).casefold() for item in cadeia)
    if "401" in textos or "invalid api key" in textos or "incorrect api key" in textos:
        return "openai_api_key_invalida"
    if "403" in textos or "permission" in textos:
        return "openai_api_key_sem_permissao"
    if "404" in textos or "model" in textos and "not" in textos:
        return "openai_modelo_indisponivel"
    if "429" in textos or "quota" in textos or "rate limit" in textos:
        return "openai_quota_ou_faturamento"
    if any(codigo in textos for codigo in ("500", "502", "503", "504")):
        return "openai_provedor_indisponivel"
    if isinstance(exc, TimeoutError) or "timeout" in textos:
        return "openai_timeout"
    return "openai_healthcheck_externo_falhou"


@dataclass(frozen=True, kw_only=True)
class ResultadoHealthcheckOpenAI:
    evidencia_ref: str
    model: str


def _evidencia(
    *,
    contexto: ContextoExecucao,
    configuracao_id: str,
    model: str,
    texto: str,
    agora: datetime,
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = (
        f"{contexto.tenant_id}|{contexto.unidade_id}|{configuracao_id}|"
        f"{model}|{instante}|{texto}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://openai/{instante}/{model}/{digest}"


def executar_healthcheck_openai(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    configuracao_id: str = "ia.generativa--openai",
    gateway: OpenAIChatTenantGateway | None = None,
    agora: datetime | None = None,
) -> ResultadoHealthcheckOpenAI:
    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        configuracao_id=configuracao_id,
    )
    if config is None:
        raise ErroConfiguracaoServico("configuracao_indisponivel")
    if not config.habilitada:
        raise ErroConfiguracaoServico("integracao_desabilitada")
    if (config.servico, config.provedor) != ("ia.generativa", "openai"):
        raise ErroConfiguracaoServico("adapter_incompativel")

    model = str(config.parametros.get("model") or "").strip()
    finalidade = str(config.credenciais.get("api_key") or "").strip()
    if not model or not finalidade:
        raise ErroConfiguracaoServico("openai_configuracao_incompleta")

    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == contexto.tenant_id,
            CredencialReferenciaORM.unidade_id == contexto.unidade_id,
            CredencialReferenciaORM.provedor == "openai",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_indisponivel")

    api_key = secret_store.resolve(row.referencia).reveal()
    transporte = gateway or OpenAIChatTenantGateway()
    try:
        resposta = transporte.create_chat_completion(
            api_key=api_key,
            model=model,
            contents=_PROMPT,
            timeout_seconds=20.0,
        )
    except Exception as exc:
        raise ErroConfiguracaoServico(_classificar_falha_openai(exc)) from exc

    texto = str(resposta.get("text") if isinstance(resposta, dict) else "").strip()
    if _EXPECTED not in texto.upper():
        raise ErroConfiguracaoServico("openai_healthcheck_resposta_invalida")

    return ResultadoHealthcheckOpenAI(
        evidencia_ref=_evidencia(
            contexto=contexto,
            configuracao_id=configuracao_id,
            model=model,
            texto=texto,
            agora=agora or datetime.now(timezone.utc),
        ),
        model=model,
    )
