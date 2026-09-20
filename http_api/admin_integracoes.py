"""Adaptador HTTP fino para a administração de integrações da V1.

Reutiliza a autoridade existente: CATALOGO_V1, ServicoConfiguracoesExternas,
AplicacaoIntegracoesAdminV1, healthchecks canônicos.
NÃO cria segunda autoridade.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from application.integracoes_admin_transacoes import AplicacaoIntegracoesAdminV1
from core.integracoes.catalogo import CATALOGO_V1
from core.integracoes.modelos import (
    AmbienteIntegracao,
    ConfiguracaoServicoExterno,
    ErroConfiguracaoServico,
    EstadoProntidaoServico,
    ValorParametro,
)
from core.integracoes.servicos import ServicoConfiguracoesExternas
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import (
    CredenciaisInvalidas,
    ErroSeguranca,
    PermissaoInsuficiente,
)
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import SecretStore
from http_api.auth import AuthSessionRuntime
from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini
from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps
from infra.integracoes.mercado_pago_healthcheck import executar_healthcheck_mercado_pago
from infra.integracoes.meta_healthcheck import executar_healthcheck_meta
from infra.integracoes.repositorio_sqlalchemy import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _tratar_erro_integracoes(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(401, "credenciais_invalidas")
    if isinstance(exc, PermissaoInsuficiente):
        return _erro(403, str(exc))
    if isinstance(exc, ErroConfiguracaoServico):
        codigo = str(exc)
        if codigo == "versao_configuracao_divergente":
            return _erro(409, codigo)
        return _erro(400, codigo)
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(403, str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")))
    if isinstance(exc, LookupError):
        return _erro(404, str(exc) or "admin.nao_encontrado")
    if isinstance(exc, (ValueError, TypeError)):
        return _erro(400, "admin.cadastro_invalido")
    return _erro(503, "admin.integracoes_indisponivel")


class CatalogoItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    servico: str
    provedor: str
    label: str
    parametros_obrigatorios: list[str]
    credenciais_obrigatorias: list[str]
    healthcheck_supported: bool


class ConfiguracaoSalvaOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configuracao_id: str
    servico: str
    provedor: str
    conta_externa: str
    ambiente: str
    parametros: dict[str, ValorParametro]
    credenciais_estado: dict[str, bool]
    habilitada: bool
    homologada: bool
    evidencia_homologacao_ref: str | None
    versao: int
    prontidao: dict[str, Any]


class IntegracaoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalogo: CatalogoItemOut
    configuracao: ConfiguracaoSalvaOut | None


class IntegracoesListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integracoes: list[IntegracaoOut]


class ParametroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    valor: ValorParametro


class CredencialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    papel: str
    valor: str


class IntegracoesPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    servico: str
    provedor: str
    conta_externa: str = "principal"
    ambiente: str
    parametros: list[ParametroIn]
    credenciais: list[CredencialIn]
    habilitada: bool
    versao: int


class HealthcheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executado: bool
    suportado: bool
    provedor: str
    evidencia_ref: str | None = None
    detalhes: dict[str, Any] | None = None
    erro: str | None = None


class HomologarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidencia_ref: str


_LABELS = {
    ("social.facebook", "meta"): "Meta · Facebook",
    ("social.instagram", "meta"): "Meta · Instagram Business",
    ("mensageria.whatsapp", "meta"): "Meta · WhatsApp Business",
    ("mapas", "google_maps"): "Google Maps",
    ("pagamentos.pix", "pagbank"): "PagBank · PIX",
    ("pagamentos.pix", "mercado_pago"): "Mercado Pago · PIX",
    ("ia.generativa", "gemini"): "Google Gemini",
    ("marketplace.pedidos", "ifood"): "Marketplace · iFood",
    ("marketplace.pedidos", "keeta"): "Marketplace · Keeta",
    ("fiscal.documentos", "sefaz"): "Fiscal · SEFAZ",
}

_HEALTHCHECK_SUPPORTED = {
    "gemini",
    "google_maps",
    "mercado_pago",
    "meta",
}

_STATUS_LABELS = {
    EstadoProntidaoServico.DESATIVADO: "desativado",
    EstadoProntidaoServico.BLOQUEADO: "bloqueado",
    EstadoProntidaoServico.CONFIGURADO: "configurado",
    EstadoProntidaoServico.PRONTO: "pronto",
}


def _config_id(spec_servico: str, spec_provedor: str) -> str:
    return f"{spec_servico}--{spec_provedor}"


def _catalogo_item_out(spec) -> CatalogoItemOut:
    provedor_normalizado = spec.provedor.strip().casefold()
    return CatalogoItemOut(
        servico=spec.servico,
        provedor=spec.provedor,
        label=_LABELS.get((spec.servico, spec.provedor), f"{spec.servico} · {spec.provedor}"),
        parametros_obrigatorios=sorted(spec.parametros_obrigatorios),
        credenciais_obrigatorias=sorted(spec.credenciais_obrigatorias),
        healthcheck_supported=provedor_normalizado in _HEALTHCHECK_SUPPORTED,
    )


def _credenciais_estado(config: ConfiguracaoServicoExterno, spec) -> dict[str, bool]:
    credenciais = config.credenciais
    return {papel: papel in credenciais for papel in sorted(spec.credenciais_obrigatorias)}


def _prontidao_out(prontidao) -> dict[str, Any]:
    return {
        "estado": _STATUS_LABELS.get(prontidao.estado, prontidao.estado.value),
        "pronto": prontidao.pronto,
        "faltam_parametros": list(prontidao.faltam_parametros),
        "faltam_finalidades": list(prontidao.faltam_finalidades),
        "faltam_credenciais": list(prontidao.faltam_credenciais),
    }





def _resolver_identidade_integracoes(request: Request, auth_runtime: AuthSessionRuntime) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    if Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes:
        raise PermissionError("seguranca.integracao_gerenciar_exigido")
    _, elevado, _ = auth_runtime.admin_status(request)
    if not elevado:
        raise PermissionError("seguranca.admin_step_up_exigido")
    return identidade.contexto(
        origem=request.headers.get("x-correlation-id") or "admin_integracoes_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _contexto_leitura(request: Request, auth_runtime: AuthSessionRuntime) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    if Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes:
        raise PermissionError("seguranca.integracao_gerenciar_exigido")
    return identidade.contexto(
        origem=request.headers.get("x-correlation-id") or "admin_integracoes_http_v1.listar",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _criar_servico_e_vault(session: Session, master_key: str | None) -> tuple[ServicoConfiguracoesExternas, EncryptedSQLAlchemySecretStore]:
    vault = EncryptedSQLAlchemySecretStore(session, master_key=master_key)
    service = ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, vault),
        auditoria=RepositorioAuditoriaSQLAlchemy(session),
    )
    return service, vault


def _executar_healthcheck_por_provedor(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    provedor: str,
    configuracao_id: str,
) -> HealthcheckOut:
    try:
        if provedor == "gemini":
            resultado_gemini = executar_healthcheck_gemini(
                session=session,
                secret_store=secret_store,
                contexto=contexto,
                configuracao_id=configuracao_id,
            )
            return HealthcheckOut(
                executado=True,
                suportado=True,
                provedor="gemini",
                evidencia_ref=resultado_gemini.evidencia_ref,
                detalhes={"model": resultado_gemini.model},
            )
        if provedor == "google_maps":
            resultado_google_maps = executar_healthcheck_google_maps(
                session=session,
                secret_store=secret_store,
                contexto=contexto,
                configuracao_id=configuracao_id,
            )
            return HealthcheckOut(
                executado=True,
                suportado=True,
                provedor="google_maps",
                evidencia_ref=resultado_google_maps.evidencia_ref,
                detalhes={
                    "endereco_origem": resultado_google_maps.endereco_origem,
                    "endereco_destino": resultado_google_maps.endereco_destino,
                    "distancia_metros": resultado_google_maps.distancia_metros,
                    "duracao_segundos": resultado_google_maps.duracao_segundos,
                    "browser_key_presente": resultado_google_maps.browser_key_presente,
                },
            )
        if provedor == "mercado_pago":
            resultado_mercado_pago = executar_healthcheck_mercado_pago(
                session=session,
                secret_store=secret_store,
                contexto=contexto,
                configuracao_id=configuracao_id,
            )
            return HealthcheckOut(
                executado=True,
                suportado=True,
                provedor="mercado_pago",
                evidencia_ref=resultado_mercado_pago.evidencia_ref,
                detalhes={"credencial_valida": resultado_mercado_pago.credencial_valida},
            )
        if provedor == "meta":
            resultado_meta = executar_healthcheck_meta(
                session=session,
                secret_store=secret_store,
                contexto=contexto,
                configuracao_id=configuracao_id,
            )
            return HealthcheckOut(
                executado=True,
                suportado=True,
                provedor="meta",
                evidencia_ref=resultado_meta.evidencia_ref,
                detalhes={
                    "servico": resultado_meta.servico,
                    "recurso_id": resultado_meta.recurso_id,
                    "rotulo": resultado_meta.rotulo,
                },
            )
    except ErroConfiguracaoServico as exc:
        return HealthcheckOut(
            executado=False,
            suportado=True,
            provedor=provedor,
            erro=str(exc),
        )
    except Exception:  # noqa: BLE001 - fronteira externa fail-closed
        return HealthcheckOut(
            executado=False,
            suportado=True,
            provedor=provedor,
            erro="healthcheck_externo_falhou",
        )

    return HealthcheckOut(
        executado=False,
        suportado=False,
        provedor=provedor,
        erro="healthcheck_nao_suportado_para_este_provedor",
    )


def build_admin_integracoes_router(
    *,
    session_factory: Callable[[], Session],
    auth_runtime: AuthSessionRuntime,
    master_key: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/integracoes", tags=["admin-integracoes"])
    app = AplicacaoIntegracoesAdminV1(session_factory, master_key=master_key)

    @router.get("", response_model=None)
    def listar(request: Request) -> IntegracoesListOut | JSONResponse:
        try:
            contexto = _contexto_leitura(request, auth_runtime)
            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)

                configuracoes = service.listar(contexto=contexto)
                configs_por_id = {c.configuracao_id: c for c in configuracoes}

                integracoes_out: list[IntegracaoOut] = []
                for spec in CATALOGO_V1.listar():
                    config_id = _config_id(spec.servico, spec.provedor)
                    configuracao = configs_por_id.get(config_id)
                    cat_out = _catalogo_item_out(spec)
                    config_out = None
                    if configuracao is not None:
                        prontidao = service.avaliar(contexto=contexto, configuracao_id=config_id)
                        config_out = ConfiguracaoSalvaOut(
                            configuracao_id=configuracao.configuracao_id,
                            servico=configuracao.servico,
                            provedor=configuracao.provedor,
                            conta_externa=configuracao.conta_externa,
                            ambiente=configuracao.ambiente.value,
                            parametros=configuracao.parametros,
                            credenciais_estado=_credenciais_estado(configuracao, spec),
                            habilitada=configuracao.habilitada,
                            homologada=configuracao.homologada,
                            evidencia_homologacao_ref=configuracao.evidencia_homologacao_ref,
                            versao=configuracao.versao,
                            prontidao=_prontidao_out(prontidao),
                        )
                    integracoes_out.append(IntegracaoOut(catalogo=cat_out, configuracao=config_out))

                return IntegracoesListOut(integracoes=integracoes_out)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro_integracoes(exc)

    @router.put("/{config_id}", response_model=None)
    def configurar(config_id: str, payload: IntegracoesPutIn, request: Request) -> ConfiguracaoSalvaOut | JSONResponse:
        try:
            contexto = _resolver_identidade_integracoes(request, auth_runtime)

            spec = CATALOGO_V1.obter(payload.servico, payload.provedor)
            if _config_id(spec.servico, spec.provedor) != config_id:
                return _tratar_erro_integracoes(ValueError("config_id_nao_confere_com_servico_provedor"))

            ambiente = AmbienteIntegracao(payload.ambiente.strip().casefold())

            parametros: Mapping[str, ValorParametro] = {p.nome: p.valor for p in payload.parametros}
            credenciais: Mapping[str, str] = {c.papel: c.valor for c in payload.credenciais if c.valor.strip()}

            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)

                existente = service.obter(contexto=contexto, configuracao_id=config_id) if config_id else None
                versao_esperada = payload.versao

                finalidades_atuais = dict(existente.credenciais) if existente else {}

                configuracao_salva, _ = app.salvar_configuracao(
                    contexto,
                    configuracao_id=config_id,
                    servico=spec.servico,
                    provedor=spec.provedor,
                    conta_externa=payload.conta_externa.strip(),
                    ambiente=ambiente,
                    parametros_publicos=parametros,
                    finalidades_atuais=finalidades_atuais,
                    novos_segredos=credenciais,
                    habilitada=payload.habilitada,
                    versao_esperada=versao_esperada,
                )

                prontidao = service.avaliar(contexto=contexto, configuracao_id=configuracao_salva.configuracao_id)
                return ConfiguracaoSalvaOut(
                    configuracao_id=configuracao_salva.configuracao_id,
                    servico=configuracao_salva.servico,
                    provedor=configuracao_salva.provedor,
                    conta_externa=configuracao_salva.conta_externa,
                    ambiente=configuracao_salva.ambiente.value,
                    parametros=configuracao_salva.parametros,
                    credenciais_estado=_credenciais_estado(configuracao_salva, spec),
                    habilitada=configuracao_salva.habilitada,
                    homologada=configuracao_salva.homologada,
                    evidencia_homologacao_ref=configuracao_salva.evidencia_homologacao_ref,
                    versao=configuracao_salva.versao,
                    prontidao=_prontidao_out(prontidao),
                )
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro_integracoes(exc)

    @router.post("/{config_id}/healthcheck", response_model=None)
    def healthcheck(config_id: str, request: Request) -> HealthcheckOut | JSONResponse:
        try:
            contexto = _resolver_identidade_integracoes(request, auth_runtime)
            with session_factory() as session:
                service, vault = _criar_servico_e_vault(session, master_key)
                configuracao = service.obter(contexto=contexto, configuracao_id=config_id)
                provedor = configuracao.provedor.strip().casefold()
                return _executar_healthcheck_por_provedor(
                    session=session,
                    secret_store=vault,
                    contexto=contexto,
                    provedor=provedor,
                    configuracao_id=config_id,
                )
        except ErroConfiguracaoServico as exc:
            return _tratar_erro_integracoes(exc)
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro_integracoes(exc)

    @router.post("/{config_id}/homologar", response_model=None)
    def homologar(config_id: str, payload: HomologarIn, request: Request) -> ConfiguracaoSalvaOut | JSONResponse:
        try:
            identidade = auth_runtime.resolver_identidade(request)
            if identidade is None:
                raise CredenciaisInvalidas("credenciais invalidas")
            if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
                raise PermissionError("seguranca.admin_acesso_exigido")
            if Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes:
                raise PermissionError("seguranca.integracao_gerenciar_exigido")
            if Papel.ADMINISTRADOR not in identidade.papeis:
                raise PermissionError("seguranca.administrador_exigido_para_homologar")
            _, elevado, _ = auth_runtime.admin_status(request)
            if not elevado:
                raise PermissionError("seguranca.admin_step_up_exigido")

            contexto = identidade.contexto(
                origem=request.headers.get("x-correlation-id") or "admin_integracoes_http_v1.homologar",
                correlation_id=request.headers.get("x-correlation-id") or None,
            )

            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)

                configuracao_atual = service.obter(contexto=contexto, configuracao_id=config_id)
                spec = CATALOGO_V1.obter(configuracao_atual.servico, configuracao_atual.provedor)

                homologada = app.homologar(
                    contexto,
                    configuracao_id=config_id,
                    evidencia_ref=payload.evidencia_ref.strip(),
                )

                prontidao = service.avaliar(contexto=contexto, configuracao_id=config_id)
                return ConfiguracaoSalvaOut(
                    configuracao_id=homologada.configuracao_id,
                    servico=homologada.servico,
                    provedor=homologada.provedor,
                    conta_externa=homologada.conta_externa,
                    ambiente=homologada.ambiente.value,
                    parametros=homologada.parametros,
                    credenciais_estado=_credenciais_estado(homologada, spec),
                    habilitada=homologada.habilitada,
                    homologada=homologada.homologada,
                    evidencia_homologacao_ref=homologada.evidencia_homologacao_ref,
                    versao=homologada.versao,
                    prontidao=_prontidao_out(prontidao),
                )
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro_integracoes(exc)

    return router
