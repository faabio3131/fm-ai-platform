from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core/comercial/billing_events.py"
APP = ROOT / "application/commercial_billing_events.py"
ORM = ROOT / "infra/comercial/billing_events_orm.py"
MIGRATION = ROOT / "migrations/commercial_billing_events_v1.py"
HTTP = ROOT / "http_api/commercial_billing_webhooks.py"
ADMIN = ROOT / "http_api/admin_comercial.py"
WORKFLOW = ROOT / ".github/workflows/kordena-kca-commercial-gate.yml"


def test_kca10_migration_is_canonical_and_additive() -> None:
    versions = tuple(migration.version for migration in DEFAULT_MIGRATIONS)
    assert versions[-1] == "0058_commercial_billing_events_v1"

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    for table in (
        "fm_billing_subscription_bindings_v1",
        "fm_billing_webhook_inbox_v1",
        "fm_billing_transactions_v1",
        "fm_billing_event_cursors_v1",
        "fm_billing_reconciliation_runs_v1",
    ):
        assert table in tables


def test_kca10_is_provider_neutral_and_does_not_persist_raw_webhook() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CORE, APP, ORM, MIGRATION, HTTP)
    ).casefold()
    for concrete in (
        "stripe",
        "cakto",
        "mercadopago",
        "mercado pago",
        "pagbank",
    ):
        assert concrete not in combined

    orm = ORM.read_text(encoding="utf-8").casefold()
    assert "body_hash" in orm
    assert "normalized_payload" in orm
    assert "raw_body" not in orm
    assert "raw_payload" not in orm
    assert "signature_value" not in orm


def test_kca10_has_durable_inbox_ordering_retry_dlq_and_reconciliation() -> None:
    app = APP.read_text(encoding="utf-8").casefold()
    for marker in (
        "failed_retryable",
        "dead_letter",
        "ignored_out_of_order",
        "reprocessar_dead_letter",
        "processar_retries",
        "reconciliar_transacao",
        "billing_event_cursor",
        "replay_body_conflict",
    ):
        assert marker in app


def test_kca10_http_ingress_passes_all_headers_to_adapter() -> None:
    http = HTTP.read_text(encoding="utf-8")
    assert "dict(request.headers.items())" in http
    assert "_MAX_BILLING_WEBHOOK_BYTES" in http
    assert "payload" not in http.split("content={", 1)[-1]


def test_kca10_admin_controls_are_behind_existing_backoffice_context() -> None:
    admin = ADMIN.read_text(encoding="utf-8")
    for marker in (
        "/billing/subscription-bindings",
        "/billing/webhook-inbox/{inbox_id}/replay",
        "/billing/webhook-inbox/process-retries",
        "/billing/transactions/{billing_transaction_id}/reconcile",
    ):
        assert marker in admin
    assert "contexto(request)" in admin


def test_kca10_does_not_anticipate_kca11_paywall_or_dunning() -> None:
    combined = (
        APP.read_text(encoding="utf-8")
        + HTTP.read_text(encoding="utf-8")
        + ORM.read_text(encoding="utf-8")
    ).casefold()
    assert "paywall" not in combined
    assert "dunning" not in combined


def test_kca10_gate_tracks_new_surfaces() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "application/commercial_billing_events.py" in workflow
    assert "migrations/commercial_billing_events_v1.py" in workflow
    assert "tests/fitness/test_kca10_billing_events.py" in workflow
