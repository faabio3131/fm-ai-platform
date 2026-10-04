from __future__ import annotations

import pytest

from infra.seguranca.google_oidc import GoogleIdentityError, verify_google_id_token


def test_google_identity_accepts_verified_gmail(monkeypatch) -> None:
    monkeypatch.setattr(
        "infra.seguranca.google_oidc.id_token.verify_oauth2_token",
        lambda token, request, audience: {
            "iss": "https://accounts.google.com",
            "sub": "google-sub-1",
            "email": "Pessoa@gmail.com",
            "email_verified": True,
            "name": "Pessoa",
        },
    )

    claims = verify_google_id_token("credential-valid", client_id="client-id")

    assert claims.subject == "google-sub-1"
    assert claims.email == "pessoa@gmail.com"
    assert claims.name == "Pessoa"


def test_google_identity_accepts_workspace_with_hd(monkeypatch) -> None:
    monkeypatch.setattr(
        "infra.seguranca.google_oidc.id_token.verify_oauth2_token",
        lambda token, request, audience: {
            "iss": "accounts.google.com",
            "sub": "google-sub-2",
            "email": "dono@empresa.com.br",
            "email_verified": True,
            "hd": "empresa.com.br",
        },
    )

    claims = verify_google_id_token("credential-valid", client_id="client-id")
    assert claims.hosted_domain == "empresa.com.br"


def test_google_identity_rejeita_email_externo_sem_autoridade_google(monkeypatch) -> None:
    monkeypatch.setattr(
        "infra.seguranca.google_oidc.id_token.verify_oauth2_token",
        lambda token, request, audience: {
            "iss": "https://accounts.google.com",
            "sub": "google-sub-3",
            "email": "pessoa@provedor-externo.com",
            "email_verified": True,
        },
    )

    with pytest.raises(
        GoogleIdentityError,
        match="google_identity_email_not_authoritative",
    ):
        verify_google_id_token("credential-valid", client_id="client-id")
