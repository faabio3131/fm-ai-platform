"""KCA-17 final technical readiness drill.

Runs only against disposable PostgreSQL staging databases. It proves backup/restore,
tenant integrity, health and release-safe defaults. External business prerequisites
remain separate and cannot be promoted by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from application.commercial_observability import AplicacaoCommercialObservabilityKCA13
from core.runtime.backup import backup_database, restore_database, verify_backup
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from http_api.frontend_app import build_frontend_http_app
from infra.legacy_product_scope import garantir_loja_legada_para_escopo
from migrations.runner import run_migrations

TENANT = "kca17-readiness-tenant"
UNIT = "kca17-readiness-unit"


def _load_external_prerequisites(path: Path) -> tuple[list[str], dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["items"]
    blockers = [
        name
        for name, item in items.items()
        if item.get("required") is True and item.get("status") != "PASS"
    ]
    return blockers, payload


def _mapping(engine) -> tuple[str, str, int, bool]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT tenant_id, unidade_id, loja_id, ativo "
                "FROM fm_unidade_loja_legacy_v1 "
                "WHERE tenant_id=:tenant AND unidade_id=:unit"
            ),
            {"tenant": TENANT, "unit": UNIT},
        ).one()
    return str(row.tenant_id), str(row.unidade_id), int(row.loja_id), bool(row.ativo)


def run(*, output: Path, prerequisites: Path, backup_file: Path) -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("KCA-17 readiness drill must not use FM_AI_TEST_MODE")

    source_url = os.environ["DATABASE_URL"].strip()
    restore_url = os.environ["RESTORE_DATABASE_URL"].strip()
    for name, value in (("DATABASE_URL", source_url), ("RESTORE_DATABASE_URL", restore_url)):
        if not value.startswith("postgresql"):
            raise RuntimeError(f"{name} must point to disposable PostgreSQL")

    source_database = str(make_url(source_url).database or "")
    restore_database_name = str(make_url(restore_url).database or "")
    if not source_database or not restore_database_name or source_database == restore_database_name:
        raise RuntimeError("KCA-17 source and restore databases must be distinct")

    source_engine = create_engine(source_url, future=True)
    run_migrations(source_engine)
    factory = sessionmaker(bind=source_engine, expire_on_commit=False, future=True)

    with factory() as session, session.begin():
        garantir_loja_legada_para_escopo(
            session,
            tenant_id=TENANT,
            unidade_id=UNIT,
            nome_fantasia="KCA-17 Readiness Sentinel",
        )

    source_tables = tuple(sorted(inspect(source_engine).get_table_names()))
    source_mapping = _mapping(source_engine)

    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_started = time.monotonic()
    manifest = backup_database(source_url, backup_file)
    backup_seconds = time.monotonic() - backup_started
    verified = verify_backup(backup_file)
    if verified.sha256 != manifest.sha256:
        raise AssertionError("backup manifest verification mismatch")

    restore_started = time.monotonic()
    restore_database(
        restore_url,
        backup_file,
        confirm_database=restore_database_name,
    )
    restore_seconds = time.monotonic() - restore_started

    restored_engine = create_engine(restore_url, future=True)
    restored_tables = tuple(sorted(inspect(restored_engine).get_table_names()))
    restored_mapping = _mapping(restored_engine)

    assert restored_tables == source_tables
    assert restored_mapping == source_mapping
    assert restored_mapping[0] == TENANT
    assert restored_mapping[1] == UNIT
    assert restored_mapping[3] is True

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url=source_url,
        tenant_id=TENANT,
        unidade_id=UNIT,
        commercial_access_gate_enabled=True,
        fmcc_control_plane_token=os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"],
    ).validate()
    app = build_frontend_http_app(
        settings=settings,
        engine=source_engine,
        session_factory=factory,
        public_signup_enabled=False,
    )
    client = TestClient(app, base_url="https://kca17.local")

    health = client.get("/healthz")
    assert health.status_code == 200, health.text
    assert health.json()["ok"] is True

    signup = client.post(
        "/v1/public/signup",
        json={
            "owner_name": "KCA17",
            "email": "should-not-open@example.test",
            "password": "KCA17-Disabled-Password!",
            "establishment_name": "Blocked Until Release",
            "segment": "restaurant",
            "terms_accepted": True,
            "consents": {},
        },
    )
    assert signup.status_code == 404

    observability = AplicacaoCommercialObservabilityKCA13(factory).snapshot()
    assert observability["schema_version"] == "kordena.observability.kca13.v1"
    assert observability["internal_test_excluded"] is True
    assert "health" in observability
    assert "alerts" in observability
    assert "metrics" in observability

    external_blockers, external_manifest = _load_external_prerequisites(prerequisites)
    release_gate = "PASS" if not external_blockers else "BLOCKED_EXTERNALLY"

    evidence = {
        "gate": "KCA17-TECHNICAL-READINESS",
        "technical_readiness": "PASS",
        "release_gate": release_gate,
        "environment": "ephemeral_postgresql_staging",
        "fm_ai_test_mode": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backup_restore": {
            "status": "pass",
            "backend": manifest.backend,
            "sha256": manifest.sha256,
            "size_bytes": manifest.size_bytes,
            "source_database": source_database,
            "restore_database": restore_database_name,
            "backup_seconds_measured": round(backup_seconds, 3),
            "restore_seconds_measured": round(restore_seconds, 3),
            "source_table_count": len(source_tables),
            "restored_table_count": len(restored_tables),
            "tenant_integrity": "pass",
            "rpo_rto_claimed": False,
        },
        "runtime": {
            "healthz": "pass",
            "public_signup_default_disabled": "pass",
            "commercial_observability": "pass",
        },
        "external_prerequisites": {
            "blockers": external_blockers,
            "manifest": external_manifest,
        },
        "public_activation": "disabled",
        "billing_real_used": False,
        "external_customer_used": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/kca17-final-readiness.json")
    parser.add_argument(
        "--prerequisites",
        default="docs/commercial-platform/KCA17_EXTERNAL_PREREQUISITES.json",
    )
    parser.add_argument("--backup-file", default="evidence/kca17-readiness.dump")
    args = parser.parse_args()
    run(
        output=Path(args.output),
        prerequisites=Path(args.prerequisites),
        backup_file=Path(args.backup_file),
    )


if __name__ == "__main__":
    main()
