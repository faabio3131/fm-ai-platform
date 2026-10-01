"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  adjustFiscalFinancialObligation,
  approveFiscalPurchaseOrder,
  createFiscalFinancialObligation,
  createFiscalProductBinding,
  createFiscalPurchaseOrder,
  createFiscalSupplier,
  decideFiscalTaxCredit,
  fileToBase64,
  getFiscalProcurement,
  queryFiscalDocument,
  receiveFiscalPurchase,
  reconcileFiscalIntake,
  recordFiscalManifestation,
  returnFiscalPurchase,
  uploadOfficialFiscalXml,
  uploadPreliminaryFiscalIntake,
  type FiscalEnvironment,
  type FiscalManifestationType,
  type FiscalProcurementWorkspace,
  type FiscalPurchaseOrderItemInput,
  type FiscalReceiptItemInput,
  type FiscalWorkspaceResponse,
} from "@/features/backoffice/fiscal/services/fiscal-api";

interface Props {
  environment: FiscalEnvironment;
  capabilities: FiscalWorkspaceResponse["capabilities"];
  onChanged: () => Promise<void>;
}

const emptyOrderItem = (): FiscalPurchaseOrderItemInput => ({
  linha: 1,
  insumo_id: "",
  codigo_fornecedor: "",
  descricao: "",
  unidade_medida: "UN",
  quantidade: "1",
  valor_unitario: "0",
});

const emptyReceiptItem = (): FiscalReceiptItemInput => ({
  linha_pedido: 1,
  linha_fiscal: 1,
  insumo_id: "",
  quantidade: "1",
  unidade_medida: "UN",
  valor_unitario: "0",
  condicao_aceita: true,
});

function randomKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function moneyTotal(
  items: FiscalPurchaseOrderItemInput[],
  freight: string,
  discount: string,
): string {
  const products = items.reduce(
    (sum, item) =>
      sum +
      (Number.parseFloat(item.quantidade || "0") || 0) *
        (Number.parseFloat(item.valor_unitario || "0") || 0),
    0,
  );
  return Math.max(
    0,
    products +
      (Number.parseFloat(freight || "0") || 0) -
      (Number.parseFloat(discount || "0") || 0),
  ).toFixed(2);
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function FieldLabel({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="space-y-1.5 text-xs font-semibold text-slate-400">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function FiscalOperationsPanel({
  environment,
  capabilities,
  onChanged,
}: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [procurement, setProcurement] =
    useState<FiscalProcurementWorkspace | null>(null);

  const [xmlFile, setXmlFile] = useState<File | null>(null);
  const [intakeFile, setIntakeFile] = useState<File | null>(null);
  const [intakeSource, setIntakeSource] =
    useState<"pdf" | "image" | "camera">("pdf");
  const [manifestKey, setManifestKey] = useState("");
  const [manifestType, setManifestType] =
    useState<FiscalManifestationType>("acknowledgement");
  const [manifestProtocol, setManifestProtocol] = useState("");
  const [reconcileCapture, setReconcileCapture] = useState("");
  const [reconcileKey, setReconcileKey] = useState("");
  const [providerQueryKey, setProviderQueryKey] = useState("");

  const [supplierId, setSupplierId] = useState("");
  const [supplierDocument, setSupplierDocument] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [bindingSupplier, setBindingSupplier] = useState("");
  const [bindingCode, setBindingCode] = useState("");
  const [bindingInput, setBindingInput] = useState("");

  const [orderId, setOrderId] = useState("");
  const [orderSupplier, setOrderSupplier] = useState("");
  const [orderFreight, setOrderFreight] = useState("0");
  const [orderDiscount, setOrderDiscount] = useState("0");
  const [orderItems, setOrderItems] = useState<FiscalPurchaseOrderItemInput[]>([
    emptyOrderItem(),
  ]);

  const [receiptOrder, setReceiptOrder] = useState("");
  const [receiptAccessKey, setReceiptAccessKey] = useState("");
  const [receiptItems, setReceiptItems] = useState<FiscalReceiptItemInput[]>([
    emptyReceiptItem(),
  ]);
  const [returnReceiptId, setReturnReceiptId] = useState("");
  const [returnReason, setReturnReason] = useState("");

  const [obligationReceipt, setObligationReceipt] = useState("");
  const [adjustReceipt, setAdjustReceipt] = useState("");
  const [adjustType, setAdjustType] =
    useState<"devolucao" | "cancelamento">("devolucao");
  const [adjustOrigin, setAdjustOrigin] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [adjustValue, setAdjustValue] = useState("");

  const [taxReceipt, setTaxReceipt] = useState("");
  const [taxName, setTaxName] = useState("ICMS");
  const [taxBase, setTaxBase] = useState("");
  const [taxHighlighted, setTaxHighlighted] = useState("");
  const [taxCfop, setTaxCfop] = useState("");
  const [taxCst, setTaxCst] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [ruleVersion, setRuleVersion] = useState("");
  const [ruleRate, setRuleRate] = useState("");
  const [ruleCfops, setRuleCfops] = useState("");
  const [ruleCsts, setRuleCsts] = useState("");
  const [ruleStart, setRuleStart] = useState("");
  const [ruleEnd, setRuleEnd] = useState("");

  const orderTotal = useMemo(
    () => moneyTotal(orderItems, orderFreight, orderDiscount),
    [orderItems, orderFreight, orderDiscount],
  );

  const loadProcurement = useCallback(async () => {
    if (!capabilities.purchases_view) {
      setProcurement(null);
      return;
    }
    try {
      setProcurement(await getFiscalProcurement(environment));
    } catch {
      setProcurement(null);
    }
  }, [capabilities.purchases_view, environment]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadProcurement(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProcurement]);

  async function execute(
    key: string,
    success: string,
    action: () => Promise<unknown>,
  ): Promise<void> {
    setBusy(key);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await Promise.all([onChanged(), loadProcurement()]);
    } catch (error) {
      setMessage(messageOf(error, "A operação não pôde ser concluída."));
    } finally {
      setBusy(null);
    }
  }

  async function submitXml(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!xmlFile) return;
    await execute("xml", "XML oficial registrado no Fiscal Inbox.", async () => {
      await uploadOfficialFiscalXml({
        environment,
        content_base64: await fileToBase64(xmlFile),
      });
      setXmlFile(null);
    });
  }

  async function submitIntake(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!intakeFile) return;
    await execute(
      "intake",
      "Smart Intake concluído. A evidência permanece preliminar até reconciliação.",
      async () => {
        await uploadPreliminaryFiscalIntake(
          {
            environment,
            source: intakeSource,
            media_type: intakeFile.type,
            content_base64: await fileToBase64(intakeFile),
          },
          randomKey("fiscal-intake"),
        );
        setIntakeFile(null);
      },
    );
  }

  return (
    <section className="space-y-5 rounded-2xl border border-sky-300/10 bg-slate-900/72 p-5 shadow-[0_24px_70px_-48px_rgba(14,165,233,0.5)]">
      <div>
        <p className="text-xs font-black uppercase tracking-[0.18em] text-sky-300">
          Operação fiscal completa
        </p>
        <h2 className="mt-2 text-xl font-black text-white">
          Entrada fiscal, compras e financeiro
        </h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
          Estas ações usam as autoridades fiscais e de Procurement já existentes.
          Tenant e unidade vêm exclusivamente da sessão autenticada. Evidência de
          IA continua preliminar e não substitui XML/DF-e oficial.
        </p>
      </div>

      {message ? (
        <div role="status" className="rounded-xl border border-sky-300/15 bg-sky-400/[0.06] p-3 text-sm text-sky-100">
          {message}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/45 p-4">
          <h3 className="font-bold text-white">Fiscal Inbox e Smart Intake</h3>

          <form className="space-y-3" onSubmit={(event) => void submitXml(event)}>
            <p className="text-sm font-semibold text-slate-200">Importar XML oficial</p>
            <input
              aria-label="Arquivo XML fiscal oficial"
              type="file"
              accept=".xml,application/xml,text/xml"
              onChange={(event) => setXmlFile(event.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200"
              disabled={!capabilities.purchases_receive}
            />
            <Button
              type="submit"
              disabled={!xmlFile || !capabilities.purchases_receive || busy !== null}
            >
              {busy === "xml" ? "Importando…" : "Registrar XML no Inbox"}
            </Button>
          </form>

          <form className="space-y-3 border-t border-slate-800 pt-4" onSubmit={(event) => void submitIntake(event)}>
            <p className="text-sm font-semibold text-slate-200">Captura por IA</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <select
                aria-label="Origem do Smart Intake"
                value={intakeSource}
                onChange={(event) =>
                  setIntakeSource(event.target.value as "pdf" | "image" | "camera")
                }
                className="h-10 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm"
              >
                <option value="pdf">PDF</option>
                <option value="image">Imagem</option>
                <option value="camera">Câmera</option>
              </select>
              <input
                aria-label="Arquivo para Smart Intake"
                type="file"
                accept={intakeSource === "pdf" ? "application/pdf" : "image/jpeg,image/png"}
                capture={intakeSource === "camera" ? "environment" : undefined}
                onChange={(event) => setIntakeFile(event.target.files?.[0] ?? null)}
                className="block w-full text-xs text-slate-400 file:mr-2 file:rounded-lg file:border-0 file:bg-slate-800 file:px-2 file:py-2"
                disabled={!capabilities.purchases_receive}
              />
            </div>
            <Button
              type="submit"
              disabled={!intakeFile || !capabilities.purchases_receive || busy !== null}
            >
              {busy === "intake" ? "Analisando…" : "Analisar evidência com IA"}
            </Button>
            <p className="text-xs text-slate-500">
              PDF/imagem/câmera geram evidência preliminar. A reconciliação com
              documento oficial é obrigatória antes de qualquer autoridade fiscal.
            </p>
          </form>

          <div className="grid gap-3 border-t border-slate-800 pt-4 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-200">Reconciliar captura</p>
              <Input
                placeholder="Capture ID"
                value={reconcileCapture}
                onChange={(event) => setReconcileCapture(event.target.value)}
              />
              <Input
                placeholder="Chave oficial NF-e"
                value={reconcileKey}
                onChange={(event) => setReconcileKey(event.target.value)}
              />
              <Button
                type="button"
                variant="outline"
                disabled={
                  busy !== null ||
                  !capabilities.purchases_receive ||
                  !reconcileCapture.trim() ||
                  reconcileKey.length !== 44
                }
                onClick={() =>
                  void execute(
                    "reconcile",
                    "Captura reconciliada com a autoridade oficial.",
                    () =>
                      reconcileFiscalIntake(reconcileCapture, {
                        environment,
                        official_access_key: reconcileKey,
                      }),
                  )
                }
              >
                Reconciliar
              </Button>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-200">Consultar provider</p>
              <Input
                placeholder="Chave de acesso"
                value={providerQueryKey}
                onChange={(event) => setProviderQueryKey(event.target.value)}
              />
              <Button
                type="button"
                variant="outline"
                disabled={busy !== null || !capabilities.query || providerQueryKey.length !== 44}
                onClick={() =>
                  void execute(
                    "provider-query",
                    "Consulta ao provider concluída.",
                    () => queryFiscalDocument(providerQueryKey, environment),
                  )
                }
              >
                Consultar situação
              </Button>
            </div>
          </div>

          <div className="space-y-2 border-t border-slate-800 pt-4">
            <p className="text-sm font-semibold text-slate-200">Registrar manifestação</p>
            <Input
              placeholder="Chave de acesso"
              value={manifestKey}
              onChange={(event) => setManifestKey(event.target.value)}
            />
            <select
              aria-label="Tipo de manifestação"
              value={manifestType}
              onChange={(event) => setManifestType(event.target.value as FiscalManifestationType)}
              className="h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm"
            >
              <option value="acknowledgement">Ciência da operação</option>
              <option value="confirmation">Confirmação da operação</option>
              <option value="unknown_operation">Operação desconhecida</option>
              <option value="operation_not_performed">Operação não realizada</option>
            </select>
            <Input
              placeholder="Protocolo externo, se já existente"
              value={manifestProtocol}
              onChange={(event) => setManifestProtocol(event.target.value)}
            />
            <Button
              type="button"
              variant="outline"
              disabled={busy !== null || !capabilities.manifest || manifestKey.length !== 44}
              onClick={() =>
                void execute(
                  "manifest",
                  "Manifestação registrada. Nenhum envio externo foi presumido.",
                  () =>
                    recordFiscalManifestation(
                      manifestKey,
                      {
                        environment,
                        event_type: manifestType,
                        protocol_reference: manifestProtocol.trim() || null,
                      },
                      randomKey("fiscal-manifest"),
                    ),
                )
              }
            >
              Registrar manifestação
            </Button>
            <p className="text-xs text-amber-200/75">
              Esta ação registra a manifestação canônica no Kordena; não afirma
              transmissão à SEFAZ sem gateway/evidência externa.
            </p>
          </div>
        </article>

        <article className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/45 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-bold text-white">Fornecedores e vínculos</h3>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!capabilities.purchases_view || busy !== null}
              onClick={() => void loadProcurement()}
            >
              Atualizar
            </Button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-semibold">Cadastrar fornecedor</p>
              <Input placeholder="ID do fornecedor" value={supplierId} onChange={(event) => setSupplierId(event.target.value)} />
              <Input placeholder="CNPJ/CPF" value={supplierDocument} onChange={(event) => setSupplierDocument(event.target.value)} />
              <Input placeholder="Nome" value={supplierName} onChange={(event) => setSupplierName(event.target.value)} />
              <Button
                type="button"
                disabled={
                  busy !== null ||
                  !capabilities.purchase_approve ||
                  !supplierId.trim() ||
                  !supplierDocument.trim() ||
                  !supplierName.trim()
                }
                onClick={() =>
                  void execute("supplier", "Fornecedor cadastrado.", () =>
                    createFiscalSupplier({
                      environment,
                      fornecedor_id: supplierId,
                      documento: supplierDocument,
                      nome: supplierName,
                    }),
                  )
                }
              >
                Salvar fornecedor
              </Button>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-semibold">Vincular código ao insumo</p>
              <Input placeholder="ID do fornecedor" value={bindingSupplier} onChange={(event) => setBindingSupplier(event.target.value)} />
              <Input placeholder="Código do fornecedor" value={bindingCode} onChange={(event) => setBindingCode(event.target.value)} />
              <Input placeholder="ID do insumo Kordena" value={bindingInput} onChange={(event) => setBindingInput(event.target.value)} />
              <Button
                type="button"
                disabled={
                  busy !== null ||
                  !capabilities.purchase_approve ||
                  !bindingSupplier.trim() ||
                  !bindingCode.trim() ||
                  !bindingInput.trim()
                }
                onClick={() =>
                  void execute("binding", "Produto do fornecedor vinculado ao insumo.", () =>
                    createFiscalProductBinding({
                      environment,
                      fornecedor_id: bindingSupplier,
                      codigo_fornecedor: bindingCode,
                      insumo_id: bindingInput,
                    }),
                  )
                }
              >
                Criar vínculo
              </Button>
            </div>
          </div>

          {procurement ? (
            <div className="grid gap-2 border-t border-slate-800 pt-4 text-xs text-slate-400 sm:grid-cols-2">
              <div>
                <span className="font-semibold text-slate-200">Fornecedores:</span>{" "}
                {procurement.suppliers.length}
              </div>
              <div>
                <span className="font-semibold text-slate-200">Vínculos:</span>{" "}
                {procurement.bindings.length}
              </div>
            </div>
          ) : null}
        </article>
      </div>

      <article className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/45 p-4">
        <h3 className="font-bold text-white">Pedido de compra</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldLabel label="ID do pedido">
            <Input value={orderId} onChange={(event) => setOrderId(event.target.value)} />
          </FieldLabel>
          <FieldLabel label="Fornecedor">
            <Input value={orderSupplier} onChange={(event) => setOrderSupplier(event.target.value)} />
          </FieldLabel>
        </div>

        <div className="space-y-3">
          {orderItems.map((item, index) => (
            <div key={index} className="grid gap-2 rounded-xl border border-slate-800 p-3 md:grid-cols-7">
              <Input aria-label={`Insumo linha ${index + 1}`} placeholder="Insumo" value={item.insumo_id} onChange={(event) => setOrderItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, insumo_id: event.target.value } : row))} />
              <Input placeholder="Cód. fornecedor" value={item.codigo_fornecedor} onChange={(event) => setOrderItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, codigo_fornecedor: event.target.value } : row))} />
              <Input placeholder="Descrição" value={item.descricao} onChange={(event) => setOrderItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, descricao: event.target.value } : row))} />
              <Input placeholder="Un." value={item.unidade_medida} onChange={(event) => setOrderItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, unidade_medida: event.target.value } : row))} />
              <Input inputMode="decimal" placeholder="Qtd." value={item.quantidade} onChange={(event) => setOrderItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, quantidade: event.target.value } : row))} />
              <Input inputMode="decimal" placeholder="Valor unit." value={item.valor_unitario} onChange={(event) => setOrderItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, valor_unitario: event.target.value } : row))} />
              <Button type="button" variant="ghost" disabled={orderItems.length === 1} onClick={() => setOrderItems((current) => current.filter((_, rowIndex) => rowIndex !== index).map((row, rowIndex) => ({ ...row, linha: rowIndex + 1 })))}>Remover</Button>
            </div>
          ))}
          <Button type="button" variant="outline" onClick={() => setOrderItems((current) => [...current, { ...emptyOrderItem(), linha: current.length + 1 }])}>
            Adicionar item
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <FieldLabel label="Frete">
            <Input inputMode="decimal" value={orderFreight} onChange={(event) => setOrderFreight(event.target.value)} />
          </FieldLabel>
          <FieldLabel label="Desconto">
            <Input inputMode="decimal" value={orderDiscount} onChange={(event) => setOrderDiscount(event.target.value)} />
          </FieldLabel>
          <div className="rounded-xl border border-slate-800 p-3">
            <p className="text-xs text-slate-500">Total calculado</p>
            <p className="mt-1 font-bold text-white">R$ {orderTotal}</p>
          </div>
          <Button
            type="button"
            className="self-end"
            disabled={
              busy !== null ||
              !capabilities.purchase_approve ||
              !orderId.trim() ||
              !orderSupplier.trim() ||
              orderItems.some((item) => !item.insumo_id || !item.codigo_fornecedor || !item.descricao)
            }
            onClick={() =>
              void execute("order", "Pedido de compra criado em rascunho.", () =>
                createFiscalPurchaseOrder({
                  environment,
                  pedido_id: orderId,
                  fornecedor_id: orderSupplier,
                  itens: orderItems,
                  frete: orderFreight,
                  desconto: orderDiscount,
                  total: orderTotal,
                }),
              )
            }
          >
            Criar pedido
          </Button>
        </div>

        {procurement?.orders.length ? (
          <div className="grid gap-2 border-t border-slate-800 pt-4 md:grid-cols-2">
            {procurement.orders.map((order) => (
              <div key={order.pedido_id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 p-3 text-sm">
                <div>
                  <p className="font-semibold text-white">{order.pedido_id}</p>
                  <p className="text-xs text-slate-500">{order.status} · v{order.versao} · R$ {order.payload.total}</p>
                </div>
                {order.status === "rascunho" && capabilities.purchase_approve ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() =>
                      void execute("approve", "Pedido de compra aprovado.", () =>
                        approveFiscalPurchaseOrder(order.pedido_id, {
                          environment,
                          expected_version: order.versao,
                        }),
                      )
                    }
                  >
                    Aprovar
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </article>

      <article className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/45 p-4">
        <h3 className="font-bold text-white">Recebimento físico</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldLabel label="Pedido aprovado">
            <Input value={receiptOrder} onChange={(event) => setReceiptOrder(event.target.value)} />
          </FieldLabel>
          <FieldLabel label="Chave da NF-e oficial">
            <Input value={receiptAccessKey} onChange={(event) => setReceiptAccessKey(event.target.value)} />
          </FieldLabel>
        </div>

        <div className="space-y-3">
          {receiptItems.map((item, index) => (
            <div key={index} className="grid gap-2 rounded-xl border border-slate-800 p-3 md:grid-cols-7">
              <Input inputMode="numeric" placeholder="Linha pedido" value={String(item.linha_pedido)} onChange={(event) => setReceiptItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, linha_pedido: Number(event.target.value) } : row))} />
              <Input inputMode="numeric" placeholder="Linha NF" value={String(item.linha_fiscal)} onChange={(event) => setReceiptItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, linha_fiscal: Number(event.target.value) } : row))} />
              <Input placeholder="Insumo" value={item.insumo_id} onChange={(event) => setReceiptItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, insumo_id: event.target.value } : row))} />
              <Input inputMode="decimal" placeholder="Qtd." value={item.quantidade} onChange={(event) => setReceiptItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, quantidade: event.target.value } : row))} />
              <Input placeholder="Un." value={item.unidade_medida} onChange={(event) => setReceiptItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, unidade_medida: event.target.value } : row))} />
              <Input inputMode="decimal" placeholder="Valor unit." value={item.valor_unitario} onChange={(event) => setReceiptItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, valor_unitario: event.target.value } : row))} />
              <Button type="button" variant="ghost" disabled={receiptItems.length === 1} onClick={() => setReceiptItems((current) => current.filter((_, rowIndex) => rowIndex !== index))}>Remover</Button>
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setReceiptItems((current) => [...current, emptyReceiptItem()])}>
              Adicionar item
            </Button>
            <Button
              type="button"
              disabled={
                busy !== null ||
                !capabilities.purchases_receive ||
                !receiptOrder.trim() ||
                receiptAccessKey.length !== 44 ||
                receiptItems.some((item) => !item.insumo_id)
              }
              onClick={() =>
                void execute("receipt", "Recebimento fiscal processado.", () =>
                  receiveFiscalPurchase(
                    {
                      environment,
                      pedido_id: receiptOrder,
                      access_key: receiptAccessKey,
                      itens: receiptItems,
                    },
                    randomKey("fiscal-receipt"),
                  ),
                )
              }
            >
              Confirmar recebimento
            </Button>
          </div>
        </div>

        <div className="grid gap-3 border-t border-slate-800 pt-4 sm:grid-cols-[1fr_2fr_auto]">
          <Input placeholder="ID do recebimento para devolução" value={returnReceiptId} onChange={(event) => setReturnReceiptId(event.target.value)} />
          <Input placeholder="Motivo da devolução" value={returnReason} onChange={(event) => setReturnReason(event.target.value)} />
          <Button
            type="button"
            variant="outline"
            disabled={busy !== null || !capabilities.purchases_receive || !returnReceiptId.trim() || returnReason.trim().length < 3}
            onClick={() =>
              void execute("return", "Devolução ao fornecedor registrada.", () =>
                returnFiscalPurchase(
                  returnReceiptId,
                  { environment, motivo: returnReason },
                  randomKey("fiscal-return"),
                ),
              )
            }
          >
            Devolver
          </Button>
        </div>
      </article>

      <article className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/45 p-4">
        <h3 className="font-bold text-white">Financeiro e crédito tributário</h3>
        {environment !== "production" ? (
          <p className="rounded-xl border border-amber-400/15 bg-amber-400/[0.06] p-3 text-xs text-amber-100">
            Obrigações financeiras e decisões tributárias produzem efeito somente
            na partição de Produção. Homologação continua sem efeito financeiro real.
          </p>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="space-y-2">
            <p className="text-sm font-semibold">Criar obrigação da compra</p>
            <Input placeholder="ID do recebimento" value={obligationReceipt} onChange={(event) => setObligationReceipt(event.target.value)} />
            <Button
              type="button"
              disabled={busy !== null || environment !== "production" || !capabilities.financial_register || !obligationReceipt.trim()}
              onClick={() =>
                void execute("obligation", "Obrigação financeira criada sem executar pagamento.", () =>
                  createFiscalFinancialObligation(
                    obligationReceipt,
                    randomKey("fiscal-obligation"),
                  ),
                )
              }
            >
              Criar obrigação
            </Button>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Ajustar obrigação</p>
            <Input placeholder="ID do recebimento" value={adjustReceipt} onChange={(event) => setAdjustReceipt(event.target.value)} />
            <select value={adjustType} onChange={(event) => setAdjustType(event.target.value as "devolucao" | "cancelamento")} className="h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm">
              <option value="devolucao">Devolução</option>
              <option value="cancelamento">Cancelamento</option>
            </select>
            <Input placeholder="ID da origem" value={adjustOrigin} onChange={(event) => setAdjustOrigin(event.target.value)} />
            <Input placeholder="Motivo" value={adjustReason} onChange={(event) => setAdjustReason(event.target.value)} />
            <Input inputMode="decimal" placeholder="Valor (vazio = saldo total)" value={adjustValue} onChange={(event) => setAdjustValue(event.target.value)} />
            <Button
              type="button"
              variant="outline"
              disabled={busy !== null || environment !== "production" || !capabilities.financial_register || !adjustReceipt || !adjustOrigin || adjustReason.length < 3}
              onClick={() =>
                void execute("adjustment", "Obrigação financeira ajustada preservando histórico.", () =>
                  adjustFiscalFinancialObligation(
                    {
                      recebimento_id: adjustReceipt,
                      tipo: adjustType,
                      origem_id: adjustOrigin,
                      motivo: adjustReason,
                      valor: adjustValue.trim() || null,
                    },
                    randomKey("fiscal-adjust"),
                  ),
                )
              }
            >
              Registrar ajuste
            </Button>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Decisão de crédito tributário</p>
            <Input placeholder="ID do recebimento" value={taxReceipt} onChange={(event) => setTaxReceipt(event.target.value)} />
            <div className="grid grid-cols-2 gap-2">
              <Input placeholder="Tributo" value={taxName} onChange={(event) => setTaxName(event.target.value)} />
              <Input placeholder="CFOP" value={taxCfop} onChange={(event) => setTaxCfop(event.target.value)} />
              <Input placeholder="CST" value={taxCst} onChange={(event) => setTaxCst(event.target.value)} />
              <Input inputMode="decimal" placeholder="Base cálculo" value={taxBase} onChange={(event) => setTaxBase(event.target.value)} />
              <Input inputMode="decimal" placeholder="Valor destacado" value={taxHighlighted} onChange={(event) => setTaxHighlighted(event.target.value)} />
            </div>
            <details className="rounded-xl border border-slate-800 p-3">
              <summary className="cursor-pointer text-xs font-semibold text-slate-300">
                Regra explícita versionada (opcional)
              </summary>
              <div className="mt-3 grid gap-2">
                <Input placeholder="Regra ID" value={ruleId} onChange={(event) => setRuleId(event.target.value)} />
                <Input inputMode="numeric" placeholder="Versão" value={ruleVersion} onChange={(event) => setRuleVersion(event.target.value)} />
                <Input inputMode="decimal" placeholder="Alíquota 0..1" value={ruleRate} onChange={(event) => setRuleRate(event.target.value)} />
                <Input placeholder="CFOPs elegíveis separados por vírgula" value={ruleCfops} onChange={(event) => setRuleCfops(event.target.value)} />
                <Input placeholder="CSTs elegíveis separados por vírgula" value={ruleCsts} onChange={(event) => setRuleCsts(event.target.value)} />
                <Input type="date" value={ruleStart} onChange={(event) => setRuleStart(event.target.value)} />
                <Input type="date" value={ruleEnd} onChange={(event) => setRuleEnd(event.target.value)} />
              </div>
            </details>
            <Button
              type="button"
              variant="outline"
              disabled={
                busy !== null ||
                environment !== "production" ||
                !capabilities.tax_decide ||
                !taxReceipt ||
                !taxName ||
                !taxBase ||
                !taxHighlighted ||
                !taxCfop ||
                !taxCst
              }
              onClick={() =>
                void execute("tax", "Decisão tributária registrada de forma versionada.", () =>
                  decideFiscalTaxCredit(
                    {
                      recebimento_id: taxReceipt,
                      tributo: taxName,
                      base_calculo: taxBase,
                      valor_destacado: taxHighlighted,
                      cfop: taxCfop,
                      cst: taxCst,
                      regra_id: ruleId.trim() || null,
                      regra_versao: ruleVersion ? Number(ruleVersion) : null,
                      aliquota_credito: ruleRate.trim() || null,
                      cfops_elegiveis: ruleCfops.split(",").map((item) => item.trim()).filter(Boolean),
                      csts_elegiveis: ruleCsts.split(",").map((item) => item.trim()).filter(Boolean),
                      vigente_desde: ruleStart || null,
                      vigente_ate: ruleEnd || null,
                    },
                    randomKey("fiscal-tax"),
                  ),
                )
              }
            >
              Registrar decisão
            </Button>
          </div>
        </div>

        {procurement ? (
          <div className="grid gap-3 border-t border-slate-800 pt-4 md:grid-cols-3">
            <div className="rounded-xl border border-slate-800 p-3 text-sm">
              <span className="text-slate-500">Pedidos</span>
              <p className="mt-1 text-xl font-bold text-white">{procurement.orders.length}</p>
            </div>
            <div className="rounded-xl border border-slate-800 p-3 text-sm">
              <span className="text-slate-500">Recebimentos</span>
              <p className="mt-1 text-xl font-bold text-white">{procurement.receipts.length}</p>
            </div>
            <div className="rounded-xl border border-slate-800 p-3 text-sm">
              <span className="text-slate-500">Obrigações</span>
              <p className="mt-1 text-xl font-bold text-white">{procurement.obligations.length}</p>
            </div>
          </div>
        ) : null}
      </article>
    </section>
  );
}
