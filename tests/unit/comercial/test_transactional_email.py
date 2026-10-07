from __future__ import annotations

from email.message import EmailMessage

import httpx
import pytest

from core.seguranca.segredos import ReferenceSecretStore
from infra.comercial.transactional_email import (
    BrevoHTTPEmailConfig,
    BrevoHTTPPasswordRecoveryDispatcher,
    BrevoHTTPVerificationDispatcher,
    SMTPPasswordRecoveryDispatcher,
    SMTPVerificationConfig,
    SMTPVerificationDispatcher,
    build_password_recovery_dispatcher_from_env,
    build_verification_dispatcher_from_env,
)


class FakeSMTP:
    def __init__(self) -> None:
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages: list[EmailMessage] = []
        self.quit_called = False

    def starttls(self, *, context) -> None:
        assert context is not None
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)

    def quit(self) -> None:
        self.quit_called = True


def _dispatcher(fake: FakeSMTP) -> SMTPVerificationDispatcher:
    return SMTPVerificationDispatcher(
        config=SMTPVerificationConfig(
            host="smtp.example.test",
            port=587,
            from_email="no-reply@kordena.example",
            frontend_base_url="https://kordena.example",
            username="smtp-user",
            password_secret_reference="mapping:smtp-password",
        ),
        secret_store=ReferenceSecretStore(
            mapping={"smtp-password": "fixture-only-secret"}
        ),
        smtp_factory=lambda _config: fake,
    )



def _password_dispatcher(fake: FakeSMTP) -> SMTPPasswordRecoveryDispatcher:
    return SMTPPasswordRecoveryDispatcher(
        config=SMTPVerificationConfig(
            host="smtp.example.test",
            port=587,
            from_email="no-reply@kordena.example",
            frontend_base_url="https://kordena.example",
            username="smtp-user",
            password_secret_reference="mapping:smtp-password",
        ),
        secret_store=ReferenceSecretStore(
            mapping={"smtp-password": "fixture-only-secret"}
        ),
        smtp_factory=lambda _config: fake,
    )


def test_smtp_verification_dispatcher_sends_encoded_one_time_link() -> None:
    fake = FakeSMTP()
    dispatcher = _dispatcher(fake)

    dispatcher.send_verification(
        signup_id="signup/with space",
        email="OWNER@EXAMPLE.TEST",
        token="token+/with?reserved=value",
    )

    assert fake.started_tls is True
    assert fake.login_args == ("smtp-user", "fixture-only-secret")
    assert fake.quit_called is True
    assert len(fake.messages) == 1
    message = fake.messages[0]
    assert message["To"] == "owner@example.test"
    body = message.get_content()
    assert "https://kordena.example/signup/verify#" in body
    assert "signup_id=signup%2Fwith+space" in body
    assert "token=token%2B%2Fwith%3Freserved%3Dvalue" in body
    assert "fixture-only-secret" not in body


def test_smtp_config_requires_auth_secret_when_username_is_present() -> None:
    with pytest.raises(ValueError, match="transactional_email_auth_config_invalid"):
        SMTPVerificationConfig(
            host="smtp.example.test",
            port=587,
            from_email="no-reply@kordena.example",
            frontend_base_url="https://kordena.example",
            username="smtp-user",
        )


def test_password_recovery_dispatcher_uses_fragment_and_security_notice() -> None:
    fake = FakeSMTP()
    dispatcher = _password_dispatcher(fake)

    dispatcher.send_password_reset(
        email="OWNER@EXAMPLE.TEST",
        token="reset+/with?reserved=value",
    )
    dispatcher.send_password_changed(email="OWNER@EXAMPLE.TEST")

    assert len(fake.messages) == 2
    reset_body = fake.messages[0].get_content()
    assert "https://kordena.example/reset-password#" in reset_body
    assert "token=reset%2B%2Fwith%3Freserved%3Dvalue" in reset_body
    assert "30 minutos" in reset_body
    assert fake.messages[1]["Subject"] == "Sua senha do Kordena foi alterada"
    assert "sessões anteriores foram encerradas" in fake.messages[1].get_content()
    assert "fixture-only-secret" not in reset_body



def _brevo_config() -> BrevoHTTPEmailConfig:
    return BrevoHTTPEmailConfig(
        from_email="acesso@kordenaia.com.br",
        frontend_base_url="https://app.kordenaia.com.br",
        api_key_secret_reference="mapping:brevo-api-key",
    )


def test_brevo_http_verification_dispatcher_uses_https_api() -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            201,
            json={"messageId": "fixture-message-id"},
            request=httpx.Request("POST", url),
        )

    dispatcher = BrevoHTTPVerificationDispatcher(
        config=_brevo_config(),
        secret_store=ReferenceSecretStore(
            mapping={"brevo-api-key": "fixture-only-api-key"}
        ),
        http_post=fake_post,
    )

    dispatcher.send_verification(
        signup_id="signup/with space",
        email="OWNER@EXAMPLE.TEST",
        token="token+/with?reserved=value",
    )

    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["api-key"] == "fixture-only-api-key"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["sender"] == {
        "name": "Kordena",
        "email": "acesso@kordenaia.com.br",
    }
    assert payload["to"] == [{"email": "owner@example.test"}]
    assert payload["subject"] == "Confirme seu e-mail para ativar o Kordena"
    body = str(payload["textContent"])
    assert "https://app.kordenaia.com.br/signup/verify#" in body
    assert "signup_id=signup%2Fwith+space" in body
    assert "token=token%2B%2Fwith%3Freserved%3Dvalue" in body
    assert "fixture-only-api-key" not in body


def test_brevo_http_password_recovery_dispatcher_uses_https_api() -> None:
    payloads: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs):
        assert url == "https://api.brevo.com/v3/smtp/email"
        payload = kwargs["json"]
        assert isinstance(payload, dict)
        payloads.append(payload)
        return httpx.Response(
            201,
            json={"messageId": "fixture-message-id"},
            request=httpx.Request("POST", url),
        )

    dispatcher = BrevoHTTPPasswordRecoveryDispatcher(
        config=_brevo_config(),
        secret_store=ReferenceSecretStore(
            mapping={"brevo-api-key": "fixture-only-api-key"}
        ),
        http_post=fake_post,
    )

    dispatcher.send_password_reset(
        email="OWNER@EXAMPLE.TEST",
        token="reset+/with?reserved=value",
    )
    dispatcher.send_password_changed(email="OWNER@EXAMPLE.TEST")

    assert len(payloads) == 2
    reset_body = str(payloads[0]["textContent"])
    assert "https://app.kordenaia.com.br/reset-password#" in reset_body
    assert "token=reset%2B%2Fwith%3Freserved%3Dvalue" in reset_body
    assert payloads[1]["subject"] == "Sua senha do Kordena foi alterada"


def test_transactional_email_auto_prefers_brevo_api(monkeypatch) -> None:
    monkeypatch.setenv(
        "FM_AI_TRANSACTIONAL_EMAIL_BREVO_API_KEY",
        "fixture-only-api-key",
    )
    monkeypatch.setenv(
        "FM_AI_TRANSACTIONAL_EMAIL_FROM",
        "acesso@kordenaia.com.br",
    )
    monkeypatch.setenv(
        "FM_AI_PUBLIC_WEB_BASE_URL",
        "https://app.kordenaia.com.br",
    )
    monkeypatch.setenv(
        "FM_AI_TRANSACTIONAL_EMAIL_SMTP_HOST",
        "smtp.example.test",
    )
    monkeypatch.delenv("FM_AI_TRANSACTIONAL_EMAIL_PROVIDER", raising=False)

    secret_store = ReferenceSecretStore()
    verification = build_verification_dispatcher_from_env(
        secret_store=secret_store
    )
    recovery = build_password_recovery_dispatcher_from_env(
        secret_store=secret_store
    )

    assert isinstance(verification, BrevoHTTPVerificationDispatcher)
    assert isinstance(recovery, BrevoHTTPPasswordRecoveryDispatcher)


def test_transactional_email_can_force_smtp_even_with_brevo_key(monkeypatch) -> None:
    monkeypatch.setenv(
        "FM_AI_TRANSACTIONAL_EMAIL_BREVO_API_KEY",
        "fixture-only-api-key",
    )
    monkeypatch.setenv(
        "FM_AI_TRANSACTIONAL_EMAIL_FROM",
        "acesso@kordenaia.com.br",
    )
    monkeypatch.setenv(
        "FM_AI_PUBLIC_WEB_BASE_URL",
        "https://app.kordenaia.com.br",
    )
    monkeypatch.setenv(
        "FM_AI_TRANSACTIONAL_EMAIL_SMTP_HOST",
        "smtp.example.test",
    )
    monkeypatch.setenv("FM_AI_TRANSACTIONAL_EMAIL_PROVIDER", "smtp")

    verification = build_verification_dispatcher_from_env(
        secret_store=ReferenceSecretStore()
    )

    assert isinstance(verification, SMTPVerificationDispatcher)
