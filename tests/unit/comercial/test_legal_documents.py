from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.comercial.erros import DadoComercialInvalido
from core.comercial.legal import (
    LEGAL_DOCUMENT_VERSIONS,
    active_legal_acceptance_claims,
    active_legal_documents,
    validate_legal_acceptance_claims,
)


def test_legal_v1_expoe_tres_documentos_ativos_com_hash_do_conteudo() -> None:
    documents = active_legal_documents()
    assert {document.document_type.value for document in documents} == {
        "terms",
        "privacy",
        "dpa",
    }
    assert {document.version for document in documents} == {"1.0"}
    assert all(len(document.content_sha256) == 64 for document in documents)
    assert all(document.content.startswith("#") for document in documents)
    assert {document.public_path for document in documents} == {
        "/legal/termos",
        "/legal/privacidade",
        "/legal/dpa",
    }


def test_claim_exato_da_versao_ativa_e_aceito() -> None:
    claims = active_legal_acceptance_claims()
    validated = validate_legal_acceptance_claims(claims)
    assert len(validated) == 3


@pytest.mark.parametrize("field,value,error", [
    ("version", "0.9", "signup_legal_document_version_invalid"),
    ("sha256", "0" * 64, "signup_legal_document_hash_invalid"),
])
def test_claim_divergente_falha_fechado(field: str, value: str, error: str) -> None:
    claims = active_legal_acceptance_claims()
    claims["terms"][field] = value
    with pytest.raises(DadoComercialInvalido, match=error):
        validate_legal_acceptance_claims(claims)


def test_claim_incompleto_falha_fechado() -> None:
    claims = active_legal_acceptance_claims()
    claims.pop("privacy")
    with pytest.raises(DadoComercialInvalido, match="signup_legal_documents_required"):
        validate_legal_acceptance_claims(claims)


def test_definicao_expirada_deixa_de_ser_ativa() -> None:
    now = datetime.now(timezone.utc)
    definition = replace(
        LEGAL_DOCUMENT_VERSIONS[0],
        effective_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    assert definition.is_active(now) is False
