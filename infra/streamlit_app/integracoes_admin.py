"""Administração comercial das integrações externas no runtime Streamlit normal."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st
from sqlalchemy.orm import Session

from core.integracoes.catalogo import CATALOGO_V1, EspecificacaoServico
from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from core.integracoes.servicos import ServicoConfiguracoesExternas
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes.repositorio_sqlalchemy import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.streamlit_app.auth_ui import verify_sensitive_pin


_LABELS = {
    ("social.facebook", "meta"): "Meta · Facebook",
    ("social.instagram", "meta"): "Meta · Instagram Business",
    ("mensageria.whatsapp", "meta"): "Meta · WhatsApp Business",
    ("mapas", "google_maps"): "Google Maps",
    ("pagamentos.pix", "pagbank"): "PagBank · PIX",
    ("pagamentos.pix", "mercado_pago"): "Mercado Pago · PIX",
    ("ia.generativa", "gemini"): "Google Gemini",
}

_PARAM_LABELS = {
    "page_id": "Facebook Page ID",
    "facebook_page_id": "Facebook Page ID",
    "business_account_id": "Business Account ID",
    "app_id": "App ID",
    "phone_number_id": "WhatsApp Phone Number ID",
    "origin_address": "Endereço de origem",
    "country_code": "País (ex.: BR)",
    "language": "Idioma (ex.: pt-BR)",
    "currency": "Moeda (ex.: BRL)",
    "notification_url": "URL de notificação / webhook",
    "model": "Modelo",
    "region": "Região",
}

_SECRET_LABELS = {
    "access_token": "Access Token",
    "app_secret": "App Secret",
    "webhook_verify_token": "Webhook Verify Token",
    "browser_api_key": "Browser API Key",
    "server_api_key": "Server API Key",
    "api_token": "API Token",
    "webhook_secret": "Webhook Secret",
    "api_key": "API Key",
}

_STATUS_LABELS = {
    "desativado": "Configurado / desativado",
    "bloqueado": "Erro de configuração",
    "configurado": "Homologação pendente",
    "pronto": "Ativo",
}


def _config_id(spec: EspecificacaoServico) -> str:
    return f"{spec.servico}--{spec.provedor}"


def _purpose(spec: EspecificacaoServico, role: str) -> str:
    prefix = spec.servico.replace(".", "_").replace("-", "_")
    return f"{prefix}_{role}"


def _key(spec: EspecificacaoServico, suffix: str) -> str:
    base = f"{spec.servico}_{spec.provedor}_{suffix}"
    return base.replace(".", "_").replace("-", "_")


def _status_text(service: ServicoConfiguracoesExternas, contexto: Any, config_id: str) -> str:
    try:
        status = service.avaliar(contexto=contexto, configuracao_id=config_id)
    except ErroConfiguracaoServico:
        return "Não configurado"
    return _STATUS_LABELS.get(status.estado.value, status.estado.value)


def _critical_pin_ok(
    *,
    identidade: IdentidadeUsuario,
    pin: str,
    session_factory: Callable[[], Session],
) -> bool:
    return verify_sensitive_pin(
        identity=identidade,
        pin=pin,
        session_factory=session_factory,
        required_permission=Permissao.INTEGRACAO_GERENCIAR,
    )


def _sensitive_nonce(spec: EspecificacaoServico) -> int:
    raw = st.session_state.get(_key(spec, "sensitive_nonce"), 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _consume_sensitive_inputs(spec: EspecificacaoServico) -> None:
    """Invalida PIN/segredos digitados para impedir reutilização entre ações."""

    nonce_key = _key(spec, "sensitive_nonce")
    st.session_state[nonce_key] = _sensitive_nonce(spec) + 1


def _set_flash(spec: EspecificacaoServico, level: str, message: str) -> None:
    st.session_state[_key(spec, "critical_flash")] = (level, message)


def _render_flash(spec: EspecificacaoServico) -> None:
    flash = st.session_state.pop(_key(spec, "critical_flash"), None)
    if not isinstance(flash, tuple) or len(flash) != 2:
        return
    level, message = flash
    if level == "success":
        st.success(str(message))
    elif level == "error":
        st.error(str(message))
    else:
        st.info(str(message))


def _render_one(
    *,
    spec: EspecificacaoServico,
    session: Session,
    session_factory: Callable[[], Session],
    identidade: IdentidadeUsuario,
    service: ServicoConfiguracoesExternas,
    credentials: ServicoCredenciaisReferenciadas,
    vault: EncryptedSQLAlchemySecretStore,
) -> None:
    contexto = identidade.contexto(origem="streamlit.integracoes_admin")
    config_id = _config_id(spec)
    existing = None
    try:
        existing = service.obter(contexto=contexto, configuracao_id=config_id)
    except ErroConfiguracaoServico:
        pass

    label = _LABELS.get((spec.servico, spec.provedor), f"{spec.servico} · {spec.provedor}")
    status = _status_text(service, contexto, config_id)
    with st.expander(f"{label} — {status}", expanded=False):
        _render_flash(spec)
        st.caption(
            "Credenciais são cifradas antes de chegar ao banco. O valor salvo nunca é "
            "reexibido; para trocar uma credencial, informe um novo valor."
        )

        current_params = existing.parametros if existing else {}
        conta_externa = st.text_input(
            "Conta / identificação externa",
            value=existing.conta_externa if existing else "principal",
            key=_key(spec, "conta"),
        )
        ambiente_atual = existing.ambiente if existing else AmbienteIntegracao.SANDBOX
        ambiente = AmbienteIntegracao(
            st.selectbox(
                "Ambiente",
                options=[item.value for item in AmbienteIntegracao],
                index=[item.value for item in AmbienteIntegracao].index(ambiente_atual.value),
                key=_key(spec, "ambiente"),
            )
        )
        habilitada = st.checkbox(
            "Integração habilitada",
            value=existing.habilitada if existing else False,
            key=_key(spec, "habilitada"),
        )

        st.markdown("**Parâmetros da integração**")
        public_values: dict[str, str] = {}
        for name in sorted(spec.parametros_obrigatorios):
            public_values[name] = st.text_input(
                _PARAM_LABELS.get(name, name),
                value=str(current_params.get(name) or ""),
                key=_key(spec, f"param_{name}"),
            )

        sensitive_nonce = _sensitive_nonce(spec)
        st.markdown("**Credenciais protegidas**")
        new_secrets: dict[str, str] = {}
        current_purposes: dict[str, str] = {}
        for role in sorted(spec.credenciais_obrigatorias):
            purpose = _purpose(spec, role)
            current = credentials.atual(
                contexto=contexto,
                provedor=spec.provedor,
                finalidade=purpose,
            )
            if current is not None:
                current_purposes[role] = purpose
            state = "Configurada" if current is not None else "Não configurada"
            new_secrets[role] = st.text_input(
                f"{_SECRET_LABELS.get(role, role)} · {state}",
                value="",
                type="password",
                autocomplete="new-password",
                placeholder="Deixe vazio para manter a credencial atual",
                key=_key(spec, f"secret_{role}_{sensitive_nonce}"),
            )

        st.markdown("**Homologação**")
        st.caption(
            "O status Ativo só deve ser registrado após validação real do provedor. "
            "Informe abaixo uma referência verificável da evidência (ticket, log sanitizado, "
            "execução de healthcheck ou registro de homologação). Não cole tokens, chaves, PINs "
            "ou qualquer outro segredo neste campo."
        )
        evidence_ref = st.text_input(
            "Referência da evidência de homologação",
            value="",
            max_chars=512,
            placeholder="Ex.: healthcheck://meta/2026-08-17/resultado-123",
            key=_key(spec, "homolog_evidence_ref"),
        )

        st.markdown("**Confirmação para ação crítica**")
        st.caption(
            "Salvar credenciais/configurações ou homologar exige seu PIN administrativo "
            "individual novamente, mesmo com a área já desbloqueada. O PIN é consumido "
            "pela ação e não pode ser reutilizado no próximo clique."
        )
        critical_pin = st.text_input(
            "PIN administrativo",
            value="",
            type="password",
            autocomplete="one-time-code",
            max_chars=8,
            key=_key(spec, f"critical_pin_{sensitive_nonce}"),
        )

        c_save, c_validate, c_homolog = st.columns(3)
        if c_save.button("Salvar / atualizar", key=_key(spec, "save"), type="primary"):
            pin_ok = _critical_pin_ok(
                identidade=identidade,
                pin=critical_pin,
                session_factory=session_factory,
            )
            _consume_sensitive_inputs(spec)
            if not pin_ok:
                _set_flash(
                    spec,
                    "error",
                    "PIN administrativo inválido. Nenhuma alteração foi salva. Digite o PIN novamente para uma nova tentativa.",
                )
                st.rerun()
            try:
                finalidades = dict(current_purposes)
                credencial_rotacionada = False
                for role, value in new_secrets.items():
                    if not value.strip():
                        continue
                    credencial_rotacionada = True
                    purpose = _purpose(spec, role)
                    reference = vault.armazenar(
                        contexto=contexto,
                        provedor=spec.provedor,
                        finalidade=purpose,
                        valor=value,
                    )
                    credentials.rotacionar(
                        contexto=contexto,
                        provedor=spec.provedor,
                        finalidade=purpose,
                        nova_referencia=reference,
                    )
                    finalidades[role] = purpose

                service.configurar(
                    contexto=contexto,
                    configuracao_id=config_id,
                    servico=spec.servico,
                    provedor=spec.provedor,
                    conta_externa=conta_externa or "principal",
                    ambiente=ambiente,
                    parametros_publicos=public_values,
                    finalidades_credenciais=finalidades,
                    habilitada=habilitada,
                    versao_esperada=existing.versao if existing else 0,
                    forcar_rehomologacao=credencial_rotacionada,
                )
                session.commit()
                mensagem = (
                    "Configuração salva com segurança. Como uma credencial foi alterada, "
                    "a homologação anterior foi invalidada e deve ser refeita com nova evidência."
                    if credencial_rotacionada and existing is not None and existing.homologada
                    else "Configuração salva com segurança. PIN e valores sensíveis digitados foram limpos da sessão de entrada."
                )
                _set_flash(spec, "success", mensagem)
                st.rerun()
            except Exception as exc:
                session.rollback()
                _set_flash(
                    spec,
                    "error",
                    f"Não foi possível salvar a configuração: {type(exc).__name__}. PIN e valores sensíveis digitados foram limpos.",
                )
                st.rerun()

        if c_validate.button("Validar configuração", key=_key(spec, "validate")):
            try:
                readiness = service.avaliar(contexto=contexto, configuracao_id=config_id)
                if readiness.faltam_parametros:
                    st.error("Faltam parâmetros: " + ", ".join(readiness.faltam_parametros))
                elif readiness.faltam_finalidades or readiness.faltam_credenciais:
                    missing = (*readiness.faltam_finalidades, *readiness.faltam_credenciais)
                    st.error("Faltam credenciais: " + ", ".join(sorted(set(missing))))
                else:
                    st.success(
                        "Configuração estrutural e credenciais válidas no control plane. "
                        "A homologação externa continua pendente até existir evidência real."
                    )
            except Exception as exc:
                st.error(f"Falha de validação: {type(exc).__name__}")

        can_homologate = (
            Papel.ADMINISTRADOR in identidade.papeis
            and existing is not None
            and bool(evidence_ref.strip())
        )
        if c_homolog.button(
            "Homologar",
            key=_key(spec, "homolog"),
            disabled=not can_homologate,
        ):
            pin_ok = _critical_pin_ok(
                identidade=identidade,
                pin=critical_pin,
                session_factory=session_factory,
            )
            _consume_sensitive_inputs(spec)
            if not pin_ok:
                _set_flash(
                    spec,
                    "error",
                    "PIN administrativo inválido. A homologação não foi registrada. Digite o PIN novamente para uma nova tentativa.",
                )
                st.rerun()
            try:
                current = service.obter(contexto=contexto, configuracao_id=config_id)
                service.registrar_homologacao(
                    contexto=contexto,
                    configuracao_id=config_id,
                    evidencia_ref=evidence_ref.strip(),
                    versao_esperada=current.versao,
                )
                session.commit()
                _set_flash(
                    spec,
                    "success",
                    "Homologação registrada com evidência e auditoria. O PIN foi consumido e limpo.",
                )
                st.rerun()
            except Exception as exc:
                session.rollback()
                _set_flash(
                    spec,
                    "error",
                    f"Não foi possível homologar: {type(exc).__name__}. O PIN foi consumido e limpo.",
                )
                st.rerun()


def render_integracoes_admin(
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    """Renderiza a central real de integrações para o tenant/unidade autenticado."""

    st.header("🔐 Integrações e Credenciais")
    st.caption(
        "Configure provedores externos do estabelecimento. Cada configuração é isolada "
        "pelo tenant e pela unidade autenticados."
    )
    if Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes:
        st.error("Seu usuário não possui permissão para gerenciar integrações.")
        return

    session = session_factory()
    try:
        try:
            vault = EncryptedSQLAlchemySecretStore(session)
        except RuntimeError as exc:
            st.error(str(exc))
            st.info(
                "A chave mestra é configuração única da infraestrutura do servidor; "
                "as credenciais de cada cliente continuam sendo cadastradas somente aqui."
            )
            return

        repo = RepositorioConfiguracoesExternasSQLAlchemy(session)
        readiness = ProntidaoCredenciaisSQLAlchemy(session, vault)
        audit = RepositorioAuditoriaSQLAlchemy(session)
        service = ServicoConfiguracoesExternas(
            repositorio=repo,
            prontidao_credenciais=readiness,
            auditoria=audit,
        )
        credentials = ServicoCredenciaisReferenciadas(session, vault)

        for spec in CATALOGO_V1.listar():
            _render_one(
                spec=spec,
                session=session,
                session_factory=session_factory,
                identidade=identidade,
                service=service,
                credentials=credentials,
                vault=vault,
            )
    finally:
        session.close()
