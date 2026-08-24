from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import AmbienteIntegracao, ServicoConfiguracoesExternas
from core.integracoes.modelos import ConfiguracaoServicoExterno
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import CredenciaisInvalidas
from core.seguranca.permissoes import Papel
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes import (
    IntegrationConfigBase,
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import SecurityBase
from infra.streamlit_app import auth_ui

_TENANT = "tenant-t1"
_OTHER_TENANT = "tenant-t2"
_UNIT_A = "unidade-a"
_UNIT_B = "unidade-b"
_UNIT_C = "unidade-c-nao-autorizada"


def _identity(
    *,
    tenant_id: str = _TENANT,
    default_unit: str = _UNIT_A,
    allowed_units: frozenset[str] = frozenset({_UNIT_A, _UNIT_B}),
    role: Papel = Papel.CAIXA,
) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="user-af01",
        email="af01@example.com",
        senha_hash="hash-de-teste",
        tenant_id=tenant_id,
        unidade_id=default_unit,
        papeis=frozenset({role}),
        unidades_permitidas=allowed_units,
    )


def _settings(
    *,
    tenant_id: str = _TENANT,
    unidade_id: str = _UNIT_B,
    environment: RuntimeEnvironment = RuntimeEnvironment.TEST,
) -> RuntimeSettings:
    return RuntimeSettings(
        environment=environment,
        database_url=(
            "postgresql://runtime-comercial-inacessivel/af01"
            if environment in {RuntimeEnvironment.STAGING, RuntimeEnvironment.PRODUCTION}
            else "sqlite:///:memory:"
        ),
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )


def test_af01_a_single_unit_uses_authorized_default_as_active_scope() -> None:
    identity = _identity(allowed_units=frozenset({_UNIT_A}))

    active_identity = identity.no_escopo_ativo(
        tenant_id=_TENANT,
        unidade_id=_UNIT_A,
    )
    context = active_identity.contexto(
        origem="af01-a",
        correlation_id="corr-af01-a",
    )

    assert active_identity is identity
    assert active_identity.unidade_id == _UNIT_A
    assert active_identity.unidades_permitidas == frozenset({_UNIT_A})
    assert context.tenant_id == _TENANT
    assert context.unidade_id == _UNIT_A


def test_af01_b_multiunit_rebinds_default_a_to_active_b_without_expanding_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_identity = _identity()

    active_identity = default_identity.no_escopo_ativo(
        tenant_id=_TENANT,
        unidade_id=_UNIT_B,
    )
    context = active_identity.contexto(
        origem="af01-b",
        correlation_id="corr-af01-b",
    )
    sidebar_messages: list[str] = []
    monkeypatch.setattr(auth_ui.st, "success", lambda message: None)
    monkeypatch.setattr(auth_ui.st, "info", sidebar_messages.append)
    monkeypatch.setattr(auth_ui.st, "caption", lambda message: None)
    auth_ui.render_identity_sidebar(active_identity, _settings())

    assert default_identity.unidade_id == _UNIT_A
    assert active_identity is not default_identity
    assert active_identity.tenant_id == _TENANT
    assert active_identity.unidade_id == _UNIT_B
    assert active_identity.unidades_permitidas == frozenset({_UNIT_A, _UNIT_B})
    assert context.unidade_id == _UNIT_B
    assert sidebar_messages == [f"🏪 **Unidade ativa:**\n{_UNIT_B}"]


def test_af01_c_unauthorized_unit_fails_closed() -> None:
    identity = _identity()

    with pytest.raises(CredenciaisInvalidas, match="credenciais invalidas"):
        identity.no_escopo_ativo(
            tenant_id=_TENANT,
            unidade_id=_UNIT_C,
        )

    assert identity.unidade_id == _UNIT_A
    assert _UNIT_C not in identity.unidades_permitidas


def test_af01_d_wrong_tenant_fails_closed_and_preserves_original_tenant() -> None:
    identity = _identity()

    with pytest.raises(CredenciaisInvalidas, match="credenciais invalidas"):
        identity.no_escopo_ativo(
            tenant_id=_OTHER_TENANT,
            unidade_id=_UNIT_B,
        )

    assert identity.tenant_id == _TENANT
    assert identity.unidade_id == _UNIT_A


def test_af01_e_reload_recreates_session_without_falling_back_to_default_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_identity = _identity()
    initial_state = {
        auth_ui._SESSION_KEY: initial_identity,
        auth_ui._SENSITIVE_AUTH_KEY: {
            "usuario_id": initial_identity.usuario_id,
            "last_activity_at": datetime(2026, 8, 23, tzinfo=timezone.utc),
        },
    }
    monkeypatch.setattr(auth_ui.st, "session_state", initial_state)

    first_lifecycle = auth_ui.require_authentication(
        session_factory=lambda: pytest.fail("sessao SQL nao deveria ser aberta"),
        settings=_settings(),
    )

    assert first_lifecycle.unidade_id == _UNIT_B
    assert auth_ui._SENSITIVE_AUTH_KEY not in initial_state

    recreated_state = {auth_ui._SESSION_KEY: replace(first_lifecycle)}
    monkeypatch.setattr(auth_ui.st, "session_state", recreated_state)
    after_reload = auth_ui.require_authentication(
        session_factory=lambda: pytest.fail("sessao SQL nao deveria ser aberta"),
        settings=_settings(),
    )
    context_after_reload = after_reload.contexto(
        origem="af01-e-reload",
        correlation_id="corr-af01-e",
    )

    assert after_reload.unidade_id == _UNIT_B
    assert context_after_reload.unidade_id == _UNIT_B
    assert recreated_state[auth_ui._SESSION_KEY] is after_reload
    assert after_reload.unidade_id != _UNIT_A


class _CapturingConfigurationRepository(
    RepositorioConfiguracoesExternasSQLAlchemy
):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.obter_scopes: list[tuple[str, str, str]] = []

    def obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        configuracao_id: str,
    ) -> ConfiguracaoServicoExterno | None:
        self.obter_scopes.append((tenant_id, unidade_id, configuracao_id))
        return super().obter(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            configuracao_id=configuracao_id,
        )


def test_af01_f_downstream_service_and_sqlalchemy_repository_keep_active_unit_b() -> None:
    engine = create_engine("sqlite:///:memory:")
    IntegrationConfigBase.metadata.create_all(engine)

    with Session(engine) as session:
        repository = _CapturingConfigurationRepository(session)
        service = ServicoConfiguracoesExternas(
            repositorio=repository,
            prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(
                session,
                ReferenceSecretStore(),
            ),
            auditoria=RepositorioAuditoriaEmMemoria(),
        )
        admin_identity = _identity(role=Papel.ADMINISTRADOR)

        for unit_id in (_UNIT_A, _UNIT_B):
            context = admin_identity.no_escopo_ativo(
                tenant_id=_TENANT,
                unidade_id=unit_id,
            ).contexto(
                origem=f"af01-f-{unit_id}",
                correlation_id=f"corr-af01-f-{unit_id}",
            )
            service.configurar(
                contexto=context,
                configuracao_id="maps-principal",
                servico="mapas",
                provedor="google_maps",
                conta_externa=f"billing-{unit_id}",
                ambiente=AmbienteIntegracao.HOMOLOGACAO,
                parametros_publicos={
                    "origin_address": f"Rua {unit_id}",
                    "country_code": "BR",
                    "language": "pt-BR",
                    "currency": "BRL",
                },
                finalidades_credenciais={
                    "browser_api_key": "maps_browser_api_key",
                    "server_api_key": "maps_server_api_key",
                },
                habilitada=True,
                versao_esperada=0,
            )

        active_identity = admin_identity.no_escopo_ativo(
            tenant_id=_TENANT,
            unidade_id=_UNIT_B,
        )
        active_context = active_identity.contexto(
            origem="af01-f-consumer",
            correlation_id="corr-af01-f-consumer",
        )
        repository.obter_scopes.clear()

        configuration = service.obter(
            contexto=active_context,
            configuracao_id="maps-principal",
        )

        assert active_identity.unidade_id == _UNIT_B
        assert active_context.unidade_id == _UNIT_B
        assert repository.obter_scopes == [(_TENANT, _UNIT_B, "maps-principal")]
        assert configuration.unidade_id == _UNIT_B
        assert configuration.conta_externa == f"billing-{_UNIT_B}"


def test_af01_g_legitimate_default_is_resolved_and_invalid_default_fails_closed() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)

    with Session(engine) as session:
        repository = RepositorioIdentidadesSQLAlchemy(session)
        persisted_identity = repository.criar_usuario(
            usuario_id="user-af01-default",
            email="af01-default@example.com",
            password="senha-af01-segura",
            tenant_id=_TENANT,
            unidade_padrao_id=_UNIT_A,
            papeis=(Papel.CAIXA,),
            unidades_permitidas=(_UNIT_A, _UNIT_B),
        )

        legitimate_default = persisted_identity.no_escopo_ativo(
            tenant_id=persisted_identity.tenant_id,
            unidade_id=persisted_identity.unidade_id,
        )

        assert legitimate_default.unidade_id == _UNIT_A
        assert legitimate_default.unidade_id in legitimate_default.unidades_permitidas
        assert legitimate_default.contexto(origem="af01-g").unidade_id == _UNIT_A

        with pytest.raises(
            ValueError,
            match="unidade ativa deve estar no escopo do usuario",
        ):
            replace(
                persisted_identity,
                unidade_id=_UNIT_C,
                unidades_permitidas=frozenset({_UNIT_A, _UNIT_B}),
            )


def test_af01_h_tampered_ui_scope_is_rejected_and_session_is_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StreamlitStop(RuntimeError):
        pass

    def stop() -> None:
        raise _StreamlitStop

    identity = _identity()
    session_state = {auth_ui._SESSION_KEY: identity}
    monkeypatch.setattr(auth_ui.st, "session_state", session_state)
    monkeypatch.setattr(auth_ui.st, "title", lambda message: None)
    monkeypatch.setattr(auth_ui.st, "caption", lambda message: None)
    monkeypatch.setattr(auth_ui.st, "form", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(auth_ui.st, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        auth_ui.st,
        "form_submit_button",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(auth_ui.st, "stop", stop)
    monkeypatch.setattr(auth_ui, "_render_login_autofill_guard", lambda: None)

    with pytest.raises(CredenciaisInvalidas, match="credenciais invalidas"):
        identity.no_escopo_ativo(
            tenant_id=_TENANT,
            unidade_id=_UNIT_C,
        )

    with pytest.raises(_StreamlitStop):
        auth_ui.require_authentication(
            session_factory=lambda: pytest.fail("sessao SQL nao deveria ser aberta"),
            settings=_settings(
                unidade_id=_UNIT_C,
                environment=RuntimeEnvironment.PRODUCTION,
            ),
        )

    assert auth_ui._SESSION_KEY not in session_state
    assert _UNIT_C not in identity.unidades_permitidas
