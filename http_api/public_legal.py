"""Superfície pública e versionada dos documentos jurídicos do Kordena."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from core.comercial.legal import (
    LegalDocumentSnapshot,
    LegalDocumentType,
    active_legal_document,
    active_legal_documents,
)


def _metadata(document: LegalDocumentSnapshot) -> dict[str, object]:
    return {
        "document_type": document.document_type.value,
        "version": document.version,
        "effective_at": document.effective_at.isoformat(),
        "expires_at": document.expires_at.isoformat() if document.expires_at else None,
        "sha256": document.content_sha256,
        "public_path": document.public_path,
        "acceptance_action": document.acceptance_action.value,
    }


def build_public_legal_router() -> APIRouter:
    router = APIRouter(prefix="/v1/public/legal", tags=["public-legal"])

    @router.get("/documents")
    def list_active_documents() -> dict[str, object]:
        return {
            "documents": [
                _metadata(document) for document in active_legal_documents()
            ]
        }

    @router.get("/documents/{document_type}")
    def get_active_document(document_type: str):
        try:
            kind = LegalDocumentType(document_type.strip().casefold())
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"erro": "legal_document_not_found"},
            )
        document = active_legal_document(kind)
        payload = _metadata(document)
        payload["content"] = document.content
        return payload

    return router
