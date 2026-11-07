"use client";

import {
  Banknote,
  CheckCircle2,
  CreditCard,
  Delete,
  Loader2,
  QrCode,
} from "lucide-react";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  PdvApiError,
  submitCheckout,
  iniciarPixPagBank,
  confirmarCartaoNoTerminal,
  criarCheckoutCartaoPagBank,
  verificarCheckoutCartaoPagBank,
  type CheckoutCartaoPagBank,
  verificarPixPagBank,
  type PixPagBankCobranca,
  type CheckoutPayload,
  type CheckoutResponse,
  type PaymentMethod,
} from "@/features/pdv/services/pdv-api";
import {
  cartActions,
  formatCurrency,
  useCartStore,
  useCartTotals,
} from "@/features/pdv/store/cart-store";
import { cn } from "@/lib/utils";

interface CheckoutModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const paymentOptions: Array<{
  value: PaymentMethod;
  label: string;
  description: string;
  icon: typeof Banknote;
}> = [
  { value: "dinheiro", label: "Dinheiro", description: "Troco em tela", icon: Banknote },
  { value: "pix", label: "PIX", description: "Pagamento instantâneo", icon: QrCode },
  { value: "cartao_debito", label: "Débito", description: "Cartão de débito", icon: CreditCard },
  { value: "cartao_credito", label: "Crédito", description: "Cartão de crédito", icon: CreditCard },
];

const keypadKeys = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "C", "0", "00", "backspace"] as const;

export function CheckoutModal({ open, onOpenChange }: CheckoutModalProps) {
  const cart = useCartStore();
  const totals = useCartTotals();
  const [receivedCents, setReceivedCents] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckoutResponse | null>(null);
  const [pixPagador, setPixPagador] = useState({ nome: "", email: "", documento: "" });
  const [pixCobranca, setPixCobranca] = useState<PixPagBankCobranca | null>(null);
  const [pixVerificado, setPixVerificado] = useState<string | null>(null);
  const [pixBusy, setPixBusy] = useState(false);
  const [cartaoReferencia, setCartaoReferencia] = useState("");
  const [cartaoAprovadoNoTerminal, setCartaoAprovadoNoTerminal] = useState(false);
  const [cartaoConfirmado, setCartaoConfirmado] = useState(false);
  const [cartaoBusy, setCartaoBusy] = useState(false);
  const [cartaoErro, setCartaoErro] = useState<string | null>(null);
  const [cartaoCheckout, setCartaoCheckout] = useState<CheckoutCartaoPagBank | null>(null);
  const [cartaoCheckoutBusy, setCartaoCheckoutBusy] = useState(false);
  const [cartaoCheckoutErro, setCartaoCheckoutErro] = useState<string | null>(null);


  const tentativa = useRef<{ payload: string; chave: string } | null>(null);

  const changeCents = Math.max(0, receivedCents - totals.totalCents);
  const cashIsEnough = cart.metodoPagamento !== "dinheiro" || receivedCents >= totals.totalCents;
  const pagamentoLiquidado = cartaoConfirmado || cartaoCheckout?.status_pagamento === "pago" || pixVerificado === "pago" || result?.pagamento?.status === "pago" || (
    result !== null && result.pagamento === null && Number(result.comanda.total) === 0
  );

  function selectPaymentMethod(method: PaymentMethod) {
    cartActions.setPaymentMethod(method);
    setError(null);
    if (method !== "dinheiro") {
      setReceivedCents(0);
    }
  }

  function pressKey(key: (typeof keypadKeys)[number]) {
    setError(null);
    if (key === "C") {
      setReceivedCents(0);
      return;
    }
    if (key === "backspace") {
      setReceivedCents((current) => Math.floor(current / 10));
      return;
    }
    if (key === "00") {
      setReceivedCents((current) => Math.min(current * 100, 99_999_999));
      return;
    }
    const digit = Number.parseInt(key, 10);
    setReceivedCents((current) => Math.min(current * 10 + digit, 99_999_999));
  }

  async function finalizeCheckout() {
    if (cart.itens.length === 0 || !cashIsEnough) return;

    setSubmitting(true);
    setError(null);

    try {
      const payload: CheckoutPayload = {
        itens: cart.itens.map((item) => ({
          produto_id: item.produto_id,
          quantidade: item.quantidade,
          observacoes: item.observacoes.trim() || null,
        })),
        metodo_pagamento: cart.metodoPagamento,
        ...(cart.metodoPagamento === "dinheiro"
          ? { valor_recebido: (receivedCents / 100).toFixed(2) }
          : {}),
        desconto: (totals.discountCents / 100).toFixed(2),
        cliente_id: cart.clienteId.trim() || null,
      };
      const serializado = JSON.stringify(payload);
      if (tentativa.current?.payload !== serializado) {
        tentativa.current = { payload: serializado, chave: crypto.randomUUID() };
      }
      const response = await submitCheckout(payload, tentativa.current.chave);
      tentativa.current = null;
      setResult(response);
      setPixCobranca(null);
      setPixVerificado(null);
      setCartaoConfirmado(false);
      setCartaoReferencia("");
      setCartaoAprovadoNoTerminal(false);
      setCartaoErro(null);
      setCartaoCheckout(null);
      setCartaoCheckoutErro(null);
      cartActions.reset();
    } catch (caught) {
      if (caught instanceof PdvApiError) {
        setError(caught.code ? `${caught.message} · ${caught.code}` : caught.message);
      } else {
        setError(caught instanceof Error ? caught.message : "Falha inesperada no checkout.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function gerarPix() {
    if (!result?.pagamento || result.pagamento.metodo !== "pix") return;
    if (pixPagador.nome.trim().length < 2 || !pixPagador.email.includes("@") ||
      ![11, 14].includes(pixPagador.documento.replace(/\D/g, "").length)) {
      setError("Informe nome, e-mail e CPF/CNPJ válidos para gerar o Pix.");
      return;
    }
    setPixBusy(true);
    setError(null);
    try {
      setPixCobranca(await iniciarPixPagBank(result.pagamento.id, pixPagador));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha ao criar Pix no provedor.");
    } finally {
      setPixBusy(false);
    }
  }

  async function verificarPix() {
    if (!result?.pagamento || result.pagamento.metodo !== "pix") return;
    setPixBusy(true);
    setError(null);
    try {
      const verificado = await verificarPixPagBank(result.pagamento.id);
      setPixVerificado(verificado.status_pagamento);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha ao consultar o pagamento.");
    } finally {
      setPixBusy(false);
    }
  }

  async function abrirCheckoutCartao() {
    if (!result?.pagamento || cartaoCheckoutBusy) return;
    setCartaoCheckoutBusy(true);
    setCartaoCheckoutErro(null);
    try {
      const checkout = await criarCheckoutCartaoPagBank(result.pagamento.id);
      setCartaoCheckout(checkout);
    } catch (caught) {
      setCartaoCheckoutErro(
        caught instanceof Error ? caught.message : "Checkout PagBank indisponível.",
      );
    } finally {
      setCartaoCheckoutBusy(false);
    }
  }

  async function consultarCheckoutCartao() {
    if (!result?.pagamento || !cartaoCheckout || cartaoCheckoutBusy) return;
    setCartaoCheckoutBusy(true);
    setCartaoCheckoutErro(null);
    try {
      const consultado = await verificarCheckoutCartaoPagBank(result.pagamento.id);
      setCartaoCheckout(consultado);
    } catch (caught) {
      setCartaoCheckoutErro(
        caught instanceof Error ? caught.message : "Falha ao consultar o provedor.",
      );
    } finally {
      setCartaoCheckoutBusy(false);
    }
  }

  async function registrarCartaoAprovado() {
    if (!result?.pagamento || cartaoBusy || cartaoCheckout || !cartaoAprovadoNoTerminal) return;
    setCartaoBusy(true);
    setCartaoErro(null);
    try {
      const retorno = await confirmarCartaoNoTerminal(
        result.pagamento.id,
        cartaoReferencia.trim(),
      );
      if (retorno.status === "pago") {
        setCartaoConfirmado(true);
      } else {
        setCartaoErro("O comprovante foi registrado, mas a venda ainda não consta como paga.");
      }
    } catch (caught) {
      setCartaoErro(
        caught instanceof Error
          ? caught.message
          : "Não foi possível registrar a confirmação do terminal.",
      );
    } finally {
      setCartaoBusy(false);
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && (submitting || pixBusy || cartaoBusy || cartaoCheckoutBusy)) return;
    if (!nextOpen) {
      setError(null);
      setResult(null);
      setReceivedCents(0);
      setPixCobranca(null);
      setPixVerificado(null);
      setPixPagador({ nome: "", email: "", documento: "" });
      setCartaoReferencia("");
      setCartaoAprovadoNoTerminal(false);
      setCartaoConfirmado(false);
      setCartaoErro(null);
      setCartaoCheckout(null);
      setCartaoCheckoutErro(null);
    }
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-4xl overflow-y-auto p-0">
        {result ? (
          <div className="p-6 sm:p-8">
            <div className="mx-auto flex max-w-xl flex-col items-center text-center">
              <div className="flex size-16 items-center justify-center rounded-full bg-[#10b981]/10 text-[#10b981]">
                <CheckCircle2 className="size-9" />
              </div>
              <DialogTitle className="mt-4 text-2xl">{pagamentoLiquidado ? "Venda registrada com sucesso" : "Pedido registrado — pagamento pendente"}</DialogTitle>
              <DialogDescription className="mt-2">
                {pagamentoLiquidado
                  ? "Pagamento confirmado pelo sistema. Confira os dados da operação."
                  : "O pedido foi registrado, mas o pagamento ainda não foi confirmado. Não considere a venda quitada."}
              </DialogDescription>

              {!pagamentoLiquidado ? (
                <p role="alert" className="mt-4 rounded-xl border border-amber-400/40 bg-amber-500/10 px-4 py-3 text-sm font-semibold text-amber-200">
                  PENDENTE: aguarde confirmação financeira confiável antes de concluir a entrega.
                </p>
              ) : null}

              <div className="mt-6 grid w-full gap-3 rounded-2xl border bg-muted/30 p-4 text-left sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pedido</p>
                  <p className="mt-1 break-all font-mono text-sm">{result.comanda.pedido_id}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</p>
                  <p className="mt-1 font-semibold">{result.comanda.status}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pagamento</p>
                  <p className="mt-1 font-semibold">{cartaoConfirmado ? "pago (terminal presencial)" : cartaoCheckout?.status_pagamento ?? pixVerificado ?? result.pagamento?.status ?? "sem pagamento"}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Total</p>
                  <p className="mt-1 text-xl font-black tabular-nums">R$ {result.comanda.total}</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Badge variant="outline">
                  {result.idempotente ? "Replay idempotente · HTTP 200" : pagamentoLiquidado ? "Venda paga · HTTP 201" : "Pedido pendente · HTTP 201"}
                </Badge>
                <Badge variant="outline" className="max-w-full truncate font-mono">
                  correlation {result.correlation_id}
                </Badge>
              </div>


              {result.pagamento?.metodo === "pix" && !pagamentoLiquidado ? (
                <div className="mt-5 w-full space-y-3 rounded-2xl border border-sky-400/30 bg-sky-950/20 p-4 text-left">
                  <p className="font-semibold text-white">Cobrança Pix PagBank</p>
                  <p className="text-sm text-slate-300">
                    Informe os dados exigidos pelo provedor. O pedido permanece pendente
                    até confirmação financeira por consulta autenticada ou webhook assinado.
                  </p>
                  {!pixCobranca ? (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="text-xs text-slate-300">
                        Nome do pagador
                        <input
                          value={pixPagador.nome}
                          maxLength={100}
                          onChange={(event) => setPixPagador((prev) => ({ ...prev, nome: event.target.value }))}
                          className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm text-white"
                        />
                      </label>
                      <label className="text-xs text-slate-300">
                        E-mail do pagador
                        <input
                          type="email"
                          value={pixPagador.email}
                          maxLength={200}
                          onChange={(event) => setPixPagador((prev) => ({ ...prev, email: event.target.value }))}
                          className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm text-white"
                        />
                      </label>
                      <label className="text-xs text-slate-300 sm:col-span-2">
                        CPF/CNPJ (não armazenado no cadastro pelo Kordena)
                        <input
                          value={pixPagador.documento}
                          maxLength={18}
                          onChange={(event) => setPixPagador((prev) => ({ ...prev, documento: event.target.value }))}
                          className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm text-white"
                        />
                      </label>
                      <Button type="button" disabled={pixBusy} onClick={() => void gerarPix()}>
                        {pixBusy ? <Loader2 className="animate-spin" /> : <QrCode />}
                        Gerar Pix no PagBank
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <p className="break-all font-mono text-xs text-slate-300">
                        Pedido do provedor: {pixCobranca.order_id}
                      </p>
                      {pixCobranca.pix_copia_cola ? (
                        <>
                          <textarea
                            readOnly
                            aria-label="Código Pix copia e cola"
                            value={pixCobranca.pix_copia_cola}
                            rows={3}
                            className="w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm text-white"
                          />
                          <Button type="button" variant="outline" onClick={() => void navigator.clipboard.writeText(pixCobranca.pix_copia_cola ?? "")}>
                            Copiar código Pix
                          </Button>
                        </>
                      ) : null}
                      {pixCobranca.qr_code_url?.startsWith("https://") ? (
                        <a
                          href={pixCobranca.qr_code_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block text-sm font-medium text-sky-200 underline"
                        >
                          Abrir QR Code fornecido pelo PagBank
                        </a>
                      ) : null}
                    </div>
                  )}
                  {pixVerificado ? <p role="status">Última conferência: {pixVerificado}</p> : null}
                  <Button
                    type="button"
                    variant="outline"
                    disabled={pixBusy || !pixCobranca}
                    onClick={() => void verificarPix()}
                  >
                    {pixBusy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                    Verificar pagamento no PagBank
                  </Button>
                  {error ? <p role="alert" className="text-sm text-red-300">{error}</p> : null}
                </div>
              ) : null}

              {(result.pagamento?.metodo === "cartao_debito" ||
                result.pagamento?.metodo === "cartao_credito") && !pagamentoLiquidado && !cartaoCheckout ? (
                <div className="mt-5 w-full space-y-3 rounded-2xl border border-amber-400/30 bg-amber-500/5 p-4 text-left">
                  <p className="font-semibold text-white">Pagamento em maquininha presencial</p>
                  <p className="text-sm text-slate-300">
                    Efetue a cobrança diretamente na maquininha do estabelecimento.
                    Somente após a tela ou o comprovante apresentar transação APROVADA,
                    registre abaixo o NSU/código de autorização. Esta opção não
                    processa o cartão nem consulta automaticamente a adquirente.
                  </p>
                  <label className="block text-xs text-slate-200">
                    NSU / código do comprovante aprovado
                    <input
                      value={cartaoReferencia}
                      maxLength={80}
                      onChange={(event) => setCartaoReferencia(event.target.value)}
                      placeholder="Ex.: 12345678"
                      className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950 p-2 text-sm text-white"
                    />
                  </label>
                  <label className="flex gap-2 text-xs text-slate-200">
                    <input
                      type="checkbox"
                      checked={cartaoAprovadoNoTerminal}
                      onChange={(event) => setCartaoAprovadoNoTerminal(event.target.checked)}
                    />
                    Confirmo que o terminal físico aprovou integralmente o valor deste pedido.
                  </label>
                  <Button
                    type="button"
                    onClick={() => void registrarCartaoAprovado()}
                    disabled={cartaoBusy || cartaoCheckoutBusy || !cartaoAprovadoNoTerminal || cartaoReferencia.trim().length < 4}
                  >
                    {cartaoBusy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                    Registrar cartão aprovado
                  </Button>
                  {cartaoErro ? <p role="alert" className="text-xs text-red-300">{cartaoErro}</p> : null}
                </div>
              ) : null}


              {(result.pagamento?.metodo === "cartao_debito" ||
                result.pagamento?.metodo === "cartao_credito") && !pagamentoLiquidado ? (
                <div className="mt-5 w-full space-y-3 rounded-2xl border border-sky-400/30 bg-sky-950/20 p-4 text-left">
                  <p className="font-semibold text-white">Pagar cartão na página segura do PagBank</p>
                  <p className="text-sm text-slate-300">
                    O cartão é informado diretamente no PagBank, não no Kordena.
                    A venda só será quitada após consulta autenticada ao provedor.
                    Débito online requer habilitação da conta PagBank.
                  </p>
                  {!cartaoCheckout ? (
                    <Button type="button" disabled={cartaoCheckoutBusy || cartaoBusy} onClick={() => void abrirCheckoutCartao()}>
                      {cartaoCheckoutBusy ? <Loader2 className="animate-spin" /> : <CreditCard />}
                      Gerar pagamento online PagBank
                    </Button>
                  ) : (
                    <>
                      <p className="break-all font-mono text-xs text-slate-300">
                        Checkout: {cartaoCheckout.checkout_id}
                      </p>
                      {cartaoCheckout.pagamento_url.startsWith("https://") ? (
                        <a
                          href={cartaoCheckout.pagamento_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block rounded-lg border border-sky-400/30 px-4 py-3 text-sm font-semibold text-sky-200 underline"
                        >
                          Abrir página segura para pagar com cartão
                        </a>
                      ) : null}
                      <Button type="button" variant="outline" disabled={cartaoCheckoutBusy} onClick={() => void consultarCheckoutCartao()}>
                        {cartaoCheckoutBusy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                        Verificar pagamento no PagBank
                      </Button>
                      <p role="status" className="text-xs text-amber-200">
                        Último retorno financeiro: {cartaoCheckout.status_pagamento}
                      </p>
                    </>
                  )}
                  {cartaoCheckoutErro ? <p role="alert" className="text-xs text-red-300">{cartaoCheckoutErro}</p> : null}
                </div>
              ) : null}

              <Button className="mt-6 h-12 w-full rounded-xl" onClick={() => handleOpenChange(false)}>
                Nova venda
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="border-b p-6">
              <DialogHeader>
                <DialogTitle className="text-2xl">Finalizar pagamento</DialogTitle>
                <DialogDescription>
                  Selecione o meio de pagamento e confirme o checkout canônico do PDV.
                </DialogDescription>
              </DialogHeader>
            </div>

            <div className="grid gap-6 p-6 md:grid-cols-[1fr_0.9fr]">
              <section>
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Forma de pagamento
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {paymentOptions.map((option) => {
                    const Icon = option.icon;
                    const active = cart.metodoPagamento === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => selectPaymentMethod(option.value)}
                        className={cn(
                          "flex min-h-24 items-center gap-3 rounded-2xl border p-4 text-left transition active:scale-[0.985]",
                          active
                            ? "border-primary bg-primary/10 ring-2 ring-primary/20"
                            : "bg-card hover:bg-muted/50",
                        )}
                      >
                        <span className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl", active ? "bg-primary text-white" : "bg-muted text-foreground")}>
                          <Icon className="size-5" />
                        </span>
                        <span>
                          <strong className="block">{option.label}</strong>
                          <span className="text-xs text-muted-foreground">{option.description}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>

                {cart.metodoPagamento !== "dinheiro" ? (
                  <p role="status" className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs font-medium text-amber-200">
                    Pagamentos eletrônicos só ficam pagos após confirmação do provedor.
                    Este checkout não deve ser tratado como recebimento confirmado ou QR Pix gerado.
                  </p>
                ) : null}

                <div className="mt-6 rounded-2xl border bg-slate-950 p-5 text-white">
                  <div className="flex items-center justify-between text-sm text-slate-400">
                    <span>Total do pedido</span>
                    <span className="tabular-nums">{totals.subtotalFormatted}</span>
                  </div>
                  {totals.discountCents > 0 ? (
                    <div className="mt-2 flex items-center justify-between text-sm text-slate-400">
                      <span>Desconto</span>
                      <span className="tabular-nums">- {totals.discountFormatted}</span>
                    </div>
                  ) : null}
                  <div className="mt-4 flex items-end justify-between border-t border-white/10 pt-4">
                    <span className="font-semibold">A pagar</span>
                    <span className="text-3xl font-black tabular-nums">{totals.totalFormatted}</span>
                  </div>
                </div>
              </section>

              <section className={cn(cart.metodoPagamento !== "dinheiro" && "opacity-50")}>
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Valor recebido
                  </p>
                  <Banknote className="size-5 text-muted-foreground" />
                </div>

                <div className="rounded-2xl border bg-card p-4">
                  <p className="text-center text-3xl font-black tabular-nums">
                    {formatCurrency(receivedCents)}
                  </p>
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    {keypadKeys.map((key) => (
                      <Button
                        key={key}
                        type="button"
                        variant="outline"
                        disabled={cart.metodoPagamento !== "dinheiro"}
                        onClick={() => pressKey(key)}
                        className="h-14 rounded-xl text-lg font-bold"
                        aria-label={key === "backspace" ? "Apagar último dígito" : `Tecla ${key}`}
                      >
                        {key === "backspace" ? <Delete className="size-5" /> : key}
                      </Button>
                    ))}
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-[#10b981]/30 bg-[#10b981]/10 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#10b981]">
                    Troco
                  </p>
                  <p className="mt-1 text-3xl font-black tabular-nums text-[#10b981]">
                    {formatCurrency(changeCents)}
                  </p>
                  {cart.metodoPagamento === "dinheiro" && !cashIsEnough ? (
                    <p className="mt-2 text-xs font-medium text-critical">
                      O valor recebido ainda é inferior ao total.
                    </p>
                  ) : null}
                </div>
              </section>
            </div>

            {error ? (
              <div className="mx-6 rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm font-medium text-critical">
                {error}
              </div>
            ) : null}

            <DialogFooter className="border-t p-6">
              <Button type="button" variant="outline" className="h-12 rounded-xl" onClick={() => handleOpenChange(false)}>
                Voltar
              </Button>
              <Button
                type="button"
                className="h-12 rounded-xl px-8 font-bold"
                disabled={submitting || cart.itens.length === 0 || !cashIsEnough}
                onClick={() => void finalizeCheckout()}
              >
                {submitting ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                {submitting ? "Processando..." : "Confirmar venda"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
