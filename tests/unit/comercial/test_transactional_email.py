from __future__ import annotations

from email.message import EmailMessage

import pytest

from core.seguranca.segredos import ReferenceSecretStore
from infra.comercial.transactional_email import (
    SMTPVerificationConfig,
    SMTPVerificationDispatcher,
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
