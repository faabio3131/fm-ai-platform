"""Verificação server-side do Google Identity Services para autenticação Kordena."""

from __future__ import annotations

from dataclasses import dataclass

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token


class GoogleIdentityError(ValueError):
    """Token Google ausente, inválido ou inadequado para login seguro."""


class GoogleIdentityUnavailable(RuntimeError):
    """Falha transitória ao consultar/verificar infraestrutura Google."""


@dataclass(frozen=True)
class GoogleIdentityClaims:
    subject: str
    email: str
    name: str | None
    hosted_domain: str | None


def verify_google_id_token(
    credential: str,
    *,
    client_id: str,
) -> GoogleIdentityClaims:
    token = credential.strip()
    audience = client_id.strip()
    if not token or not audience:
        raise GoogleIdentityError("google_identity_unavailable")
    try:
        claims = id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            audience,
        )
    except GoogleAuthError as exc:
        raise GoogleIdentityUnavailable("google_identity_unavailable") from exc
    except (ValueError, TypeError) as exc:
        raise GoogleIdentityError("google_identity_invalid") from exc

    issuer = str(claims.get("iss") or "")
    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().casefold()
    email_verified = claims.get("email_verified") is True
    hosted_domain = str(claims.get("hd") or "").strip().casefold() or None
    name = str(claims.get("name") or "").strip() or None

    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleIdentityError("google_identity_invalid_issuer")
    if not subject or not email or "@" not in email or not email_verified:
        raise GoogleIdentityError("google_identity_unverified")

    # Para vinculação automática a uma conta Kordena existente, seguimos a
    # recomendação do Google: Gmail é autoritativo e Google Workspace é
    # autoritativo quando a claim hd está presente. Contas Google criadas sobre
    # e-mails externos sem hd exigem outro fator antes de vincular.
    domain = email.rsplit("@", 1)[-1]
    if domain not in {"gmail.com", "googlemail.com"} and hosted_domain is None:
        raise GoogleIdentityError("google_identity_email_not_authoritative")

    return GoogleIdentityClaims(
        subject=subject,
        email=email,
        name=name,
        hosted_domain=hosted_domain,
    )
