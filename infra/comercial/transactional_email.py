"""Dispatchers transacionais do Kordena via SMTP ou API HTTPS da Brevo."""

from __future__ import annotations

import os
import smtplib
import ssl
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from core.seguranca.erros import ReferenciaSegredoInvalida, SegredoAusente
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
        return f"{self._config.frontend_base_url}/signup/verify#{query}"

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
            with suppress(Exception):
                client.quit()


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

class SMTPPasswordRecoveryDispatcher:
    """Envio SMTP para redefinição de senha e aviso de segurança."""

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

    def password_reset_url(self, *, token: str) -> str:
        raw = token.strip()
        if not raw:
            raise ValueError("password_recovery_link_invalid")
        # Fragment evita que o token seja enviado ao servidor web em logs de URL.
        fragment = urlencode({"token": raw})
        return f"{self._config.frontend_base_url}/reset-password#{fragment}"

    def _send(self, message: EmailMessage) -> None:
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
            with suppress(Exception):
                client.quit()

    def send_password_reset(self, *, email: str, token: str) -> None:
        recipient = email.strip().casefold()
        if not recipient or "@" not in recipient:
            raise ValueError("transactional_email_recipient_invalid")
        link = self.password_reset_url(token=token)
        message = EmailMessage()
        message["Subject"] = "Redefina sua senha do Kordena"
        message["From"] = self._config.from_email
        message["To"] = recipient
        message.set_content(
            "Recebemos uma solicitação para redefinir a senha do seu acesso Kordena.\n\n"
            f"{link}\n\n"
            "Este link expira em 30 minutos e só pode ser usado uma vez.\n"
            "Se você não solicitou a redefinição, ignore esta mensagem."
        )
        self._send(message)

    def send_password_changed(self, *, email: str) -> None:
        recipient = email.strip().casefold()
        if not recipient or "@" not in recipient:
            raise ValueError("transactional_email_recipient_invalid")
        message = EmailMessage()
        message["Subject"] = "Sua senha do Kordena foi alterada"
        message["From"] = self._config.from_email
        message["To"] = recipient
        message.set_content(
            "A senha do seu acesso Kordena foi alterada com sucesso.\n\n"
            "Todas as sessões anteriores foram encerradas por segurança.\n"
            "Se você não realizou esta alteração, contate o suporte imediatamente."
        )
        self._send(message)


def build_smtp_password_recovery_dispatcher_from_env(
    *,
    secret_store: SecretStore,
    required: bool = False,
) -> SMTPPasswordRecoveryDispatcher | None:
    host = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_SMTP_HOST", "").strip()
    sender = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_FROM", "").strip()
    base_url = os.getenv("FM_AI_PUBLIC_WEB_BASE_URL", "").strip()
    if not host or not sender or not base_url:
        if required:
            raise RuntimeError("transactional_email_runtime_not_configured")
        return None

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
    return SMTPPasswordRecoveryDispatcher(
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


@dataclass(frozen=True, kw_only=True)
class BrevoHTTPEmailConfig:
    """Configuração do transporte HTTPS da Brevo sem persistir a API key."""

    from_email: str
    frontend_base_url: str
    api_key_secret_reference: str = "env:FM_AI_TRANSACTIONAL_EMAIL_BREVO_API_KEY"
    from_name: str = "Kordena"
    api_url: str = "https://api.brevo.com/v3/smtp/email"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        sender = self.from_email.strip().casefold()
        base = self.frontend_base_url.strip().rstrip("/")
        secret_ref = self.api_key_secret_reference.strip()
        from_name = self.from_name.strip() or "Kordena"
        api_url = self.api_url.strip()

        if not sender or "@" not in sender or not secret_ref:
            raise ValueError("transactional_email_config_invalid")
        if self.timeout_seconds <= 0:
            raise ValueError("transactional_email_config_invalid")

        parsed_base = urlparse(base)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ValueError("transactional_email_frontend_url_invalid")

        parsed_api = urlparse(api_url)
        if parsed_api.scheme != "https" or not parsed_api.netloc:
            raise ValueError("transactional_email_provider_url_invalid")

        object.__setattr__(self, "from_email", sender)
        object.__setattr__(self, "frontend_base_url", base)
        object.__setattr__(self, "api_key_secret_reference", secret_ref)
        object.__setattr__(self, "from_name", from_name)
        object.__setattr__(self, "api_url", api_url)


HTTPPost = Callable[..., httpx.Response]


def _default_http_post(url: str, **kwargs: Any) -> httpx.Response:
    return httpx.post(url, **kwargs)


class _BrevoHTTPDispatcherBase:
    def __init__(
        self,
        *,
        config: BrevoHTTPEmailConfig,
        secret_store: SecretStore,
        http_post: HTTPPost = _default_http_post,
    ) -> None:
        self._config = config
        self._secret_store = secret_store
        self._http_post = http_post

    @staticmethod
    def _recipient(email: str) -> str:
        recipient = email.strip().casefold()
        if not recipient or "@" not in recipient:
            raise ValueError("transactional_email_recipient_invalid")
        return recipient

    def _send(self, *, email: str, subject: str, text_content: str) -> None:
        recipient = self._recipient(email)
        api_key = self._secret_store.resolve(
            self._config.api_key_secret_reference
        ).reveal()
        payload = {
            "sender": {
                "name": self._config.from_name,
                "email": self._config.from_email,
            },
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": text_content,
        }
        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        try:
            response = self._http_post(
                self._config.api_url,
                headers=headers,
                json=payload,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError("transactional_email_provider_timeout") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("transactional_email_provider_unavailable") from exc

        if not 200 <= response.status_code < 300:
            raise RuntimeError("transactional_email_provider_rejected")


class BrevoHTTPVerificationDispatcher(_BrevoHTTPDispatcherBase):
    """Envia verificação de cadastro pela API HTTPS da Brevo."""

    def verification_url(self, *, signup_id: str, token: str) -> str:
        signup = signup_id.strip()
        verification_token = token.strip()
        if not signup or not verification_token:
            raise ValueError("signup_verification_link_invalid")
        query = urlencode({"signup_id": signup, "token": verification_token})
        return f"{self._config.frontend_base_url}/signup/verify#{query}"

    def send_verification(self, *, signup_id: str, email: str, token: str) -> None:
        link = self.verification_url(signup_id=signup_id, token=token)
        self._send(
            email=email,
            subject="Confirme seu e-mail para ativar o Kordena",
            text_content=(
                "Confirme seu e-mail para continuar a ativação do Kordena:\n\n"
                f"{link}\n\n"
                "Se você não iniciou este cadastro, ignore esta mensagem."
            ),
        )


class BrevoHTTPPasswordRecoveryDispatcher(_BrevoHTTPDispatcherBase):
    """Envia recuperação de senha e avisos de segurança pela Brevo HTTPS."""

    def password_reset_url(self, *, token: str) -> str:
        raw = token.strip()
        if not raw:
            raise ValueError("password_recovery_link_invalid")
        fragment = urlencode({"token": raw})
        return f"{self._config.frontend_base_url}/reset-password#{fragment}"

    def send_password_reset(self, *, email: str, token: str) -> None:
        link = self.password_reset_url(token=token)
        self._send(
            email=email,
            subject="Redefina sua senha do Kordena",
            text_content=(
                "Recebemos uma solicitação para redefinir a senha do seu acesso Kordena.\n\n"
                f"{link}\n\n"
                "Este link expira em 30 minutos e só pode ser usado uma vez.\n"
                "Se você não solicitou a redefinição, ignore esta mensagem."
            ),
        )

    def send_password_changed(self, *, email: str) -> None:
        self._send(
            email=email,
            subject="Sua senha do Kordena foi alterada",
            text_content=(
                "A senha do seu acesso Kordena foi alterada com sucesso.\n\n"
                "Todas as sessões anteriores foram encerradas por segurança.\n"
                "Se você não realizou esta alteração, contate o suporte imediatamente."
            ),
        )


def _build_brevo_http_config_from_env(
    *,
    secret_store: SecretStore,
    required: bool,
) -> BrevoHTTPEmailConfig | None:
    sender = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_FROM", "").strip()
    base_url = os.getenv("FM_AI_PUBLIC_WEB_BASE_URL", "").strip()
    secret_reference = os.getenv(
        "FM_AI_TRANSACTIONAL_EMAIL_BREVO_API_KEY_SECRET_REF",
        "env:FM_AI_TRANSACTIONAL_EMAIL_BREVO_API_KEY",
    ).strip()
    if not sender or not base_url or not secret_reference:
        if required:
            raise RuntimeError("transactional_email_runtime_not_configured")
        return None

    try:
        secret_store.resolve(secret_reference)
    except (SegredoAusente, ReferenciaSegredoInvalida) as exc:
        if required:
            raise RuntimeError("transactional_email_runtime_not_configured") from exc
        return None

    raw_timeout = os.getenv(
        "FM_AI_TRANSACTIONAL_EMAIL_TIMEOUT_SECONDS", "10"
    ).strip()
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("transactional_email_runtime_invalid") from exc

    return BrevoHTTPEmailConfig(
        from_email=sender,
        frontend_base_url=base_url,
        api_key_secret_reference=secret_reference,
        from_name=os.getenv("FM_AI_TRANSACTIONAL_EMAIL_FROM_NAME", "Kordena").strip(),
        api_url=os.getenv(
            "FM_AI_TRANSACTIONAL_EMAIL_BREVO_API_URL",
            "https://api.brevo.com/v3/smtp/email",
        ).strip(),
        timeout_seconds=timeout,
    )


def build_brevo_verification_dispatcher_from_env(
    *,
    secret_store: SecretStore,
    required: bool = False,
) -> BrevoHTTPVerificationDispatcher | None:
    config = _build_brevo_http_config_from_env(
        secret_store=secret_store,
        required=required,
    )
    if config is None:
        return None
    return BrevoHTTPVerificationDispatcher(
        config=config,
        secret_store=secret_store,
    )


def build_brevo_password_recovery_dispatcher_from_env(
    *,
    secret_store: SecretStore,
    required: bool = False,
) -> BrevoHTTPPasswordRecoveryDispatcher | None:
    config = _build_brevo_http_config_from_env(
        secret_store=secret_store,
        required=required,
    )
    if config is None:
        return None
    return BrevoHTTPPasswordRecoveryDispatcher(
        config=config,
        secret_store=secret_store,
    )


def _transactional_email_provider() -> str:
    provider = os.getenv("FM_AI_TRANSACTIONAL_EMAIL_PROVIDER", "").strip().casefold()
    if provider in {"", "auto"}:
        return "auto"
    if provider in {"brevo", "brevo_api", "brevo-http", "https"}:
        return "brevo"
    if provider == "smtp":
        return "smtp"
    raise RuntimeError("transactional_email_provider_invalid")


def build_verification_dispatcher_from_env(
    *, secret_store: SecretStore
) -> BrevoHTTPVerificationDispatcher | SMTPVerificationDispatcher:
    provider = _transactional_email_provider()
    if provider == "brevo":
        dispatcher = build_brevo_verification_dispatcher_from_env(
            secret_store=secret_store,
            required=True,
        )
        assert dispatcher is not None
        return dispatcher
    if provider == "smtp":
        return build_smtp_verification_dispatcher_from_env(
            secret_store=secret_store
        )

    brevo = build_brevo_verification_dispatcher_from_env(
        secret_store=secret_store,
        required=False,
    )
    if brevo is not None:
        return brevo
    return build_smtp_verification_dispatcher_from_env(
        secret_store=secret_store
    )


def build_password_recovery_dispatcher_from_env(
    *,
    secret_store: SecretStore,
    required: bool = False,
) -> BrevoHTTPPasswordRecoveryDispatcher | SMTPPasswordRecoveryDispatcher | None:
    provider = _transactional_email_provider()
    if provider == "brevo":
        return build_brevo_password_recovery_dispatcher_from_env(
            secret_store=secret_store,
            required=required,
        )
    if provider == "smtp":
        return build_smtp_password_recovery_dispatcher_from_env(
            secret_store=secret_store,
            required=required,
        )

    brevo = build_brevo_password_recovery_dispatcher_from_env(
        secret_store=secret_store,
        required=False,
    )
    if brevo is not None:
        return brevo
    return build_smtp_password_recovery_dispatcher_from_env(
        secret_store=secret_store,
        required=required,
    )
