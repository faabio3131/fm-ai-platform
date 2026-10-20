from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.fiscal.modelos_orm import FiscalArchiveORM, FiscalDocumentProjectionORM
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.segredos_orm import SegredoIntegracaoORM
from kordena_fiscal.domain import Cnpj, ElectronicInvoiceModel
from kordena_fiscal.operations import FakeFiscalOperationsGateway
from kordena_fiscal.xml import AccessKeyInput, build_access_key
from migrations.runner import run_migrations

SESSION_SECRET = "wp031j-session-secret-01234567890123456789"
SENHA = "Senha-WP031J-Segura-123"
TENANT = "tenant-wp031j"
UNIDADE = "unidade-wp031j"
OUTRA_UNIDADE = "unidade-wp031j-b"
ADMIN_EMAIL = "admin-wp031j@example.com"
NOW = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)


def _infra(monkeypatch, *, gateway_factory=None) -> TestClient:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        identities = RepositorioIdentidadesSQLAlchemy(session)
        identities.criar_usuario(
            usuario_id="admin-wp031j",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE, OUTRA_UNIDADE),
            acesso_admin_sensivel=True,
        )
        identities.criar_usuario(
            usuario_id="gerente-wp031j",
            email="gerente-wp031j@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
            acesso_admin_sensivel=False,
        )
        session.add_all(
            [
                FiscalDocumentProjectionORM(
                    document_id="nfce-active-unit",
                    tenant_id=TENANT,
                    unit_id=UNIDADE,
                    environment="homologation",
                    source_type="venda",
                    source_id="sale-1",
                    document_kind="nfce",
                    state="authorized",
                    access_key=_access_key(),
                    protocol_reference="protocol-1",
                    rejection_code=None,
                    rejection_message=None,
                    correlation_id="corr-active",
                    version=1,
                    updated_at=NOW,
                ),
                FiscalDocumentProjectionORM(
                    document_id="nfce-other-unit",
                    tenant_id=TENANT,
                    unit_id=OUTRA_UNIDADE,
                    environment="homologation",
                    source_type="venda",
                    source_id="sale-2",
                    document_kind="nfce",
                    state="authorized",
                    access_key=None,
                    protocol_reference="protocol-other",
                    rejection_code=None,
                    rejection_message=None,
                    correlation_id="corr-other",
                    version=1,
                    updated_at=NOW,
                ),
                FiscalDocumentProjectionORM(
                    document_id="nfce-production",
                    tenant_id=TENANT,
                    unit_id=UNIDADE,
                    environment="production",
                    source_type="venda",
                    source_id="sale-prod",
                    document_kind="nfce",
                    state="authorized",
                    access_key=None,
                    protocol_reference="protocol-prod",
                    rejection_code=None,
                    rejection_message=None,
                    correlation_id="corr-prod",
                    version=1,
                    updated_at=NOW,
                ),
                FiscalArchiveORM(
                    entry_id="a" * 64,
                    tenant_id=TENANT,
                    unit_id=UNIDADE,
                    environment="homologation",
                    correlation_id="corr-archive",
                    document_reference="nfce-active-unit",
                    kind="authorized_xml",
                    content=b"<NFe>SECRET-CONTENT-NOT-WEB</NFe>",
                    content_sha256="b" * 64,
                    media_type="application/xml",
                    archived_at=NOW,
                    retention_policy_id="fiscal-default",
                    retention_policy_version=1,
                    retain_until=None,
                    legal_basis_reference=None,
                    previous_manifest_sha256=None,
                ),
                ServicoExternoConfigORM(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    configuracao_id="fiscal.documentos--sefaz",
                    servico="fiscal.documentos",
                    provedor="sefaz",
                    conta_externa="principal",
                    ambiente="homologacao",
                    parametros_publicos={
                        "signer_kind": "a1_pfx",
                        "signing_algorithm": "rsa-sha256",
                        "adapter_version": "wp031i-v1",
                    },
                    finalidades_credenciais={
                        "certificate_pfx": "fiscal_documentos_certificate_pfx",
                        "certificate_password": "fiscal_documentos_certificate_password",
                    },
                    habilitada=True,
                    homologada=False,
                    evidencia_homologacao_ref=None,
                    versao=1,
                    atualizado_por="admin-wp031j",
                    correlation_id="corr-config",
                    criado_em=NOW,
                    atualizado_em=NOW,
                ),
                SegredoIntegracaoORM(
                    referencia="vault:wp031j-secret",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    provedor="sefaz",
                    finalidade="fiscal_documentos_certificate_password",
                    ciphertext="SUPERSECRET-CIPHERTEXT-MUST-NOT-LEAK",
                    criado_por="admin-wp031j",
                    correlation_id="corr-secret",
                    criado_em=NOW,
                ),
            ]
        )
        session.commit()

    app = build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
        ),
        engine=engine,
        session_factory=factory,
        fiscal_operations_gateway_factory=gateway_factory,
    )
    return TestClient(app)


def _access_key() -> str:
    return build_access_key(
        AccessKeyInput(
            state_ibge_code="35",
            issued_at=NOW,
            issuer_cnpj=Cnpj("11222333000181"),
            model=ElectronicInvoiceModel.NFCE,
            series=1,
            invoice_number=123,
            emission_type=1,
            numeric_code=12345678,
        )
    ).value


def _login(client: TestClient, email: str = ADMIN_EMAIL, *, stepup: bool = True) -> None:
    assert client.post(
        "/v1/auth/login",
        json={"email": email, "senha": SENHA},
    ).status_code == 200
    if stepup:
        assert client.post(
            "/v1/auth/admin-step-up",
            json={"senha": SENHA},
        ).status_code == 200


def test_wp031j_fiscal_requires_session_admin_and_stepup(monkeypatch) -> None:
    client = _infra(monkeypatch)
    assert client.get("/v1/admin/fiscal/workspace").status_code == 401

    _login(client, "gerente-wp031j@example.com", stepup=False)
    assert client.get("/v1/admin/fiscal/workspace").status_code == 403

    client = _infra(monkeypatch)
    _login(client, stepup=False)
    response = client.get("/v1/admin/fiscal/workspace")
    assert response.status_code == 403
    assert response.json() == {"erro": "seguranca.admin_step_up_exigido"}


def test_wp031j_workspace_uses_signed_active_scope_and_ignores_spoof_headers(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    _login(client)
    response = client.get(
        "/v1/admin/fiscal/workspace?environment=homologation",
        headers={
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": OUTRA_UNIDADE,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == TENANT
    assert payload["unit_id"] == UNIDADE
    assert [item["document_id"] for item in payload["outbound"]] == [
        "nfce-active-unit"
    ]
    assert "nfce-other-unit" not in str(payload)


def test_wp031j_environment_is_read_filter_not_runtime_authority(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    homologation = client.get(
        "/v1/admin/fiscal/workspace?environment=homologation"
    )
    production = client.get(
        "/v1/admin/fiscal/workspace?environment=production"
    )
    assert homologation.status_code == 200
    assert production.status_code == 200
    assert [item["document_id"] for item in homologation.json()["outbound"]] == [
        "nfce-active-unit"
    ]
    assert [item["document_id"] for item in production.json()["outbound"]] == [
        "nfce-production"
    ]


def test_wp031j_never_exposes_secret_or_archive_content(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    workspace = client.get("/v1/admin/fiscal/workspace")
    archive = client.get("/v1/admin/fiscal/archive")
    assert workspace.status_code == 200
    assert archive.status_code == 200

    combined = f"{workspace.text}\n{archive.text}"
    assert "SUPERSECRET-CIPHERTEXT-MUST-NOT-LEAK" not in combined
    assert "SECRET-CONTENT-NOT-WEB" not in combined
    assert "ciphertext" not in combined
    assert "content" not in archive.json()["entries"][0]
    assert set(workspace.json()["configuration"]["credential_roles"]) == {
        "certificate_pfx",
        "certificate_password",
    }


def test_wp031j_invalid_environment_fails_closed(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    response = client.get("/v1/admin/fiscal/workspace?environment=dev")
    assert response.status_code == 400
    assert response.json() == {"erro": "fiscal.ambiente_invalido"}


def test_wp031j_sensitive_operations_fail_closed_without_gateway(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    cancel = client.post(
        f"/v1/admin/fiscal/documents/{_access_key()}/cancel",
        json={
            "environment": "homologation",
            "authorization_protocol": "protocol-1",
            "justification": "cancelamento fiscal controlado",
        },
    )
    inutilize = client.post(
        "/v1/admin/fiscal/inutilizations",
        json={
            "environment": "homologation",
            "model": 65,
            "series": 1,
            "first_number": 10,
            "last_number": 12,
            "justification": "inutilizacao fiscal controlada",
        },
    )
    assert cancel.status_code == 503
    assert cancel.json() == {"erro": "fiscal.gateway_nao_configurado"}
    assert inutilize.status_code == 503
    assert inutilize.json() == {"erro": "fiscal.gateway_nao_configurado"}


def test_wp031j_sensitive_operations_use_injected_fiscal_v1_gateway(monkeypatch) -> None:
    gateway = FakeFiscalOperationsGateway()
    client = _infra(monkeypatch, gateway_factory=lambda _session: gateway)
    _login(client)

    cancel = client.post(
        f"/v1/admin/fiscal/documents/{_access_key()}/cancel",
        json={
            "environment": "homologation",
            "authorization_protocol": "protocol-1",
            "justification": "cancelamento fiscal controlado",
        },
    )
    inutilize = client.post(
        "/v1/admin/fiscal/inutilizations",
        json={
            "environment": "homologation",
            "model": 65,
            "series": 1,
            "first_number": 10,
            "last_number": 12,
            "justification": "inutilizacao fiscal controlada",
        },
    )

    assert cancel.status_code == 200
    assert cancel.json()["status"] == "accepted"
    assert cancel.json()["event_protocol_reference"]
    assert inutilize.status_code == 200
    assert inutilize.json()["status"] == "accepted"
    assert inutilize.json()["event_protocol_reference"]
