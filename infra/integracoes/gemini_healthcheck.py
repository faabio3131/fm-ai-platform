"""Healthcheck real e escopado do Gemini antes da homologação formal.

Este caminho existe somente para produzir evidência externa real usando a configuração
e a credencial já salvas no control plane. Ele não altera ``homologada`` e não expõe
a API key, a resposta completa ou detalhes internos do provedor.
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
from .transportes import GoogleGenAITenantGateway

_PROMPT = "Responda exatamente com KORDENA_GEMINI_OK e nada mais."
_EXPECTED = "KORDENA_GEMINI_OK"


def _classificar_falha_gemini(exc: Exception) -> str:
    """Classifica falhas do provedor sem devolver corpo, headers ou credenciais."""

    cadeia: list[BaseException] = []
    atual: BaseException | None = exc
    for _ in range(6):
        if atual is None or atual in cadeia:
            break
        cadeia.append(atual)
        atual = atual.__cause__ or atual.__context__

    codigos: set[int] = set()
    textos: list[str] = []
    for item in cadeia:
        for atributo in ("code", "status_code", "status"):
            valor = getattr(item, atributo, None)
            if isinstance(valor, int):
                codigos.add(valor)
            elif isinstance(valor, str) and valor.isdigit():
                codigos.add(int(valor))
        textos.append(str(item).casefold())

    texto = " ".join(textos)

    if 401 in codigos or "api_key_invalid" in texto or "invalid api key" in texto:
        return "gemini_api_key_invalida"
    if 403 in codigos or "permission_denied" in texto or "permission denied" in texto:
        return "gemini_api_key_sem_permissao"
    if 404 in codigos or "not_found" in texto or "model not found" in texto:
        return "gemini_modelo_indisponivel"
    if 429 in codigos or "resource_exhausted" in texto or "quota" in texto:
        return "gemini_quota_ou_faturamento"
    if any(codigo >= 500 for codigo in codigos):
        return "gemini_provedor_indisponivel"
    if 400 in codigos or "invalid_argument" in texto or "bad request" in texto:
        return "gemini_requisicao_rejeitada"
    if isinstance(exc, TimeoutError) or "timeout" in texto:
        return "gemini_timeout"
    return "gemini_healthcheck_externo_falhou"


@dataclass(frozen=True, kw_only=True)
class ResultadoHealthcheckGemini:
    evidencia_ref: str
    model: str


def _evidencia(
    *, contexto: ContextoExecucao, configuracao_id: str, model: str, texto: str, agora: datetime
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = (
        f"{contexto.tenant_id}|{contexto.unidade_id}|{configuracao_id}|"
        f"{model}|{instante}|{texto}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://gemini/{instante}/{model}/{digest}"


def executar_healthcheck_gemini(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    configuracao_id: str = "ia.generativa--gemini",
    gateway: GoogleGenAITenantGateway | None = None,
    agora: datetime | None = None,
) -> ResultadoHealthcheckGemini:
    """Executa uma única chamada externa real sem exigir homologação prévia."""

    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        configuracao_id=configuracao_id,
    )
    if config is None:
        raise ErroConfiguracaoServico("configuracao_indisponivel")
    if not config.habilitada:
        raise ErroConfiguracaoServico("integracao_desabilitada")
    if (config.servico, config.provedor) != ("ia.generativa", "gemini"):
        raise ErroConfiguracaoServico("adapter_incompativel")

    model = str(config.parametros.get("model") or "").strip()
    finalidade = str(config.credenciais.get("api_key") or "").strip()
    if not model or not finalidade:
        raise ErroConfiguracaoServico("gemini_configuracao_incompleta")

    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == contexto.tenant_id,
            CredencialReferenciaORM.unidade_id == contexto.unidade_id,
            CredencialReferenciaORM.provedor == "gemini",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_indisponivel")

    api_key = secret_store.resolve(row.referencia).reveal()
    transporte = gateway or GoogleGenAITenantGateway()
    try:
        resposta = transporte.generate_content(
            api_key=api_key,
            model=model,
            contents=_PROMPT,
            timeout_seconds=20.0,
        )
    except Exception as exc:
        raise ErroConfiguracaoServico(_classificar_falha_gemini(exc)) from exc

    texto = str(getattr(resposta, "text", "") or "").strip()
    if _EXPECTED not in texto.upper():
        raise ErroConfiguracaoServico("gemini_healthcheck_resposta_invalida")

    return ResultadoHealthcheckGemini(
        evidencia_ref=_evidencia(
            contexto=contexto,
            configuracao_id=configuracao_id,
            model=model,
            texto=texto,
            agora=agora or datetime.now(timezone.utc),
        ),
        model=model,
    )
