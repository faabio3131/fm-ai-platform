import { apiRequest } from "@/lib/api";

export type FiscalEnvironment = "homologation" | "production";

export interface FiscalWorkspaceResponse {
  tenant_id: string;
  unit_id: string;
  environment: FiscalEnvironment;
  summary: {
    outbound_documents: number;
    inbound_documents: number;
    manifestations: number;
    intake_captures: number;
    purchase_orders: number;
    receipts: number;
    financial_obligations: number;
    archive_entries: number;
  };
  outbound: Array<{
    document_id: string;
    document_kind: string;
    state: string;
    access_key: string | null;
    protocol_reference: string | null;
    rejection_code: string | null;
    rejection_message: string | null;
    updated_at: string | null;
  }>;
  inbound: Array<{
    inbound_id: string;
    access_key: string;
    nsu: string | null;
    issuer_document: string | null;
    issuer_name: string | null;
    status: string;
    source: string;
    discovered_at: string | null;
    updated_at: string | null;
  }>;
  manifestations: Array<{
    manifestation_id: string;
    access_key: string;
    event_type: string;
    protocol_reference: string | null;
    occurred_at: string | null;
  }>;
  intake: Array<{
    capture_id: string;
    source: string;
    authority: string;
    status: string;
    media_type: string;
    last_error_code: string | null;
    captured_at: string | null;
    updated_at: string | null;
  }>;
  procurement: {
    orders: Array<{
      pedido_id: string;
      fornecedor_id: string;
      status: string;
      updated_at: string | null;
    }>;
    receipts: Array<{
      recebimento_id: string;
      pedido_id: string;
      inbound_id: string;
      access_key: string;
      status: string;
      confirmed_at: string | null;
    }>;
  };
  financial: Array<{
    obrigacao_id: string;
    fornecedor_id: string;
    pedido_id: string;
    recebimento_id: string;
    status: string;
    reconciliation: string;
    original_value: string;
    adjusted_value: string;
    balance: string;
    currency: string;
    created_at: string | null;
  }>;
  configuration: null | {
    configuration_id: string;
    provider: string;
    environment: string;
    enabled: boolean;
    homologated: boolean;
    homologation_evidence_reference: string | null;
    version: number;
    credential_roles: string[];
  };
  capabilities: {
    configure: boolean;
    certificate: boolean;
    cancel: boolean;
    inutilize: boolean;
    manifest: boolean;
    purchases_view: boolean;
    purchases_receive: boolean;
    archive_view: boolean;
  };
}

export interface FiscalArchiveResponse {
  environment: FiscalEnvironment;
  entries: Array<{
    entry_id: string;
    document_reference: string;
    kind: string;
    content_sha256: string;
    media_type: string;
    archived_at: string | null;
    retention_policy_id: string;
    retention_policy_version: number;
    retain_until: string | null;
  }>;
}

export async function getFiscalWorkspace(
  environment: FiscalEnvironment,
): Promise<FiscalWorkspaceResponse> {
  return apiRequest<FiscalWorkspaceResponse>(
    `/v1/admin/fiscal/workspace?environment=${environment}`,
    { credentials: "include" },
  );
}

export async function getFiscalArchive(
  environment: FiscalEnvironment,
): Promise<FiscalArchiveResponse> {
  return apiRequest<FiscalArchiveResponse>(
    `/v1/admin/fiscal/archive?environment=${environment}`,
    { credentials: "include" },
  );
}
