"""Healthcheck externo real e somente leitura para recursos Meta.

Valida credenciais salvas no cofre e acesso ao recurso configurado sem publicar,
enviar mensagem ou alterar dados externos. A homologacao final continua separada.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import ErroConfiguracaoServico
from core.integracoes.provedores import PortaHTTPProvedor
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from .transportes import RequestsProviderTransport


@dataclass(frozen=True, kw_only=True)
class ResultadoHealthcheckMeta:
    servico: str
    recurso_id: str
    rotulo: str
    evidencia_ref: str


def _segredo(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    finalidade: str,
) -> str:
    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == contexto.tenant_id,
            CredencialReferenciaORM.unidade_id == contexto.unidade_id,
            CredencialReferenciaORM.provedor == "meta",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_meta_indisponivel")
    return secret_store.resolve(row.referencia).reveal()


def _evidencia(
    *,
    contexto: ContextoExecucao,
    configuracao_id: str,
    recurso_id: str,
    agora: datetime,
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = "|".join(
        (
            contexto.tenant_id,
            contexto.unidade_id,
            configuracao_id,
            recurso_id,
            instante,
            "meta-readonly-access",
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://meta-access/{instante}/{digest}"


def _recurso(servico: str, parametros: Mapping[str, Any]) -> tuple[str, str]:
    if servico == "social.facebook":
        return str(parametros.get("page_id") or "").strip(), "name"
    if servico == "social.instagram":
        return str(parametros.get("business_account_id") or "").strip(), "username"
    if servico == "mensageria.whatsapp":
        return str(parametros.get("phone_number_id") or "").strip(), "display_phone_number,verified_name"
    raise ErroConfiguracaoServico("servico_meta_nao_suportado")


def executar_healthcheck_meta(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    configuracao_id: str,
    http: PortaHTTPProvedor | None = None,
    agora: datetime | None = None,
) -> ResultadoHealthcheckMeta:
    """Valida acesso real ao ativo Meta configurado, sem efeitos colaterais."""

    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        configuracao_id=configuracao_id,
    )
    if config is None:
        raise ErroConfiguracaoServico("configuracao_indisponivel")
    if config.provedor != "meta":
        raise ErroConfiguracaoServico("adapter_incompativel")
    if not config.habilitada:
        raise ErroConfiguracaoServico("integracao_desabilitada")

    access_purpose = str(config.credenciais.get("access_token") or "").strip()
    secret_purpose = str(config.credenciais.get("app_secret") or "").strip()
    if not access_purpose or not secret_purpose:
        raise ErroConfiguracaoServico("credenciais_meta_incompletas")

    access_token = _segredo(
        session=session,
        secret_store=secret_store,
        contexto=contexto,
        finalidade=access_purpose,
    )
    app_secret = _segredo(
        session=session,
        secret_store=secret_store,
        contexto=contexto,
        finalidade=secret_purpose,
    )

    recurso_id, campos = _recurso(config.servico, config.parametros)
    if not recurso_id:
        raise ErroConfiguracaoServico("recurso_meta_ausente")

    versao = str(config.parametros.get("graph_api_version") or "v23.0").strip()
    proof = hmac.new(
        app_secret.encode("utf-8"), access_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    query = urlencode({"fields": f"id,{campos}", "appsecret_proof": proof})
    url = f"https://graph.facebook.com/{versao}/{recurso_id}?{query}"

    transporte = http or RequestsProviderTransport()
    resposta = transporte.request(
        method="GET",
        url=url,
        headers={"Authorization": f"Bearer {access_token}"},
        json_body=None,
        timeout_seconds=8.0,
    )
    if not 200 <= resposta.status_code < 300 or not isinstance(resposta.payload, Mapping):
        raise ErroConfiguracaoServico("healthcheck_meta_rejeitado")

    retornado = str(resposta.payload.get("id") or "").strip()
    if retornado != recurso_id:
        raise ErroConfiguracaoServico("recurso_meta_incompativel")

    rotulo = str(
        resposta.payload.get("name")
        or resposta.payload.get("username")
        or resposta.payload.get("verified_name")
        or resposta.payload.get("display_phone_number")
        or recurso_id
    ).strip()

    evidencia = _evidencia(
        contexto=contexto,
        configuracao_id=configuracao_id,
        recurso_id=recurso_id,
        agora=agora or datetime.now(timezone.utc),
    )
    return ResultadoHealthcheckMeta(
        servico=config.servico,
        recurso_id=recurso_id,
        rotulo=rotulo or recurso_id,
        evidencia_ref=evidencia,
    )
