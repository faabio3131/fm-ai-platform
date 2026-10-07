"""Reconciliacao idempotente do Gemini platform-managed para o escopo do Command."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from core.integracoes.platform_scope import FM_PLATFORM_TENANT_ID, FM_PLATFORM_UNIT_ID
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_orm import SegredoIntegracaoORM

_CONFIG_ID = "ia.generativa--gemini"
_PROVIDER = "gemini"
_API_ROLE = "api_key"
_DEFAULT_PURPOSE = "ia_generativa_api_key"
_MIGRATION_ACTOR = "migration-0069-platform-gemini"
_MIGRATION_CORRELATION = "migration:0069-platform-gemini"


def upgrade_platform_gemini_reconciliation_v1(connection: Connection) -> None:
    """Centraliza uma autoridade Gemini homologada sem expor o segredo em claro.

    A promocao automatica so ocorre quando existe exatamente uma autoridade
    legada utilizavel. Estado central explicitamente desabilitado permanece
    fail-closed. Um estado central habilitado pode ser reparado apenas quando
    modelo e evidencia homologada do legado sao compativeis.
    """

    config_table = ServicoExternoConfigORM.__table__
    credential_table = CredencialReferenciaORM.__table__
    vault_table = SegredoIntegracaoORM.__table__

    def active_credential(
        tenant_id: str,
        unidade_id: str,
        finalidade: str,
    ) -> RowMapping | None:
        return connection.execute(
            select(credential_table)
            .where(
                credential_table.c.tenant_id == tenant_id,
                credential_table.c.unidade_id == unidade_id,
                credential_table.c.provedor == _PROVIDER,
                credential_table.c.finalidade == finalidade,
                credential_table.c.ativa.is_(True),
            )
            .order_by(credential_table.c.versao.desc())
            .limit(1)
        ).mappings().first()

    def vault(reference: str) -> RowMapping | None:
        return connection.execute(
            select(vault_table).where(vault_table.c.referencia == reference)
        ).mappings().first()

    canonical = connection.execute(
        select(config_table).where(
            config_table.c.tenant_id == FM_PLATFORM_TENANT_ID,
            config_table.c.unidade_id == FM_PLATFORM_UNIT_ID,
            config_table.c.configuracao_id == _CONFIG_ID,
        )
    ).mappings().first()

    if canonical is not None and not bool(canonical["habilitada"]):
        return

    if canonical is not None:
        canonical_purposes = dict(canonical["finalidades_credenciais"] or {})
        canonical_purpose = str(
            canonical_purposes.get(_API_ROLE) or _DEFAULT_PURPOSE
        )
        current = active_credential(
            FM_PLATFORM_TENANT_ID,
            FM_PLATFORM_UNIT_ID,
            canonical_purpose,
        )
        if (
            bool(canonical["homologada"])
            and current is not None
            and vault(str(current["referencia"])) is not None
        ):
            return

    legacy_rows = connection.execute(
        select(config_table)
        .where(
            config_table.c.configuracao_id == _CONFIG_ID,
            config_table.c.provedor == _PROVIDER,
            config_table.c.habilitada.is_(True),
            config_table.c.homologada.is_(True),
            ~and_(
                config_table.c.tenant_id == FM_PLATFORM_TENANT_ID,
                config_table.c.unidade_id == FM_PLATFORM_UNIT_ID,
            ),
        )
        .order_by(config_table.c.atualizado_em.desc())
    ).mappings().all()

    usable: list[tuple[RowMapping, RowMapping, RowMapping, str]] = []
    for row in legacy_rows:
        purposes = dict(row["finalidades_credenciais"] or {})
        purpose = str(purposes.get(_API_ROLE) or _DEFAULT_PURPOSE)
        credential = active_credential(
            str(row["tenant_id"]),
            str(row["unidade_id"]),
            purpose,
        )
        if credential is None:
            continue
        secret = vault(str(credential["referencia"]))
        if secret is None:
            continue
        usable.append((row, credential, secret, purpose))

    if len(usable) != 1:
        return

    source, _source_credential, source_secret, purpose = usable[0]
    source_params = dict(source["parametros_publicos"] or {})
    source_model = str(source_params.get("model") or "").strip()
    if not source_model:
        return

    if canonical is not None:
        canonical_params = dict(canonical["parametros_publicos"] or {})
        canonical_model = str(canonical_params.get("model") or "").strip()
        if canonical_model and canonical_model != source_model:
            return

    now = datetime.now(timezone.utc)

    if canonical is None:
        connection.execute(
            insert(config_table).values(
                tenant_id=FM_PLATFORM_TENANT_ID,
                unidade_id=FM_PLATFORM_UNIT_ID,
                configuracao_id=_CONFIG_ID,
                servico=source["servico"],
                provedor=source["provedor"],
                conta_externa=source["conta_externa"],
                ambiente=source["ambiente"],
                parametros_publicos=source_params,
                finalidades_credenciais={_API_ROLE: purpose},
                habilitada=True,
                homologada=True,
                evidencia_homologacao_ref=source["evidencia_homologacao_ref"],
                versao=1,
                atualizado_por=_MIGRATION_ACTOR,
                correlation_id=_MIGRATION_CORRELATION,
                criado_em=now,
                atualizado_em=now,
            )
        )
    else:
        purposes = dict(canonical["finalidades_credenciais"] or {})
        purposes[_API_ROLE] = purpose
        values: dict[str, Any] = {
            "finalidades_credenciais": purposes,
            "atualizado_por": _MIGRATION_ACTOR,
            "correlation_id": _MIGRATION_CORRELATION,
            "atualizado_em": now,
            "versao": int(canonical["versao"]) + 1,
        }
        if not bool(canonical["homologada"]):
            values["homologada"] = True
            values["evidencia_homologacao_ref"] = source[
                "evidencia_homologacao_ref"
            ]
        connection.execute(
            update(config_table)
            .where(
                config_table.c.tenant_id == FM_PLATFORM_TENANT_ID,
                config_table.c.unidade_id == FM_PLATFORM_UNIT_ID,
                config_table.c.configuracao_id == _CONFIG_ID,
            )
            .values(**values)
        )

    stale = connection.execute(
        select(credential_table)
        .where(
            credential_table.c.tenant_id == FM_PLATFORM_TENANT_ID,
            credential_table.c.unidade_id == FM_PLATFORM_UNIT_ID,
            credential_table.c.provedor == _PROVIDER,
            credential_table.c.finalidade == purpose,
            credential_table.c.ativa.is_(True),
        )
        .order_by(credential_table.c.versao.desc())
    ).mappings().all()
    for item in stale:
        connection.execute(
            update(credential_table)
            .where(credential_table.c.id == item["id"])
            .values(ativa=False, desativada_em=now)
        )

    latest_version = connection.execute(
        select(credential_table.c.versao)
        .where(
            credential_table.c.tenant_id == FM_PLATFORM_TENANT_ID,
            credential_table.c.unidade_id == FM_PLATFORM_UNIT_ID,
            credential_table.c.provedor == _PROVIDER,
            credential_table.c.finalidade == purpose,
        )
        .order_by(credential_table.c.versao.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_version = int(latest_version or 0) + 1

    new_reference = f"vault:{uuid4().hex}"
    connection.execute(
        insert(vault_table).values(
            referencia=new_reference,
            tenant_id=FM_PLATFORM_TENANT_ID,
            unidade_id=FM_PLATFORM_UNIT_ID,
            provedor=_PROVIDER,
            finalidade=purpose,
            ciphertext=source_secret["ciphertext"],
            criado_por=_MIGRATION_ACTOR,
            correlation_id=_MIGRATION_CORRELATION,
            criado_em=now,
        )
    )
    connection.execute(
        insert(credential_table).values(
            tenant_id=FM_PLATFORM_TENANT_ID,
            unidade_id=FM_PLATFORM_UNIT_ID,
            provedor=_PROVIDER,
            finalidade=purpose,
            referencia=new_reference,
            versao=next_version,
            ativa=True,
            rotacionada_por=_MIGRATION_ACTOR,
            correlation_id=_MIGRATION_CORRELATION,
            criada_em=now,
            desativada_em=None,
        )
    )
