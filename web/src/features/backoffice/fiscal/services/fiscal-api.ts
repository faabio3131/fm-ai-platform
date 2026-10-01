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
    contingency_entries: number;
    products_pending_fiscal: number;
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
  products_pending_fiscal: {
    available: boolean;
    items: Array<{
      product_id: string;
      name: string;
    }>;
  };
  contingency: Array<{
    entry_id: string;
    operation: string;
    status: string;
    attempt_count: number;
    available_at: string | null;
    last_error: string | null;
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

export interface FiscalOperationResponse {
  status: string;
  request_id: string;
  provider: string;
  provider_request_id: string | null;
  event_protocol_reference: string | null;
  rejection_code: string | null;
  rejection_message: string | null;
}

export async function cancelFiscalDocument(
  accessKey: string,
  payload: {
    environment: FiscalEnvironment;
    authorization_protocol: string;
    justification: string;
  },
): Promise<FiscalOperationResponse> {
  return apiRequest<FiscalOperationResponse>(
    `/v1/admin/fiscal/documents/${encodeURIComponent(accessKey)}/cancel`,
    {
      method: "POST",
      credentials: "include",
      body: JSON.stringify(payload),
    },
  );
}

export async function inutilizeFiscalNumbers(payload: {
  environment: FiscalEnvironment;
  model: 55 | 65;
  series: number;
  first_number: number;
  last_number: number;
  justification: string;
}): Promise<FiscalOperationResponse> {
  return apiRequest<FiscalOperationResponse>("/v1/admin/fiscal/inutilizations", {
    method: "POST",
    credentials: "include",
    body: JSON.stringify(payload),
  });
}


function idempotencyHeaders(key?: string): HeadersInit {
  return key ? { "Idempotency-Key": key } : {};
}

export async function queryFiscalDocument(
  accessKey: string,
  environment: FiscalEnvironment,
): Promise<{
  status: string;
  access_key: string;
  provider: string;
  provider_request_id: string | null;
  protocol_reference: string | null;
}> {
  return apiRequest(
    `/v1/admin/fiscal/documents/${encodeURIComponent(accessKey)}/query?environment=${environment}`,
    { method: "POST", credentials: "include" },
  );
}

export async function uploadOfficialFiscalXml(payload: {
  environment: FiscalEnvironment;
  content_base64: string;
}): Promise<{
  created: boolean;
  inbound_id: string;
  access_key: string;
  issuer_document: string;
  issuer_name: string;
  status: string;
  source: string;
  items: number;
}> {
  return apiRequest("/v1/admin/fiscal/inbound/xml", {
    method: "POST",
    credentials: "include",
    body: JSON.stringify(payload),
  });
}

export type FiscalManifestationType =
  | "acknowledgement"
  | "confirmation"
  | "unknown_operation"
  | "operation_not_performed";

export async function recordFiscalManifestation(
  accessKey: string,
  payload: {
    environment: FiscalEnvironment;
    event_type: FiscalManifestationType;
    protocol_reference?: string | null;
  },
  idempotencyKey: string,
): Promise<{
  recorded: boolean;
  access_key: string;
  event_type: FiscalManifestationType;
  external_submission: boolean;
}> {
  return apiRequest(
    `/v1/admin/fiscal/inbound/${encodeURIComponent(accessKey)}/manifest`,
    {
      method: "POST",
      credentials: "include",
      headers: idempotencyHeaders(idempotencyKey),
      body: JSON.stringify(payload),
    },
  );
}

export async function uploadPreliminaryFiscalIntake(
  payload: {
    environment: FiscalEnvironment;
    source: "pdf" | "image" | "camera";
    media_type: string;
    content_base64: string;
  },
  idempotencyKey: string,
): Promise<{
  created: boolean;
  capture_id: string;
  status: string;
  source: string;
  authority: string;
  media_type: string;
  confidence: string | null;
  items: number;
  last_error_code: string | null;
}> {
  return apiRequest("/v1/admin/fiscal/intake/preliminary", {
    method: "POST",
    credentials: "include",
    headers: idempotencyHeaders(idempotencyKey),
    body: JSON.stringify(payload),
  });
}

export async function reconcileFiscalIntake(
  captureId: string,
  payload: {
    environment: FiscalEnvironment;
    official_access_key: string;
  },
): Promise<{
  capture_id: string;
  status: string;
  reconciliation: null | {
    status: string;
    official_access_key: string;
    issues: string[];
    reconciled_at: string;
  };
}> {
  return apiRequest(
    `/v1/admin/fiscal/intake/${encodeURIComponent(captureId)}/reconcile`,
    {
      method: "POST",
      credentials: "include",
      body: JSON.stringify(payload),
    },
  );
}

export interface FiscalProcurementWorkspace {
  environment: FiscalEnvironment;
  suppliers: Array<{
    fornecedor_id: string;
    documento: string;
    nome: string;
    ativo: boolean;
    versao: number;
  }>;
  bindings: Array<{
    fornecedor_id: string;
    codigo_fornecedor: string;
    insumo_id: string;
  }>;
  orders: Array<{
    pedido_id: string;
    fornecedor_id: string;
    status: string;
    payload: {
      frete: string;
      desconto: string;
      total: string;
      itens: Array<{
        linha: number;
        insumo_id: string;
        codigo_fornecedor: string;
        descricao: string;
        unidade_medida: string;
        quantidade: string;
        valor_unitario: string;
      }>;
    };
    versao: number;
    updated_at: string;
  }>;
  receipts: Array<{
    recebimento_id: string;
    pedido_id: string;
    inbound_id: string;
    access_key: string;
    status: string;
    payload: {
      itens: Array<{
        linha_pedido: number;
        linha_fiscal: number;
        insumo_id: string;
        quantidade: string;
        unidade_medida: string;
        valor_unitario: string;
        condicao_aceita: boolean;
      }>;
      divergencias: Array<{
        tipo: string;
        linha_pedido: number | null;
        esperado: string;
        encontrado: string;
      }>;
    };
    versao: number;
    confirmed_at: string;
  }>;
  obligations: Array<{
    obrigacao_id: string;
    pedido_id: string;
    recebimento_id: string;
    status: string;
    reconciliation: string;
    original_value: string;
    adjusted_value: string;
    balance: string;
    currency: string;
    version: number;
  }>;
  tax_decisions: Array<{
    decisao_id: string;
    obrigacao_id: string;
    tributo: string;
    resultado: string;
    base_calculo: string;
    valor_destacado: string;
    valor_credito: string;
    cfop: string;
    cst: string;
    regra_id: string | null;
    regra_versao: number | null;
  }>;
}

export function getFiscalProcurement(
  environment: FiscalEnvironment,
): Promise<FiscalProcurementWorkspace> {
  return apiRequest(
    `/v1/admin/fiscal/procurement?environment=${environment}`,
    { credentials: "include" },
  );
}

export function createFiscalSupplier(payload: {
  environment: FiscalEnvironment;
  fornecedor_id: string;
  documento: string;
  nome: string;
}): Promise<{ fornecedor_id: string; documento: string; nome: string; ativo: boolean; versao: number }> {
  return apiRequest("/v1/admin/fiscal/procurement/suppliers", {
    method: "POST",
    credentials: "include",
    body: JSON.stringify(payload),
  });
}

export function createFiscalProductBinding(payload: {
  environment: FiscalEnvironment;
  fornecedor_id: string;
  codigo_fornecedor: string;
  insumo_id: string;
}): Promise<{ fornecedor_id: string; codigo_fornecedor: string; insumo_id: string }> {
  return apiRequest("/v1/admin/fiscal/procurement/bindings", {
    method: "POST",
    credentials: "include",
    body: JSON.stringify(payload),
  });
}

export interface FiscalPurchaseOrderItemInput {
  linha: number;
  insumo_id: string;
  codigo_fornecedor: string;
  descricao: string;
  unidade_medida: string;
  quantidade: string;
  valor_unitario: string;
}

export function createFiscalPurchaseOrder(payload: {
  environment: FiscalEnvironment;
  pedido_id: string;
  fornecedor_id: string;
  itens: FiscalPurchaseOrderItemInput[];
  frete: string;
  desconto: string;
  total: string;
}): Promise<{ pedido_id: string; status: string; versao: number }> {
  return apiRequest("/v1/admin/fiscal/procurement/orders", {
    method: "POST",
    credentials: "include",
    body: JSON.stringify(payload),
  });
}

export function approveFiscalPurchaseOrder(
  pedidoId: string,
  payload: { environment: FiscalEnvironment; expected_version: number },
): Promise<{ pedido_id: string; status: string; versao: number }> {
  return apiRequest(
    `/v1/admin/fiscal/procurement/orders/${encodeURIComponent(pedidoId)}/approve`,
    {
      method: "POST",
      credentials: "include",
      body: JSON.stringify(payload),
    },
  );
}

export interface FiscalReceiptItemInput {
  linha_pedido: number;
  linha_fiscal: number;
  insumo_id: string;
  quantidade: string;
  unidade_medida: string;
  valor_unitario: string;
  condicao_aceita: boolean;
}

export function receiveFiscalPurchase(
  payload: {
    environment: FiscalEnvironment;
    pedido_id: string;
    access_key: string;
    itens: FiscalReceiptItemInput[];
  },
  idempotencyKey: string,
): Promise<{
  recebimento_id: string;
  pedido_id: string;
  status: string;
  divergencias: Array<{
    tipo: string;
    linha_pedido: number | null;
    esperado: string;
    encontrado: string;
  }>;
  stock_movements: number;
  idempotent: boolean;
}> {
  return apiRequest("/v1/admin/fiscal/procurement/receipts", {
    method: "POST",
    credentials: "include",
    headers: idempotencyHeaders(idempotencyKey),
    body: JSON.stringify(payload),
  });
}

export function returnFiscalPurchase(
  recebimentoId: string,
  payload: { environment: FiscalEnvironment; motivo: string },
  idempotencyKey: string,
): Promise<{ recebimento_id: string; stock_movements: number }> {
  return apiRequest(
    `/v1/admin/fiscal/procurement/receipts/${encodeURIComponent(recebimentoId)}/return`,
    {
      method: "POST",
      credentials: "include",
      headers: idempotencyHeaders(idempotencyKey),
      body: JSON.stringify(payload),
    },
  );
}

export function createFiscalFinancialObligation(
  recebimentoId: string,
  idempotencyKey: string,
): Promise<{
  obrigacao_id: string;
  recebimento_id: string;
  status: string;
  reconciliation: string;
  original_value: string;
  balance: string;
  idempotent: boolean;
}> {
  return apiRequest("/v1/admin/fiscal/financial/obligations", {
    method: "POST",
    credentials: "include",
    headers: idempotencyHeaders(idempotencyKey),
    body: JSON.stringify({ recebimento_id: recebimentoId }),
  });
}

export function adjustFiscalFinancialObligation(
  payload: {
    recebimento_id: string;
    tipo: "devolucao" | "cancelamento";
    origem_id: string;
    motivo: string;
    valor?: string | null;
  },
  idempotencyKey: string,
): Promise<{
  obrigacao_id: string;
  status: string;
  adjusted_value: string;
  balance: string;
  version: number;
}> {
  return apiRequest("/v1/admin/fiscal/financial/adjustments", {
    method: "POST",
    credentials: "include",
    headers: idempotencyHeaders(idempotencyKey),
    body: JSON.stringify(payload),
  });
}

export function decideFiscalTaxCredit(
  payload: {
    recebimento_id: string;
    tributo: string;
    base_calculo: string;
    valor_destacado: string;
    cfop: string;
    cst: string;
    regra_id?: string | null;
    regra_versao?: number | null;
    aliquota_credito?: string | null;
    cfops_elegiveis?: string[];
    csts_elegiveis?: string[];
    vigente_desde?: string | null;
    vigente_ate?: string | null;
  },
  idempotencyKey: string,
): Promise<{
  decisao_id: string;
  obrigacao_id: string;
  resultado: string;
  valor_credito: string;
  regra_id: string | null;
  regra_versao: number | null;
  motivo: string;
}> {
  return apiRequest("/v1/admin/fiscal/financial/tax-credit-decisions", {
    method: "POST",
    credentials: "include",
    headers: idempotencyHeaders(idempotencyKey),
    body: JSON.stringify(payload),
  });
}

export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}
