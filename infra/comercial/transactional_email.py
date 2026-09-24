"""Provider-neutral SMTP dispatcher for Kordena public-signup verification."""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from core.seguranca.segredos import SecretStore


@dataclass(frozen=True, kw_only=True)
class SMTPVerificationConfig:
    host: str
    port: int
    from_email: str
    frontend_base_url: str
    security: str = "starttls"
    username: str | None = None
    password_secret_reference: str | None = None
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        host = self.host.strip()
        sender = self.from_email.strip()
        base = self.frontend_base_url.strip().rstrip("/")
        security = self.security.strip().lower()
        if not host or not sender or "@" not in sender:
            raise ValueError("transactional_email_config_invalid")
        if not 1 <= self.port <= 65535 or self.timeout_seconds <= 0:
            raise ValueError("transactional_email_config_invalid")
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("transactional_email_frontend_url_invalid")
        if security not in {"starttls", "ssl"}:
            raise ValueError("transactional_email_security_invalid")
        username = self.username.strip() if self.username else None
        secret_ref = (
            self.password_secret_reference.strip()
            if self.password_secret_reference
            else None
        )
        if bool(username) != bool(secret_ref):
            raise ValueError("transactional_email_auth_config_invalid")
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "from_email", sender)
        object.__setattr__(self, "frontend_base_url", base)
        object.__setattr__(self, "security", security)
        object.__setattr__(self, "username", username)
        object.__setattr__(self, "password_secret_reference", secret_ref)


SMTPFactory = Callable[[SMTPVerificationConfig], Any]


def _default_smtp_factory(config: SMTPVerificationConfig) -> Any:
    if config.security == "ssl":
        return smtplib.SMTP_SSL(
            config.host,
            config.port,
            timeout=config.timeout_seconds,
            context=ssl.create_default_context(),
        )
    return smtplib.SMTP(
        config.host,
        config.port,
        timeout=config.timeout_seconds,
    )


class SMTPVerificationDispatcher:
    """Sends one-time verification links without persisting provider credentials."""

    def __init__(
        self,
        *,
        config: SMTPVerificationConfig,
        secret_store: SecretStore,
        smtp_factory: SMTPFactory = _default_smtp_factory,
    ) -> None:
        self._config = config
        self._secret_store = secret_store
        self._smtp_factory = smtp_factory

    def verification_url(self, *, signup_id: str, token: str) -> str:
        signup = signup_id.strip()
        verification_token = token.strip()
        if not signup or not verification_token:
            raise ValueError("signup_verification_link_invalid")
        query = urlencode({"signup_id": signup, "token": verification_token})
        return f"{self._config.frontend_base_url}/signup/verify?{query}"

    def send_verification(self, *, signup_id: str, email: str, token: str) -> None:
        recipient = email.strip().casefold()
        if not recipient or "@" not in recipient:
            raise ValueError("transactional_email_recipient_invalid")

        message = EmailMessage()
        message["Subject"] = "Confirme seu e-mail para ativar o Kordena"
        message["From"] = self._config.from_email
        message["To"] = recipient
        link = self.verification_url(signup_id=signup_id, token=token)
        message.set_content(
            "Confirme seu e-mail para continuar a ativação do Kordena:\n\n"
            f"{link}\n\n"
            "Se você não iniciou este cadastro, ignore esta mensagem."
        )

        client = self._smtp_factory(self._config)
        try:
            if self._config.security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if self._config.username:
                reference = self._config.password_secret_reference
                if reference is None:
                    raise RuntimeError("transactional_email_secret_reference_missing")
                password = self._secret_store.resolve(reference).reveal()
                client.login(self._config.username, password)
            client.send_message(message)
        finally:
            try:
                client.quit()
            except Exception:  # noqa: BLE001 - cleanup must not hide primary failure
                pass


def build_smtp_verification_dispatcher_from_env(
    *, secret_store: SecretStore
) -> SMTPVerificationDispatcher:
    host = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_SMTP_HOST", "").strip()
    sender = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_FROM", "").strip()
    base_url = os.getenv("FM_AI_PUBLIC_WEB_BASE_URL", "").strip()
    if not host or not sender or not base_url:
        raise RuntimeError("transactional_email_runtime_not_configured")

    raw_port = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_SMTP_PORT", "587").strip()
    raw_timeout = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_TIMEOUT_SECONDS", "10").strip()
    try:
        port = int(raw_port)
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("transactional_email_runtime_invalid") from exc

    username = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_USERNAME", "").strip() or None
    secret_reference = (
        os.getenv(
            "FM_AI_TRANSACTIONAL_EMAIL_PASSWORD_SECRET_REF",
            "env:FM_AI_TRANSACTIONAL_EMAIL_PASSWORD",
        ).strip()
        if username
        else None
    )
    return SMTPVerificationDispatcher(
        config=SMTPVerificationConfig(
            host=host,
            port=port,
            from_email=sender,
            frontend_base_url=base_url,
            security=os.getenv(
                "FM_AI_TRANSACTIONAL_EMAIL_SECURITY", "starttls"
            ).strip(),
            username=username,
            password_secret_reference=secret_reference,
            timeout_seconds=timeout,
        ),
        secret_store=secret_store,
    )
