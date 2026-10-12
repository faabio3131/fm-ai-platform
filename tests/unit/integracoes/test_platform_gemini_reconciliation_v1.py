from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, insert, select

from core.integracoes.platform_scope import FM_PLATFORM_TENANT_ID, FM_PLATFORM_UNIT_ID
from infra.integracoes.modelos_orm import IntegrationConfigBase, ServicoExternoConfigORM
from infra.seguranca.modelos_orm import CredencialReferenciaORM, SecurityBase
from infra.seguranca.segredos_orm import SecretVaultBase, SegredoIntegracaoORM
from migrations.platform_gemini_reconciliation_v1 import (
    upgrade_platform_gemini_reconciliation_v1,
)


def _seed_legacy(connection, *, tenant: str = "tenant-legado", unit: str = "unit-legada") -> None:
    now = datetime.now(timezone.utc)
    connection.execute(
        insert(ServicoExternoConfigORM.__table__).values(
            tenant_id=tenant,
            unidade_id=unit,
            configuracao_id="ia.generativa--gemini",
            servico="ia.generativa",
            provedor="gemini",
            conta_externa="principal",
            ambiente="homologacao",
            parametros_publicos={"model": "gemini-3.6-flash"},
            finalidades_credenciais={"api_key": "ia_generativa_api_key"},
            habilitada=True,
            homologada=True,
            evidencia_homologacao_ref="healthcheck://gemini/legacy-ok",
            versao=2,
            atualizado_por="admin-legado",
            correlation_id="corr-legado",
            criado_em=now,
            atualizado_em=now,
        )
    )
    connection.execute(
        insert(SegredoIntegracaoORM.__table__).values(
            referencia=f"vault:{tenant}",
            tenant_id=tenant,
            unidade_id=unit,
            provedor="gemini",
            finalidade="ia_generativa_api_key",
            ciphertext="ciphertext-opaco-sem-plaintext",
            criado_por="admin-legado",
            correlation_id="corr-legado",
            criado_em=now,
        )
    )
    connection.execute(
        insert(CredencialReferenciaORM.__table__).values(
            tenant_id=tenant,
            unidade_id=unit,
            provedor="gemini",
            finalidade="ia_generativa_api_key",
            referencia=f"vault:{tenant}",
            versao=1,
            ativa=True,
            rotacionada_por="admin-legado",
            correlation_id="corr-legado",
            criada_em=now,
            desativada_em=None,
        )
    )


def _engine():
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    SecretVaultBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    return engine


def test_reconcilia_unica_autoridade_homologada_sem_plaintext() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _seed_legacy(connection)
        upgrade_platform_gemini_reconciliation_v1(connection)

        config = connection.execute(
            select(ServicoExternoConfigORM.__table__).where(
                ServicoExternoConfigORM.tenant_id == FM_PLATFORM_TENANT_ID,
                ServicoExternoConfigORM.unidade_id == FM_PLATFORM_UNIT_ID,
            )
        ).mappings().one()
        assert config["homologada"] is True
        assert config["habilitada"] is True
        assert config["parametros_publicos"]["model"] == "gemini-3.6-flash"
        assert config["evidencia_homologacao_ref"] == "healthcheck://gemini/legacy-ok"

        credential = connection.execute(
            select(CredencialReferenciaORM.__table__).where(
                CredencialReferenciaORM.tenant_id == FM_PLATFORM_TENANT_ID,
                CredencialReferenciaORM.unidade_id == FM_PLATFORM_UNIT_ID,
                CredencialReferenciaORM.provedor == "gemini",
                CredencialReferenciaORM.ativa.is_(True),
            )
        ).mappings().one()
        assert str(credential["referencia"]).startswith("vault:")
        assert credential["referencia"] != "vault:tenant-legado"

        secret = connection.execute(
            select(SegredoIntegracaoORM.__table__).where(
                SegredoIntegracaoORM.referencia == credential["referencia"]
            )
        ).mappings().one()
        assert secret["ciphertext"] == "ciphertext-opaco-sem-plaintext"
        assert secret["tenant_id"] == FM_PLATFORM_TENANT_ID
        assert secret["unidade_id"] == FM_PLATFORM_UNIT_ID


def test_ambiguidade_legada_permanece_fail_closed() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _seed_legacy(connection, tenant="tenant-a", unit="unit-a")
        _seed_legacy(connection, tenant="tenant-b", unit="unit-b")
        upgrade_platform_gemini_reconciliation_v1(connection)

        canonical = connection.execute(
            select(ServicoExternoConfigORM.__table__).where(
                ServicoExternoConfigORM.tenant_id == FM_PLATFORM_TENANT_ID,
                ServicoExternoConfigORM.unidade_id == FM_PLATFORM_UNIT_ID,
            )
        ).mappings().all()
        assert canonical == []


def test_central_explicitamente_desabilitada_nao_e_reativada() -> None:
    engine = _engine()
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        _seed_legacy(connection)
        connection.execute(
            insert(ServicoExternoConfigORM.__table__).values(
                tenant_id=FM_PLATFORM_TENANT_ID,
                unidade_id=FM_PLATFORM_UNIT_ID,
                configuracao_id="ia.generativa--gemini",
                servico="ia.generativa",
                provedor="gemini",
                conta_externa="principal",
                ambiente="homologacao",
                parametros_publicos={"model": "gemini-3.6-flash"},
                finalidades_credenciais={"api_key": "ia_generativa_api_key"},
                habilitada=False,
                homologada=False,
                evidencia_homologacao_ref=None,
                versao=1,
                atualizado_por="fm-command",
                correlation_id="corr-command",
                criado_em=now,
                atualizado_em=now,
            )
        )

        upgrade_platform_gemini_reconciliation_v1(connection)

        canonical = connection.execute(
            select(ServicoExternoConfigORM.__table__).where(
                ServicoExternoConfigORM.tenant_id == FM_PLATFORM_TENANT_ID,
                ServicoExternoConfigORM.unidade_id == FM_PLATFORM_UNIT_ID,
            )
        ).mappings().one()
        assert canonical["habilitada"] is False
        assert canonical["homologada"] is False
