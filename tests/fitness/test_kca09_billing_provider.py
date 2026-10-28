from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core" / "comercial" / "billing.py"
APP = ROOT / "application" / "commercial_billing.py"
WORKFLOW = ROOT / ".github" / "workflows" / "kordena-kca-commercial-gate.yml"


def test_kca09_domain_is_provider_neutral() -> None:
    text = (CORE.read_text(encoding="utf-8") + APP.read_text(encoding="utf-8")).casefold()
    for provider_name in ("stripe", "cakto", "mercadopago", "mercado pago", "pagbank"):
        assert provider_name not in text


def test_kca09_contract_exposes_required_provider_operations() -> None:
    text = CORE.read_text(encoding="utf-8")
    for operation in (
        "create_customer",
        "create_checkout",
        "create_subscription",
        "cancel_subscription",
        "change_subscription",
        "fetch_transaction",
        "verify_webhook",
    ):
        assert f"def {operation}(" in text


def test_kca09_keeps_secrets_as_references() -> None:
    app = APP.read_text(encoding="utf-8")
    assert "credential_secret_reference" in app
    assert "SecretStore" in app
    assert ".resolve(self._binding.credential_secret_reference)" in app
    assert "api_key =" not in app.casefold()
    assert "secret_key =" not in app.casefold()


def test_kca09_does_not_anticipate_webhook_inbox_or_reconciliation() -> None:
    combined = (CORE.read_text(encoding="utf-8") + APP.read_text(encoding="utf-8")).casefold()
    assert "webhook_inbox" not in combined
    assert "reconciliation_job" not in combined
    assert "dead_letter" not in combined


def test_kca09_gate_tracks_new_surfaces() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "application/commercial_billing.py" in workflow
    assert "tests/fitness/test_kca09_billing_provider.py" in workflow
