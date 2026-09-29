from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.integracoes.platform_scope import (
    FM_PLATFORM_TENANT_ID,
    FM_PLATFORM_UNIT_ID,
)
from http_api.fmcc_platform_integrations import (
    build_fmcc_platform_integrations_router,
)
from infra.integracoes.modelos_orm import IntegrationConfigBase, ServicoExternoConfigORM
from infra.seguranca.modelos_orm import SecurityBase
from infra.seguranca.segredos_orm import SecretVaultBase

TOKEN = "fmcc-platform-integrations-token-0123456789abcdef"
MASTER_KEY = Fernet.generate_key().decode("ascii")


def _client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SecurityBase.metadata.create_all(engine)
    SecretVaultBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(
        build_fmcc_platform_integrations_router(
            session_factory=factory,
            control_plane_token=TOKEN,
            master_key=MASTER_KEY,
        )
    )
    return TestClient(app), factory


def _actor(*, age: timedelta = timedelta()) -> dict[str, str]:
    return {
        "user_id": "fm-command-owner",
        "role": "owner",
        "step_up_at": (datetime.now(timezone.utc) - age).isoformat(),
    }


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-Correlation-ID": "command-platform-integration-test",
    }


def test_command_lista_somente_integracoes_gerenciadas_pela_fm() -> None:
    client, _factory = _client()

    assert client.get("/v1/control-plane/fmcc/integrations").status_code == 401

    response = client.get(
        "/v1/control-plane/fmcc/integrations",
        headers=_headers(),
    )
    assert response.status_code == 200
    providers = {
        item["catalogo"]["provedor"]
        for item in response.json()["integracoes"]
    }
    assert providers == {"gemini", "google_maps"}
    assert all(
        item["catalogo"]["escopo_gestao"] == "platform_managed"
        for item in response.json()["integracoes"]
    )


def test_command_exige_step_up_fresco_para_escrita() -> None:
    client, _factory = _client()
    response = client.put(
        "/v1/control-plane/fmcc/integrations/ia.generativa--gemini",
        headers=_headers(),
        json={
            "actor": _actor(age=timedelta(minutes=16)),
            "configuracao": {
                "servico": "ia.generativa",
                "provedor": "gemini",
                "conta_externa": "principal",
                "ambiente": "homologacao",
                "parametros": [{"nome": "model", "valor": "gemini-test"}],
                "credenciais": [{"papel": "api_key", "valor": "secret-test"}],
                "habilitada": True,
                "versao": 0,
            },
        },
    )
    assert response.status_code == 403
    assert response.json()["error"] == "fmcc_control_plane.step_up_required"


def test_command_configura_e_homologa_gemini_no_escopo_canonico_fm() -> None:
    client, factory = _client()
    configured = client.put(
        "/v1/control-plane/fmcc/integrations/ia.generativa--gemini",
        headers=_headers(),
        json={
            "actor": _actor(),
            "configuracao": {
                "servico": "ia.generativa",
                "provedor": "gemini",
                "conta_externa": "principal",
                "ambiente": "homologacao",
                "parametros": [{"nome": "model", "valor": "gemini-test"}],
                "credenciais": [{"papel": "api_key", "valor": "secret-test"}],
                "habilitada": True,
                "versao": 0,
            },
        },
    )
    assert configured.status_code == 200
    assert configured.json()["prontidao"]["estado"] == "configurado"
    assert configured.json()["credenciais_estado"]["api_key"] is True

    homologated = client.post(
        "/v1/control-plane/fmcc/integrations/ia.generativa--gemini/homologar",
        headers=_headers(),
        json={
            "actor": _actor(),
            "evidencia_ref": "healthcheck://gemini/command-test",
        },
    )
    assert homologated.status_code == 200
    assert homologated.json()["homologada"] is True
    assert homologated.json()["prontidao"]["estado"] == "pronto"

    with factory() as session:
        row = session.scalar(
            select(ServicoExternoConfigORM).where(
                ServicoExternoConfigORM.configuracao_id
                == "ia.generativa--gemini"
            )
        )
        assert row is not None
        assert row.tenant_id == FM_PLATFORM_TENANT_ID
        assert row.unidade_id == FM_PLATFORM_UNIT_ID


def test_command_recusa_integracao_que_pertence_ao_cliente() -> None:
    client, _factory = _client()
    response = client.put(
        "/v1/control-plane/fmcc/integrations/pagamentos.pix--pagbank",
        headers=_headers(),
        json={
            "actor": _actor(),
            "configuracao": {
                "servico": "pagamentos.pix",
                "provedor": "pagbank",
                "conta_externa": "principal",
                "ambiente": "homologacao",
                "parametros": [
                    {
                        "nome": "notification_url",
                        "valor": "https://example.test/webhook",
                    }
                ],
                "credenciais": [{"papel": "api_token", "valor": "secret"}],
                "habilitada": True,
                "versao": 0,
            },
        },
    )
    assert response.status_code == 403
    assert (
        response.json()["error"]
        == "fmcc.integrations.tenant_managed_forbidden"
    )
