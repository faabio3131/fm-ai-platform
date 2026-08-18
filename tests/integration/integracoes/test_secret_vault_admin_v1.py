from __future__ import annotations

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.segredos_orm import SegredoIntegracaoORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from migrations.runner import run_migrations


def _identity(
    tenant: str,
    user: str,
    *,
    unidade: str = "loja-1",
) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id=user,
        email=f"{user}@example.test",
        senha_hash="hash-test",
        tenant_id=tenant,
        unidade_id=unidade,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({unidade}),
    )


def test_vault_cifra_segredo_e_referencia_fica_isolada_por_tenant() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    key = Fernet.generate_key().decode("ascii")
    secret = "token-super-secreto-123"

    with Session(engine) as session:
        identity_a = _identity("tenant-a", "admin-a")
        context_a = identity_a.contexto(origem="test")
        vault = EncryptedSQLAlchemySecretStore(session, master_key=key)
        reference = vault.armazenar(
            contexto=context_a,
            provedor="meta",
            finalidade="mensageria_whatsapp_access_token",
            valor=secret,
        )
        credentials = ServicoCredenciaisReferenciadas(session, vault)
        credentials.rotacionar(
            contexto=context_a,
            provedor="meta",
            finalidade="mensageria_whatsapp_access_token",
            nova_referencia=reference,
        )
        session.commit()

        row = session.scalar(
            select(SegredoIntegracaoORM).where(
                SegredoIntegracaoORM.referencia == reference
            )
        )
        assert row is not None
        assert row.tenant_id == "tenant-a"
        assert secret not in row.ciphertext
        assert vault.resolve(reference).reveal() == secret
        assert credentials.resolver_valor(
            contexto=context_a,
            provedor="meta",
            finalidade="mensageria_whatsapp_access_token",
        ) == secret

        identity_b = _identity("tenant-b", "admin-b")
        context_b = identity_b.contexto(origem="test")
        assert credentials.atual(
            contexto=context_b,
            provedor="meta",
            finalidade="mensageria_whatsapp_access_token",
        ) is None
        assert vault.pertence_ao_escopo(contexto=context_b, reference=reference) is False


def test_vault_isola_mesmo_tenant_por_unidade() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    key = Fernet.generate_key().decode("ascii")

    with Session(engine) as session:
        context_loja_1 = _identity(
            "tenant-a", "admin-loja-1", unidade="loja-1"
        ).contexto(origem="test")
        context_loja_2 = _identity(
            "tenant-a", "admin-loja-2", unidade="loja-2"
        ).contexto(origem="test")
        vault = EncryptedSQLAlchemySecretStore(session, master_key=key)
        credentials = ServicoCredenciaisReferenciadas(session, vault)

        reference = vault.armazenar(
            contexto=context_loja_1,
            provedor="google_maps",
            finalidade="maps_server_api_key",
            valor="server-key-loja-1",
        )
        credentials.rotacionar(
            contexto=context_loja_1,
            provedor="google_maps",
            finalidade="maps_server_api_key",
            nova_referencia=reference,
        )
        session.commit()

        assert credentials.resolver_valor(
            contexto=context_loja_1,
            provedor="google_maps",
            finalidade="maps_server_api_key",
        ) == "server-key-loja-1"
        assert credentials.atual(
            contexto=context_loja_2,
            provedor="google_maps",
            finalidade="maps_server_api_key",
        ) is None
        assert (
            vault.pertence_ao_escopo(
                contexto=context_loja_2,
                reference=reference,
            )
            is False
        )
