"""Factory Asaas: credenciais por tenant/unidade/servico no Vault cifrado."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.pagamentos.asaas import ConfiguracaoAsaas, ErroAsaas
from infra.integracoes.modelos_orm import (
    IntegrationConfigBase,
    ServicoExternoConfigORM,
)
from infra.pagamentos.asaas_runtime import AsaasAdapterFactory
from infra.seguranca.modelos_orm import CredencialReferenciaORM, SecurityBase
from infra.seguranca.segredos_orm import SecretVaultBase, SegredoIntegracaoORM


def _db(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("FM_AI_SECRET_MASTER_KEY", key.decode())
    engine = create_engine("sqlite:///:memory:")
    IntegrationConfigBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    SecretVaultBase.metadata.create_all(engine)
    return engine, Fernet(key)


def _config(session, tenant, unit, service, *, env="sandbox", homologada=False):
    suffix = service.split(".")[-1]
    cfg = ServicoExternoConfigORM(
        tenant_id=tenant, unidade_id=unit,
        configuracao_id="asaas-" + suffix,
        servico=service, provedor="asaas", conta_externa="loja-a",
        ambiente=env, parametros_publicos={},
        finalidades_credenciais={
            "api_key": "asaas_" + suffix + "_key",
            "webhook_token": "asaas_" + suffix + "_hook",
        },
        habilitada=True, homologada=homologada,
        evidencia_homologacao_ref="evidencia://homologado" if homologada else None,
        versao=1, atualizado_por="proprietario", correlation_id="qa",
    )
    session.add(cfg)


def _secret(session, fernet, tenant, unit, purpose, plaintext, *, vault_tenant=None):
    ref = f"vault:{tenant}-{unit}-{purpose}"
    session.add(SegredoIntegracaoORM(
        referencia=ref, tenant_id=vault_tenant or tenant,
        unidade_id=unit, provedor="asaas", finalidade=purpose,
        ciphertext=fernet.encrypt(plaintext.encode()).decode(),
        criado_por="qa", correlation_id="qa",
    ))
    session.add(CredencialReferenciaORM(
        tenant_id=tenant, unidade_id=unit, provedor="asaas",
        finalidade=purpose, referencia=ref, ativa=True,
        versao=1, rotacionada_por="qa", correlation_id="qa",
    ))


def _fill(session, fernet, tenant, unit, service, *, env="sandbox", homologada=False):
    _config(session, tenant, unit, service, env=env, homologada=homologada)
    suffix = service.split(".")[-1]
    _secret(session, fernet, tenant, unit, f"asaas_{suffix}_key", f"key-{tenant}-{unit}-{suffix}")
    _secret(session, fernet, tenant, unit, f"asaas_{suffix}_hook", "hook-" + "w" * 40)


def _factory():
    return AsaasAdapterFactory(builder=lambda config: config)


def test_vault_factory_distingue_tenant_unidade_e_metodo(monkeypatch):
    engine, fernet = _db(monkeypatch)
    with Session(engine) as session:
        for tenant in ("tenant-a", "tenant-b"):
            for unit in ("unit-1", "unit-2"):
                for servico in ("pagamentos.pix", "pagamentos.cartao"):
                    _fill(session, fernet, tenant, unit, servico)
        session.commit()
        factory = _factory()
        pix = factory.construir(
            session=session, tenant_id="tenant-a", unidade_id="unit-1",
            servico="pagamentos.pix",
        )
        card = factory.construir(
            session=session, tenant_id="tenant-a", unidade_id="unit-1",
            servico="pagamentos.cartao",
        )
        other = factory.construir(
            session=session, tenant_id="tenant-b", unidade_id="unit-1",
            servico="pagamentos.pix",
        )
        assert isinstance(pix, ConfiguracaoAsaas)
        assert pix.api_key == "key-tenant-a-unit-1-pix"
        assert card.api_key == "key-tenant-a-unit-1-cartao"
        assert other.api_key == "key-tenant-b-unit-1-pix"
        assert pix.api_key != card.api_key != other.api_key


def test_factory_sem_config_nao_buscara_credencial_de_outra_unidade(monkeypatch):
    engine, fernet = _db(monkeypatch)
    with Session(engine) as session:
        _fill(session, fernet, "tenant-a", "unit-1", "pagamentos.pix")
        session.commit()
        with pytest.raises(ErroAsaas, match="asaas_configuracao_unica_necessaria"):
            _factory().construir(
                session=session, tenant_id="tenant-a", unidade_id="unit-2",
                servico="pagamentos.pix",
            )


def test_vault_referencia_cruzada_rejeitada_mesmo_com_registro_no_tenant(monkeypatch):
    engine, fernet = _db(monkeypatch)
    with Session(engine) as session:
        _fill(session, fernet, "tenant-a", "unit-1", "pagamentos.pix")
        session.flush()
        vault_record = session.scalar(
            select(SegredoIntegracaoORM).where(
                SegredoIntegracaoORM.tenant_id == "tenant-a",
                SegredoIntegracaoORM.finalidade == "asaas_pix_key",
            )
        )
        assert vault_record is not None
        vault_record.tenant_id = "tenant-b"
        session.commit()
        with pytest.raises(ErroAsaas, match="asaas_credencial_escopo_divergente"):
            _factory().construir(
                session=session, tenant_id="tenant-a", unidade_id="unit-1",
                servico="pagamentos.pix",
            )


def test_factory_producao_nao_homologada_falha_fechada(monkeypatch):
    engine, fernet = _db(monkeypatch)
    with Session(engine) as session:
        _fill(session, fernet, "tenant-a", "unit-1", "pagamentos.pix", env="producao")
        session.commit()
        with pytest.raises(ErroAsaas, match="asaas_producao_nao_homologada"):
            _factory().construir(
                session=session, tenant_id="tenant-a", unidade_id="unit-1",
                servico="pagamentos.pix",
            )
