"use client";

import { API_BASE_URL } from "@/lib/api";

export type LegalDocumentType = "terms" | "privacy" | "dpa";

export interface LegalDocumentMetadata {
  document_type: LegalDocumentType;
  version: string;
  effective_at: string;
  expires_at: string | null;
  sha256: string;
  public_path: string;
  acceptance_action: "accepted" | "acknowledged" | "incorporated";
}

export interface LegalDocumentDetail extends LegalDocumentMetadata {
  content: string;
}

export async function getActiveLegalDocuments(): Promise<LegalDocumentMetadata[]> {
  const response = await fetch(API_BASE_URL + "/v1/public/legal/documents", {
    method: "GET",
    credentials: "omit",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("legal_documents_unavailable");
  }
  const payload = (await response.json()) as { documents: LegalDocumentMetadata[] };
  return payload.documents;
}

export async function getLegalDocument(
  documentType: LegalDocumentType,
): Promise<LegalDocumentDetail> {
  const response = await fetch(
    API_BASE_URL + "/v1/public/legal/documents/" + encodeURIComponent(documentType),
    {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      headers: { Accept: "application/json" },
    },
  );
  if (!response.ok) {
    throw new Error("legal_document_unavailable");
  }
  return (await response.json()) as LegalDocumentDetail;
}
