from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes.catalogo import CATALOGO_V1
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.fiscal.runtime_adapters import (
    ConfiguredFiscalGatewayAdapter,
    ConfiguredFiscalSignerAdapter,
    FiscalControlPlaneResolver,
    FiscalProviderTimeoutError,
    FiscalProviderUnavailableError,
    FiscalRuntimeConfigurationError,
)
from infra.integracoes.modelos_orm import IntegrationConfigBase, ServicoExternoConfigORM
from infra.seguranca.modelos_orm import CredencialReferenciaORM, SecurityBase
from infra.seguranca.segredos_orm import SecretVaultBase
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from kordena_fiscal.domain import (
    Cnpj,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalEnvironment,
)
from kordena_fiscal.gateway import (
    AuthorizationRequest,
    AuthorizationResult,
    AuthorizationStatus,
    FiscalGatewayClient,
    GatewayProviderMetadata,
)
from kordena_fiscal.lifecycle import IdempotencyKey
from kordena_fiscal.operations import (
    CancellationRequest,
    CancellationResult,
    FiscalEventStatus,
    FiscalOperationsClient,
    FiscalQueryRequest,
    FiscalQueryResult,
    FiscalQueryStatus,
    InutilizationRequest,
    InutilizationResult,
)
from kordena_fiscal.security import (
    CertificateValidityError,
    FiscalSigningService,
    SigningRequest,
)
from kordena_fiscal.xml import AccessKeyInput, build_access_key

NOW = datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc)
MASTER_KEY = Fernet.generate_key().decode("ascii")
PASSWORD = "test-pfx-password"


def _scope(
    environment: FiscalEnvironment = FiscalEnvironment.HOMOLOGATION,
    *,
    tenant: str = "tenant-a",
    unit: str = "unit-a",
) -> ExecutionScope:
    return ExecutionScope(tenant, unit, environment, f"corr-{tenant}-{unit}")


def _contexto(*, tenant: str = "tenant-a", unit: str = "unit-a") -> ContextoExecucao:
    return ContextoExecucao(
        usuario_id="admin-1",
        tenant_id=tenant,
        unidade_id=unit,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset({Permissao.INTEGRACAO_GERENCIAR}),
        correlation_id=f"corr-{tenant}-{unit}",
        solicitado_em=NOW,
        origem="test_wp031i",
        unidades_permitidas=frozenset({unit}),
    )


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    IntegrationConfigBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    SecretVaultBase.metadata.create_all(engine)
    return engine


def _pfx(
    *,
    not_before: datetime = NOW - timedelta(days=10),
    expires_at: datetime = NOW + timedelta(days=90),
) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Kordena Fiscal Test")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(expires_at)
        .sign(key, hashes.SHA256())
    )
    raw = pkcs12.serialize_key_and_certificates(
        name=b"kordena-test",
        key=key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(
            PASSWORD.encode("utf-8")
        ),
    )
    return base64.b64encode(raw).decode("ascii")


def _configure(
    session: Session,
    *,
    environment: str = "homologacao",
    homologated: bool = False,
    evidence: str | None = None,
    include_certificate: bool = True,
    include_gateway_secret: bool = True,
    pfx_value: str | None = None,
) -> EncryptedSQLAlchemySecretStore:
    vault = EncryptedSQLAlchemySecretStore(session, master_key=MASTER_KEY)
    context = _contexto()
    purposes: dict[str, str] = {}

    def add_secret(role: str, value: str) -> None:
        purpose = f"fiscal_documentos_{role}"
        reference = vault.armazenar(
            contexto=context,
            provedor="sefaz",
            finalidade=purpose,
            valor=value,
        )
        session.add(
            CredencialReferenciaORM(
                tenant_id=context.tenant_id,
                unidade_id=context.unidade_id,
                provedor="sefaz",
                finalidade=purpose,
                referencia=reference,
                versao=1,
                ativa=True,
                rotacionada_por=context.usuario_id,
                correlation_id=context.correlation_id,
                criada_em=NOW,
            )
        )
        purposes[role] = purpose

    if include_certificate:
        add_secret("certificate_pfx", pfx_value or _pfx())
        add_secret("certificate_password", PASSWORD)
    if include_gateway_secret:
        add_secret("provider_token", "provider-token-value")
        add_secret("csc", "csc-secret-value")

    session.add(
        ServicoExternoConfigORM(
            tenant_id=context.tenant_id,
            unidade_id=context.unidade_id,
            configuracao_id="fiscal.documentos--sefaz",
            servico="fiscal.documentos",
            provedor="sefaz",
            conta_externa="principal",
            ambiente=environment,
            parametros_publicos={
                "signer_kind": "a1_pfx",
                "signing_algorithm": "rsa-sha256",
                "adapter_version": "wp031i-v1",
            },
            finalidades_credenciais=purposes,
            habilitada=True,
            homologada=homologated,
            evidencia_homologacao_ref=evidence,
            versao=1,
            atualizado_por=context.usuario_id,
            correlation_id=context.correlation_id,
            criado_em=NOW,
            atualizado_em=NOW,
        )
    )
    session.commit()
    return vault


def _access_key():
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
    )


def _authorization(scope: ExecutionScope) -> AuthorizationRequest:
    return AuthorizationRequest(
        scope=scope,
        access_key=_access_key(),
        signed_xml=b"<NFe>signed</NFe>",
        idempotency_key=IdempotencyKey("a" * 64),
        request_fingerprint="b" * 64,
    )


class StubTransport:
    def __init__(
        self,
        *,
        authorization_status: AuthorizationStatus = AuthorizationStatus.AUTHORIZED,
        transient: str | None = None,
    ) -> None:
        self.authorization_status = authorization_status
        self.transient = transient
        self.calls = 0
        self.last_credentials = None

    def _before(self, credentials) -> None:
        self.calls += 1
        self.last_credentials = credentials
        if self.transient == "timeout":
            raise TimeoutError("synthetic timeout")
        if self.transient == "unavailable":
            raise ConnectionError("synthetic unavailable")

    def authorize(self, request, *, configuration, credentials):
        self._before(credentials)
        provider = GatewayProviderMetadata(configuration.provider, "wp031i-v1")
        common = {
            "scope": request.scope,
            "access_key": request.access_key,
            "idempotency_key": request.idempotency_key,
            "request_fingerprint": request.request_fingerprint,
            "provider": provider,
            "provider_request_id": f"request-{self.calls}",
        }
        if self.authorization_status is AuthorizationStatus.AUTHORIZED:
            return AuthorizationResult(
                status=self.authorization_status,
                protocol_reference="protocol-1",
                **common,
            )
        if self.authorization_status is AuthorizationStatus.REJECTED:
            return AuthorizationResult(
                status=self.authorization_status,
                rejection_code="999",
                rejection_message="synthetic rejection",
                **common,
            )
        return AuthorizationResult(status=self.authorization_status, **common)

    def query(self, request, *, configuration, credentials):
        self._before(credentials)
        return FiscalQueryResult(
            status=FiscalQueryStatus.AUTHORIZED,
            scope=request.scope,
            access_key=request.access_key,
            provider=GatewayProviderMetadata(configuration.provider, "wp031i-v1"),
            provider_request_id=f"query-{self.calls}",
            protocol_reference="protocol-1",
        )

    def cancel(self, request, *, configuration, credentials):
        self._before(credentials)
        return CancellationResult(
            status=FiscalEventStatus.ACCEPTED,
            scope=request.scope,
            access_key=request.access_key,
            request_id=request.request_id,
            provider=GatewayProviderMetadata(configuration.provider, "wp031i-v1"),
            provider_request_id=f"cancel-{self.calls}",
            event_protocol_reference="cancel-protocol-1",
        )

    def inutilize(self, request, *, configuration, credentials):
        self._before(credentials)
        return InutilizationResult(
            status=FiscalEventStatus.ACCEPTED,
            scope=request.scope,
            model=request.model,
            series=request.series,
            first_number=request.first_number,
            last_number=request.last_number,
            request_id=request.request_id,
            provider=GatewayProviderMetadata(configuration.provider, "wp031i-v1"),
            provider_request_id=f"inutilize-{self.calls}",
            event_protocol_reference="inutilize-protocol-1",
        )


def test_wp031i_catalog_registers_fiscal_control_plane_without_secret_values() -> None:
    spec = CATALOGO_V1.obter("fiscal.documentos", "sefaz")
    assert spec.parametros_obrigatorios == frozenset(
        {"signer_kind", "signing_algorithm", "adapter_version"}
    )
    assert spec.credenciais_obrigatorias == frozenset(
        {"certificate_pfx", "certificate_password"}
    )


def test_wp031i_environment_defaults_to_homologation_and_production_is_explicit() -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = EncryptedSQLAlchemySecretStore(session, master_key=MASTER_KEY)
        resolver = FiscalControlPlaneResolver(session, vault)
        assert (
            resolver.resolve_environment(tenant_id="tenant-a", unit_id="unit-a")
            is FiscalEnvironment.HOMOLOGATION
        )

    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session, environment="producao")
        resolver = FiscalControlPlaneResolver(session, vault)
        with pytest.raises(
            FiscalRuntimeConfigurationError,
            match="homologation evidence",
        ):
            resolver.resolve_environment(tenant_id="tenant-a", unit_id="unit-a")

    engine = _engine()
    with Session(engine) as session:
        vault = _configure(
            session,
            environment="producao",
            homologated=True,
            evidence="evidence://approved-test",
        )
        resolver = FiscalControlPlaneResolver(session, vault)
        assert (
            resolver.resolve_environment(tenant_id="tenant-a", unit_id="unit-a")
            is FiscalEnvironment.PRODUCTION
        )


def test_wp031i_scope_and_environment_mismatch_fail_closed() -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session)
        resolver = FiscalControlPlaneResolver(session, vault)
        with pytest.raises(FiscalRuntimeConfigurationError):
            resolver.configuration_for_scope(_scope(tenant="tenant-b"))
        with pytest.raises(FiscalRuntimeConfigurationError):
            resolver.configuration_for_scope(_scope(unit="unit-b"))
        with pytest.raises(FiscalRuntimeConfigurationError):
            resolver.configuration_for_scope(_scope(FiscalEnvironment.PRODUCTION))


def test_wp031i_missing_certificate_and_expired_certificate_fail_closed() -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session, include_certificate=False)
        resolver = FiscalControlPlaneResolver(session, vault)
        with pytest.raises(FiscalRuntimeConfigurationError, match="certificate_pfx"):
            resolver.resolve_certificate(scope=_scope(), instant=NOW)

    engine = _engine()
    with Session(engine) as session:
        expired = _pfx(
            not_before=NOW - timedelta(days=30),
            expires_at=NOW - timedelta(days=1),
        )
        vault = _configure(session, pfx_value=expired)
        resolver = FiscalControlPlaneResolver(session, vault)
        certificate = resolver.resolve_certificate(scope=_scope(), instant=NOW)
        service = FiscalSigningService(ConfiguredFiscalSignerAdapter(resolver))
        with pytest.raises(CertificateValidityError, match="expired"):
            service.sign(
                SigningRequest(
                    scope=_scope(),
                    certificate=certificate,
                    payload=b"<NFe>payload</NFe>",
                    algorithm="rsa-sha256",
                    signing_time=NOW,
                )
            )


def test_wp031i_a1_pfx_signer_resolves_vault_and_verifies_signature() -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session)
        resolver = FiscalControlPlaneResolver(session, vault)
        certificate = resolver.resolve_certificate(scope=_scope(), instant=NOW)
        result = FiscalSigningService(
            ConfiguredFiscalSignerAdapter(resolver)
        ).sign(
            SigningRequest(
                scope=_scope(),
                certificate=certificate,
                payload=b"<NFe>payload</NFe>",
                algorithm="rsa-sha256",
                signing_time=NOW,
            )
        )
        assert result.certificate_reference_id.startswith("vault:")
        assert result.signature_value
        assert result.payload_sha256
        assert "provider-token-value" not in repr(result)


@pytest.mark.parametrize(
    "status",
    [
        AuthorizationStatus.AUTHORIZED,
        AuthorizationStatus.REJECTED,
        AuthorizationStatus.PENDING,
    ],
)
def test_wp031i_gateway_normalizes_authorized_rejected_and_pending(status) -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session)
        resolver = FiscalControlPlaneResolver(session, vault)
        transport = StubTransport(authorization_status=status)
        result = FiscalGatewayClient(
            ConfiguredFiscalGatewayAdapter(resolver, transport)
        ).authorize(_authorization(_scope()))
        assert result.status is status
        assert transport.last_credentials is not None
        assert str(transport.last_credentials["provider_token"]) == "***"
        assert str(transport.last_credentials["csc"]) == "***"


def test_wp031i_gateway_operations_query_cancel_and_inutilize() -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session)
        resolver = FiscalControlPlaneResolver(session, vault)
        transport = StubTransport()
        client = FiscalOperationsClient(
            ConfiguredFiscalGatewayAdapter(resolver, transport)
        )
        query = client.query(FiscalQueryRequest(_scope(), _access_key()))
        cancel = client.cancel(
            CancellationRequest.build(
                scope=_scope(),
                access_key=_access_key(),
                authorization_protocol="protocol-1",
                justification="cancelamento fiscal controlado",
            )
        )
        inutilize = client.inutilize(
            InutilizationRequest.build(
                scope=_scope(),
                model=ElectronicInvoiceModel.NFCE,
                series=1,
                first_number=10,
                last_number=12,
                justification="inutilizacao fiscal controlada",
            )
        )
        assert query.status is FiscalQueryStatus.AUTHORIZED
        assert cancel.status is FiscalEventStatus.ACCEPTED
        assert inutilize.status is FiscalEventStatus.ACCEPTED


@pytest.mark.parametrize(
    ("transient", "error_type"),
    [
        ("timeout", FiscalProviderTimeoutError),
        ("unavailable", FiscalProviderUnavailableError),
    ],
)
def test_wp031i_gateway_retries_transient_failures_then_fails_closed(
    transient,
    error_type,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session)
        resolver = FiscalControlPlaneResolver(session, vault)
        transport = StubTransport(transient=transient)
        adapter = ConfiguredFiscalGatewayAdapter(
            resolver,
            transport,
            max_attempts=2,
        )
        with pytest.raises(error_type):
            adapter.authorize(_authorization(_scope()))
        assert transport.calls == 2


def test_wp031i_no_secret_is_persisted_in_control_plane_public_parameters() -> None:
    engine = _engine()
    with Session(engine) as session:
        vault = _configure(session)
        resolver = FiscalControlPlaneResolver(session, vault)
        configuration = resolver.configuration_for_scope(_scope())
        serialized = repr(configuration.public_parameters)
        assert PASSWORD not in serialized
        assert "provider-token-value" not in serialized
        assert "csc-secret-value" not in serialized
