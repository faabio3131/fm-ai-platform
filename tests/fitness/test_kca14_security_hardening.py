from __future__ import annotations

from pathlib import Path

AUTH = Path("http_api/auth.py")
OPERATIONAL_AUTH = Path("http_api/operational_auth.py")
FRONTEND = Path("http_api/frontend_app.py")
FMCC = Path("http_api/fmcc_commercial_control.py")
BILLING_WEBHOOK = Path("http_api/commercial_billing_webhooks.py")
WORKFLOW = Path(".github/workflows/kordena-kca-commercial-gate.yml")


def test_kca14_session_rotation_and_fail_closed_are_explicit() -> None:
    auth = AUTH.read_text(encoding="utf-8")
    operational = OPERATIONAL_AUTH.read_text(encoding="utf-8")

    assert "secrets.token_urlsafe(32)" in auth
    assert "self._sessions.pop(sessao.session_id, None)" in auth
    assert "admin_elevado_ate=None" in auth
    assert 'key=_SESSION_COOKIE' in auth
    assert "httponly=True" in auth
    assert "secure=settings.commercial" in auth
    assert 'samesite="lax"' in auth

    assert "Resolve sessão web primeiro e Basic legado somente quando ela inexiste." in operational
    assert "auth_runtime.resolver_identidade(request)" in operational
    assert 'request.headers.get("x-tenant-id"' in operational
    assert 'request.headers.get("x-unit-id"' in operational
    assert "identidade.no_escopo_ativo(" in operational


def test_kca14_commercial_cors_and_checkout_boundaries_fail_closed() -> None:
    frontend = FRONTEND.read_text(encoding="utf-8")

    assert "if settings.commercial:" in frontend
    assert "return app" in frontend
    assert "allow_credentials=True" in frontend
    assert "DEV_FRONTEND_ORIGINS" in frontend


def test_kca14_fmcc_and_webhook_boundaries_require_governed_authentication() -> None:
    fmcc = FMCC.read_text(encoding="utf-8")
    webhook = BILLING_WEBHOOK.read_text(encoding="utf-8")

    assert "secrets.compare_digest" in fmcc
    assert "MIN_SERVICE_TOKEN_LENGTH = 32" in fmcc
    assert "STEP_UP_TTL = timedelta(minutes=15)" in fmcc
    assert "fmcc_control_plane.step_up_required" in fmcc

    assert "_MAX_BILLING_WEBHOOK_BYTES" in webhook
    assert "dict(request.headers.items())" in webhook
    assert "billing_webhook_replay_conflict" in webhook


def test_kca14_targeted_gate_includes_adversarial_security_matrix() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    required = (
        "tests/api/test_operational_session_sso_http_contract.py",
        "tests/api/test_auth_admin_stepup_http_contract.py",
        "tests/api/test_auth_membership_http_contract.py",
        "tests/api/test_commercial_billing_webhook_http_contract.py",
        "tests/api/test_fmcc_commercial_control_http_contract.py",
        "tests/fitness/test_f14_transversal_rbac_security_v1.py",
        "tests/fitness/test_kca04_entitlement.py",
        "tests/fitness/test_kca06_public_signup.py",
        "tests/fitness/test_kca10_billing_events.py",
        "tests/fitness/test_kca12_fmcc_control_plane.py",
        "tests/fitness/test_kca13_observability.py",
        "tests/fitness/test_kca14_security_hardening.py",
        "tests/integration/comercial",
    )
    for path in required:
        assert path in workflow, path
