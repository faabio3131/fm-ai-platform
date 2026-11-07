"""Garante que o PDV Pix consome credenciais configuradas na interface do Kordena."""
from __future__ import annotations

from types import SimpleNamespace

from core.seguranca.segredos import ReferenceSecretStore, SecretValue
from infra.pagamentos.pagbank_runtime import (
    PagBankAdapterFactory,
    PagBankRuntimeConfig,
)


def test_pagbank_runtime_resolve_vault_da_unidade_sem_revelar_no_http(monkeypatch):
    from infra.pagamentos import pagbank_runtime

    session = SimpleNamespace(
        scalar=lambda statement: SimpleNamespace(referencia="vault:token-sintetico")
    )
    chamadas = []

    class VaultFake:
        def __init__(self, session_param):
            assert session_param is session

        def resolve(self, reference):
            chamadas.append(reference)
            return SecretValue("token_pagbank_sintetico")

    monkeypatch.setattr(pagbank_runtime, "EncryptedSQLAlchemySecretStore", VaultFake)
    monkeypatch.setattr(pagbank_runtime, "AdapterPagBank", lambda config: config)
    factory = PagBankAdapterFactory(
        secret_store=ReferenceSecretStore(),
        config=PagBankRuntimeConfig(ambiente="sandbox"),
    )
    config = factory.construir(
        session=session, tenant_id="tenant-test", unidade_id="unidade-test"
    )
    assert config.token == "token_pagbank_sintetico"
    assert chamadas == ["vault:token-sintetico"]


def test_pagbank_runtime_conserva_referencia_env_e_nao_tenta_vault(monkeypatch):
    from infra.pagamentos import pagbank_runtime

    session = SimpleNamespace(
        scalar=lambda statement: SimpleNamespace(referencia="mapping:TEST_PAGBANK")
    )
    monkeypatch.setattr(
        pagbank_runtime,
        "EncryptedSQLAlchemySecretStore",
        lambda *_: (_ for _ in ()).throw(AssertionError("não criar vault")),
    )
    monkeypatch.setattr(pagbank_runtime, "AdapterPagBank", lambda config: config)
    factory = PagBankAdapterFactory(
        secret_store=ReferenceSecretStore(mapping={"TEST_PAGBANK": "token-env-test"}),
        config=PagBankRuntimeConfig(ambiente="sandbox"),
    )
    config = factory.construir(
        session=session, tenant_id="tenant-test", unidade_id="unidade-test"
    )
    assert config.token == "token-env-test"
