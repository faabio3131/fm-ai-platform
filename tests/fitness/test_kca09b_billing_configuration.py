from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core/comercial/billing_config.py"
APP = ROOT / "application/commercial_billing_config.py"
ORM = ROOT / "infra/comercial/billing_config_orm.py"
MIGRATION = ROOT / "migrations/commercial_billing_config_v1.py"
ADMIN = ROOT / "http_api/admin_comercial.py"
WORKFLOW = ROOT / ".github/workflows/kordena-kca-commercial-gate.yml"


def test_kca09b_migration_is_canonical_and_additive() -> None:
    versions = tuple(migration.version for migration in DEFAULT_MIGRATIONS)
    assert versions[-1] == "0057_commercial_billing_config_v1"

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    assert "fm_billing_provider_accounts_v1" in tables
    assert "fm_billing_routing_policies_v1" in tables


def test_kca09b_is_provider_neutral_and_configurable() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CORE, APP, ORM, MIGRATION, ADMIN)
    ).casefold()
    for concrete in (
        "stripe",
        "cakto",
        "mercado pago",
        "mercadopago",
        "pagbank",
    ):
        assert concrete not in combined

    assert "provider_code" in combined
    assert "credential_secret_reference" in combined
    assert "encryptedsqlalchemysecretstore" in combined
    assert "billing.secret_reference_scope_mismatch" in combined
    assert "supported_payment_methods" in combined
    assert "fallback_provider_account_ids" in combined
    assert "requires_recurring" in combined
    assert "requires_webhooks" in combined


def test_kca09b_does_not_anticipate_kca10() -> None:
    combined = (
        APP.read_text(encoding="utf-8")
        + ORM.read_text(encoding="utf-8")
        + MIGRATION.read_text(encoding="utf-8")
    ).casefold()
    assert "webhook_inbox" not in combined
    assert "reconciliation_job" not in combined
    assert "dead_letter" not in combined
    assert "replay_engine" not in combined


def test_kca09b_admin_api_does_not_return_secret_reference() -> None:
    text = ADMIN.read_text(encoding="utf-8")
    provider_out = text.split("def _billing_provider_out", 1)[1].split(
        "def _billing_routing_out", 1
    )[0]
    assert "credential_configured" in provider_out
    assert '"credential_secret_reference"' not in provider_out


def test_kca09b_gate_tracks_new_surfaces() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "application/commercial_billing_config.py" in workflow
    assert "migrations/commercial_billing_config_v1.py" in workflow
    assert "tests/fitness/test_kca09b_billing_configuration.py" in workflow
