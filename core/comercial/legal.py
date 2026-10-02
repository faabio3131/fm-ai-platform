"""Autoridade canônica de versões jurídicas do Kordena V1.

Os documentos jurídicos permanecem em docs/legal como fonte única de conteúdo.
Esta camada vincula cada versão a um caminho público estável e calcula o SHA-256
sobre o conteúdo realmente publicado, evitando duplicação silenciosa de texto.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from core.comercial.erros import DadoComercialInvalido


class LegalDocumentType(StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"
    DPA = "dpa"


class LegalAcceptanceAction(StrEnum):
    ACCEPTED = "accepted"
    ACKNOWLEDGED = "acknowledged"
    INCORPORATED = "incorporated"


@dataclass(frozen=True, kw_only=True)
class LegalDocumentDefinition:
    document_type: LegalDocumentType
    version: str
    effective_at: datetime
    expires_at: datetime | None
    repository_path: str
    public_path: str
    acceptance_action: LegalAcceptanceAction

    def is_active(self, at: datetime) -> bool:
        moment = at.astimezone(timezone.utc)
        if moment < self.effective_at.astimezone(timezone.utc):
            return False
        return not (
            self.expires_at is not None
            and moment >= self.expires_at.astimezone(timezone.utc)
        )


@dataclass(frozen=True, kw_only=True)
class LegalDocumentSnapshot:
    document_type: LegalDocumentType
    version: str
    effective_at: datetime
    expires_at: datetime | None
    public_path: str
    acceptance_action: LegalAcceptanceAction
    content_sha256: str
    content: str


_EFFECTIVE_V1 = datetime(2026, 9, 30, tzinfo=timezone.utc)

LEGAL_DOCUMENT_VERSIONS: tuple[LegalDocumentDefinition, ...] = (
    LegalDocumentDefinition(
        document_type=LegalDocumentType.TERMS,
        version="1.0",
        effective_at=_EFFECTIVE_V1,
        expires_at=None,
        repository_path="docs/legal/01_TERMOS_DE_USO_KORDENA_V1.md",
        public_path="/legal/termos",
        acceptance_action=LegalAcceptanceAction.ACCEPTED,
    ),
    LegalDocumentDefinition(
        document_type=LegalDocumentType.PRIVACY,
        version="1.0",
        effective_at=_EFFECTIVE_V1,
        expires_at=None,
        repository_path="docs/legal/02_POLITICA_PRIVACIDADE_LGPD_KORDENA_V1.md",
        public_path="/legal/privacidade",
        acceptance_action=LegalAcceptanceAction.ACKNOWLEDGED,
    ),
    LegalDocumentDefinition(
        document_type=LegalDocumentType.DPA,
        version="1.0",
        effective_at=_EFFECTIVE_V1,
        expires_at=None,
        repository_path="docs/legal/03_DPA_TRATAMENTO_DADOS_KORDENA_V1.md",
        public_path="/legal/dpa",
        acceptance_action=LegalAcceptanceAction.INCORPORATED,
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_content(definition: LegalDocumentDefinition) -> str:
    path = _repo_root() / definition.repository_path
    if not path.is_file():
        raise RuntimeError(
            "legal_document_missing:"
            f"{definition.document_type.value}:{definition.version}"
        )
    return path.read_text(encoding="utf-8")


def _snapshot(definition: LegalDocumentDefinition) -> LegalDocumentSnapshot:
    content = _read_content(definition)
    return LegalDocumentSnapshot(
        document_type=definition.document_type,
        version=definition.version,
        effective_at=definition.effective_at,
        expires_at=definition.expires_at,
        public_path=definition.public_path,
        acceptance_action=definition.acceptance_action,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        content=content,
    )


def active_legal_documents(
    *,
    at: datetime | None = None,
) -> tuple[LegalDocumentSnapshot, ...]:
    moment = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    resolved: list[LegalDocumentSnapshot] = []
    for document_type in LegalDocumentType:
        candidates = [
            definition
            for definition in LEGAL_DOCUMENT_VERSIONS
            if (
                definition.document_type is document_type
                and definition.is_active(moment)
            )
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                "legal_document_active_version_invalid:"
                f"{document_type.value}:{len(candidates)}"
            )
        resolved.append(_snapshot(candidates[0]))
    return tuple(resolved)


def active_legal_document(
    document_type: LegalDocumentType,
    *,
    at: datetime | None = None,
) -> LegalDocumentSnapshot:
    for document in active_legal_documents(at=at):
        if document.document_type is document_type:
            return document
    raise RuntimeError(f"legal_document_not_active:{document_type.value}")


def active_legal_acceptance_claims(
    *,
    at: datetime | None = None,
) -> dict[str, dict[str, str]]:
    return {
        document.document_type.value: {
            "version": document.version,
            "sha256": document.content_sha256,
        }
        for document in active_legal_documents(at=at)
    }


def validate_legal_acceptance_claims(
    claims: Mapping[str, Mapping[str, str]],
    *,
    at: datetime | None = None,
) -> tuple[LegalDocumentSnapshot, ...]:
    active = active_legal_documents(at=at)
    expected_types = {document.document_type.value for document in active}
    if set(claims) != expected_types:
        raise DadoComercialInvalido("signup_legal_documents_required")

    for document in active:
        claim = claims.get(document.document_type.value)
        if claim is None:
            raise DadoComercialInvalido("signup_legal_documents_required")
        if str(claim.get("version", "")).strip() != document.version:
            raise DadoComercialInvalido("signup_legal_document_version_invalid")
        supplied_hash = str(claim.get("sha256", "")).strip().casefold()
        if supplied_hash != document.content_sha256:
            raise DadoComercialInvalido("signup_legal_document_hash_invalid")

    return active
