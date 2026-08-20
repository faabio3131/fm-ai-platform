"""Administração comercial das integrações externas no runtime Streamlit normal."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy.orm import Session

from core.integracoes.catalogo import CATALOGO_V1, EspecificacaoServico
from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from core.integracoes.servicos import ServicoConfiguracoesExternas
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini
from infra.integracoes.google_maps_browser_healthcheck import (
    obter_evidencia_confirmada_google_maps,
    preparar_healthcheck_browser_google_maps,
)
from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps
from infra.integracoes.meta_healthcheck import executar_healthcheck_meta
from infra.integracoes.mercado_pago_healthcheck import executar_healthcheck_mercado_pago
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
        ultima_evidencia_real = st.session_state.get(
            _key(spec, "last_real_healthcheck_evidence")
        )
        if spec.provedor == "gemini" and ultima_evidencia_real:
            st.success("Último healthcheck externo real do Gemini concluído com sucesso.")
            st.code(str(ultima_evidencia_real), language=None)
            st.caption(
                "Copie esta referência para o campo de evidência abaixo. Ela não contém a API key nem conteúdo sensível."
            )
        ultima_evidencia_maps = st.session_state.get(
            _key(spec, "last_real_maps_server_healthcheck_evidence")
        )
        if spec.provedor == "google_maps" and ultima_evidencia_maps:
            st.success("Geocoding API e Routes API foram validadas externamente com a chave de servidor.")
            st.code(str(ultima_evidencia_maps), language=None)
            st.caption(
                "Esta referência comprova somente o caminho servidor. A chave de navegador ainda precisa de prova real no navegador antes da homologação final."
            )
        ultima_evidencia_mp = st.session_state.get(
            _key(spec, "last_real_mercado_pago_access_evidence")
        )
        if spec.provedor == "mercado_pago" and ultima_evidencia_mp:
            st.success(
                "Acesso externo Mercado Pago e disponibilidade de PIX validados em modo somente leitura."
            )
            st.code(str(ultima_evidencia_mp), language=None)
            st.caption(
                "Esta evidência não criou pagamento nem movimentou dinheiro. A homologação final ainda exige criar um PIX controlado em ambiente de teste e validar status/webhook."
            )
        ultima_evidencia_meta = st.session_state.get(
            _key(spec, "last_real_meta_access_evidence")
        )
        if spec.provedor == "meta" and ultima_evidencia_meta:
            st.success(
                "Acesso externo Meta validado em modo somente leitura para o recurso configurado."
            )
            st.code(str(ultima_evidencia_meta), language=None)
            st.caption(
                "Esta evidência comprova autenticação e acesso ao ativo Meta. A homologação final ainda exige a prova prática específica do serviço: publicação controlada no Facebook/Instagram ou envio/webhook real no WhatsApp."
            )
        st.caption(
            "O status Ativo só deve ser registrado após validação real do provedor. "
            "Informe abaixo uma referência verificável da evidência (ticket, log sanitizado, "
            "execução de healthcheck ou registro de homologação). Não cole tokens, chaves, PINs "
            "ou qualquer outro segredo neste campo."
        )
        evidence_key = _key(spec, "homolog_evidence_ref")
        if spec.provedor == "google_maps":
            prefill_key = _key(spec, "maps_full_evidence_prefill")
            prefill = st.session_state.pop(prefill_key, None)
            if prefill and not str(st.session_state.get(evidence_key) or "").strip():
                st.session_state[evidence_key] = str(prefill)

            token_pendente = str(
                st.session_state.get(_key(spec, "maps_browser_proof_token")) or ""
            )
            evidencia_confirmada = obter_evidencia_confirmada_google_maps(token_pendente)
            if evidencia_confirmada:
                st.session_state[_key(spec, "last_real_maps_full_healthcheck_evidence")] = (
                    evidencia_confirmada
                )
                if not str(st.session_state.get(evidence_key) or "").strip():
                    st.session_state[evidence_key] = evidencia_confirmada
                st.session_state.pop(_key(spec, "maps_browser_proof_token"), None)

            evidencia_full = st.session_state.get(
                _key(spec, "last_real_maps_full_healthcheck_evidence")
            )
            if evidencia_full:
                st.success(
                    "Prova completa do Google Maps confirmada: servidor + Maps JavaScript API no navegador."
                )
                st.code(str(evidencia_full), language=None)
                st.caption(
                    "A referência foi preenchida automaticamente no campo de homologação abaixo."
                )

        evidence_ref = st.text_input(
            "Referência da evidência de homologação",
            value="",
            max_chars=512,
            placeholder="Ex.: healthcheck://meta/2026-08-17/resultado-123",
            key=evidence_key,
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

        if spec.provedor == "mercado_pago" and existing is not None:
            st.caption(
                "Este healthcheck consulta de verdade os meios de pagamento disponíveis usando o Access Token salvo no cofre. É somente leitura: não cria PIX, não cobra ninguém e não homologa automaticamente."
            )
            if st.button(
                "Testar acesso real Mercado Pago (sem criar pagamento)",
                key=_key(spec, "real_mercado_pago_access_healthcheck"),
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
                        "PIN administrativo inválido. O healthcheck externo do Mercado Pago não foi executado.",
                    )
                    st.rerun()
                try:
                    resultado = executar_healthcheck_mercado_pago(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                    )
                    st.session_state[
                        _key(spec, "last_real_mercado_pago_access_evidence")
                    ] = resultado.evidencia_ref
                    _set_flash(
                        spec,
                        "success",
                        "Mercado Pago respondeu com sucesso e o PIX está disponível para a credencial configurada. Nenhum pagamento foi criado. A prova transacional controlada continua pendente.",
                    )
                    st.rerun()
                except Exception:
                    _set_flash(
                        spec,
                        "error",
                        "O healthcheck externo do Mercado Pago falhou. A integração continua não homologada; revise ambiente, Access Token e disponibilidade do PIX. Nenhum segredo foi exposto e nenhum pagamento foi criado.",
                    )
                    st.rerun()

        if spec.provedor == "meta" and existing is not None:
            st.caption(
                "Este healthcheck faz uma chamada real e somente leitura à Graph API usando o Access Token e o App Secret salvos no cofre. Ele valida o ativo configurado sem publicar, enviar mensagem ou alterar dados externos."
            )
            if st.button(
                "Testar acesso real Meta (somente leitura)",
                key=_key(spec, "real_meta_access_healthcheck"),
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
                        "PIN administrativo inválido. O healthcheck externo Meta não foi executado.",
                    )
                    st.rerun()
                try:
                    resultado = executar_healthcheck_meta(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                    )
                    st.session_state[_key(spec, "last_real_meta_access_evidence")] = (
                        resultado.evidencia_ref
                    )
                    _set_flash(
                        spec,
                        "success",
                        "Acesso externo Meta validado com sucesso em modo somente leitura. Nenhuma publicação, mensagem ou alteração foi feita. A prova prática específica do serviço continua pendente antes da homologação final.",
                    )
                    st.rerun()
                except Exception:
                    _set_flash(
                        spec,
                        "error",
                        "O healthcheck externo Meta falhou. A integração continua não homologada; revise o recurso configurado, permissões, token, App Secret e versão da Graph API. Nenhum segredo foi exposto.",
                    )
                    st.rerun()

        if spec.provedor == "google_maps" and existing is not None:
            st.caption(
                "O teste abaixo chama de verdade a Geocoding API e a Routes API usando somente a Server API Key salva no cofre. "
                "Ele também confirma que a Browser API Key existe e pode ser resolvida, mas não a considera externamente homologada no navegador."
            )
            if st.button(
                "Testar Google Maps real (servidor)",
                key=_key(spec, "real_maps_server_healthcheck"),
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
                        "PIN administrativo inválido. O healthcheck externo do Google Maps não foi executado.",
                    )
                    st.rerun()
                try:
                    resultado = executar_healthcheck_google_maps(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                    )
                    st.session_state[_key(spec, "last_real_maps_server_healthcheck_evidence")] = (
                        resultado.evidencia_ref
                    )
                    _set_flash(
                        spec,
                        "success",
                        f"Google Maps servidor validado de ponta a ponta: geocodificação + rota real, "
                        f"{resultado.distancia_metros / 1000:.1f} km e ETA aproximado de "
                        f"{max(1, (resultado.duracao_segundos + 59) // 60)} min. "
                        "A chave de navegador ainda precisa de prova real no navegador antes da homologação final.",
                    )
                    st.rerun()
                except Exception:
                    _set_flash(
                        spec,
                        "error",
                        "O healthcheck externo real do Google Maps falhou. A integração continua não homologada; revise habilitação das APIs, restrições das chaves e faturamento do projeto. Nenhum segredo foi exposto.",
                    )
                    st.rerun()

        if spec.provedor == "google_maps" and existing is not None:
            evidencia_servidor = st.session_state.get(
                _key(spec, "last_real_maps_server_healthcheck_evidence")
            )
            st.caption(
                "Depois do teste servidor, valide aqui a Browser API Key carregando um mapa real pela Maps JavaScript API no navegador atual. "
                "A evidencia final so aparece se os tiles do mapa forem realmente carregados."
            )
            if st.button(
                "Testar Google Maps real (navegador)",
                key=_key(spec, "real_maps_browser_healthcheck"),
                disabled=not bool(evidencia_servidor),
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
                        "PIN administrativo invalido. O teste real do navegador nao foi iniciado.",
                    )
                    st.rerun()
                try:
                    preparacao = preparar_healthcheck_browser_google_maps(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                        evidencia_servidor=str(evidencia_servidor or ""),
                    )
                    st.session_state[_key(spec, "maps_browser_proof_token")] = preparacao.token
                    st.session_state.pop(
                        _key(spec, "last_real_maps_full_healthcheck_evidence"), None
                    )
                    st.info(
                        "O mapa abaixo e a prova real da Browser API Key. Quando ficar verde, a evidencia sera confirmada pelo servidor local. "
                        "Use o botao Concluir teste logo abaixo; o campo de homologacao sera preenchido sem copiar manualmente."
                    )
                    components.iframe(preparacao.url, height=520, scrolling=False)
                except Exception:
                    st.error(
                        "Nao foi possivel preparar o teste real do navegador. A integracao continua nao homologada; revise a Browser API Key e tente novamente. Nenhum segredo foi exposto."
                    )

        if spec.provedor == "google_maps" and existing is not None:
            token_pendente = str(
                st.session_state.get(_key(spec, "maps_browser_proof_token")) or ""
            )
            if token_pendente:
                st.caption(
                    "Depois que o mapa ficar verde, conclua a prova para trazer a evidência ao painel automaticamente."
                )
                if st.button(
                    "Concluir teste e preencher evidência",
                    key=_key(spec, "confirm_maps_browser_healthcheck"),
                ):
                    evidencia_confirmada = obter_evidencia_confirmada_google_maps(
                        token_pendente
                    )
                    if evidencia_confirmada:
                        st.session_state[
                            _key(spec, "last_real_maps_full_healthcheck_evidence")
                        ] = evidencia_confirmada
                        st.session_state[
                            _key(spec, "maps_full_evidence_prefill")
                        ] = evidencia_confirmada
                        st.session_state.pop(
                            _key(spec, "maps_browser_proof_token"), None
                        )
                        _set_flash(
                            spec,
                            "success",
                            "Prova completa do Google Maps confirmada. A referência de homologação foi preenchida automaticamente.",
                        )
                        st.rerun()
                    else:
                        st.warning(
                            "A prova do navegador ainda não foi confirmada. Aguarde o mapa ficar verde e tente concluir novamente."
                        )

        if spec.provedor == "gemini" and existing is not None:
            st.caption(
                "O teste abaixo faz uma chamada mínima real ao Google Gemini usando somente a credencial já salva no cofre. "
                "Ele valida o modelo configurado, gera uma referência sanitizada e não homologa automaticamente."
            )
            if st.button(
                "Testar Gemini real antes de homologar",
                key=_key(spec, "real_healthcheck"),
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
                        "PIN administrativo inválido. O healthcheck externo não foi executado.",
                    )
                    st.rerun()
                try:
                    resultado = executar_healthcheck_gemini(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                    )
                    st.session_state[_key(spec, "last_real_healthcheck_evidence")] = (
                        resultado.evidencia_ref
                    )
                    _set_flash(
                        spec,
                        "success",
                        f"Healthcheck externo real concluído com sucesso usando o modelo {resultado.model}. "
                        "A referência sanitizada foi gerada abaixo para a homologação.",
                    )
                    st.rerun()
                except Exception:
                    _set_flash(
                        spec,
                        "error",
                        "O healthcheck externo real do Gemini falhou. A integração continua não homologada; revise o modelo, a credencial e a disponibilidade da conta. Nenhum segredo foi exposto.",
                    )
                    st.rerun()

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
            except Exception:
                session.rollback()
                _set_flash(
                    spec,
                    "error",
                    "Não foi possível salvar a configuração. Nenhuma informação interna foi exposta; PIN e valores sensíveis digitados foram limpos. Revise os dados e tente novamente.",
                )
                st.rerun()

        if c_validate.button("Validar configuração", key=_key(spec, "validate")):
            if existing is None:
                st.warning(
                    "Esta integração ainda não possui configuração salva. Preencha os "
                    "parâmetros e credenciais necessários e use Salvar / atualizar antes "
                    "de validar a prontidão."
                )
            else:
                try:
                    readiness = service.avaliar(
                        contexto=contexto, configuracao_id=config_id
                    )
                    if readiness.faltam_parametros:
                        st.error(
                            "Faltam parâmetros: " + ", ".join(readiness.faltam_parametros)
                        )
                    elif readiness.faltam_finalidades or readiness.faltam_credenciais:
                        missing = (
                            *readiness.faltam_finalidades,
                            *readiness.faltam_credenciais,
                        )
                        st.error(
                            "Faltam credenciais: "
                            + ", ".join(sorted(set(missing)))
                        )
                    else:
                        st.success(
                            "Configuração estrutural e credenciais válidas no control plane. "
                            "A homologação externa continua pendente até existir evidência real."
                        )
                except ErroConfiguracaoServico:
                    st.error(
                        "A configuração salva não pôde ser validada. Revise os dados da "
                        "integração e salve novamente antes de prosseguir."
                    )
                except Exception:
                    st.error(
                        "Ocorreu uma falha inesperada durante a validação. Nenhuma informação interna foi exposta; tente novamente ou consulte os logs administrativos sanitizados."
                    )

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
            except Exception:
                session.rollback()
                _set_flash(
                    spec,
                    "error",
                    "Não foi possível homologar. Nenhuma informação interna foi exposta; o PIN foi consumido e limpo. Revise a configuração e a evidência antes de tentar novamente.",
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