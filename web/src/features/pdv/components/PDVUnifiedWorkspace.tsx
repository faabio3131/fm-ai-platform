"use client";

import { ArrowLeft, RefreshCw, ShieldAlert, Store } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckoutModal } from "@/features/pdv/components/CheckoutModal";
import { OrderCart } from "@/features/pdv/components/OrderCart";
import { ProductCatalog } from "@/features/pdv/components/ProductCatalog";
import {
  clearPdvSession,
  fetchCatalog,
  PdvApiError,
  type CatalogItem,
} from "@/features/pdv/services/pdv-api";
import { cartActions } from "@/features/pdv/store/cart-store";
import { useAuthStore } from "@/features/auth/store/auth-store";

const PDV_PERMISSION = "pdv.operar";

function errorMessage(caught: unknown): string {
  if (caught instanceof PdvApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : "Falha ao carregar o PDV.";
}

export function PDVUnifiedWorkspace() {
  const auth = useAuthStore();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allowed = auth.permissions.includes(PDV_PERMISSION);

  async function loadCatalog() {
    setLoadingCatalog(true);
    setError(null);
    clearPdvSession();
    try {
      setCatalog(await fetchCatalog());
    } catch (caught) {
      setCatalog([]);
      setError(errorMessage(caught));
    } finally {
      setLoadingCatalog(false);
    }
  }

  useEffect(() => {
    if (auth.status !== "authenticated" || !allowed || !auth.unitId) return;
    cartActions.reset();
    setCheckoutOpen(false);
    void loadCatalog();
    // A unidade ativa é autoridade do cookie; trocar unidade força reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.status, auth.unitId, allowed]);

  if (auth.status === "authenticated" && !allowed) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 px-6">
        <div className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-xl">
          <ShieldAlert className="size-8 text-amber-500" />
          <h1 className="mt-4 text-xl font-bold">PDV não liberado para este usuário</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sua identidade está autenticada, mas não possui a permissão pdv.operar nesta função.
          </p>
          <Button asChild className="mt-5 w-full">
            <Link href="/">
              <ArrowLeft />
              Voltar ao dashboard
            </Link>
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main className="h-screen overflow-hidden bg-slate-100 p-3 text-foreground sm:p-4 lg:p-5">
      <div className="mx-auto flex h-full max-w-[1800px] flex-col gap-3">
        <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white px-4 py-3 shadow-sm">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white">
              <Store className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-lg font-black tracking-tight">PDV Touchscreen</h1>
                <Badge className="hidden bg-[#10b981]/10 text-[#10b981] hover:bg-[#10b981]/10 sm:inline-flex">
                  Sessão única
                </Badge>
              </div>
              <p className="truncate text-xs text-muted-foreground">
                {auth.tenantId ?? "—"} · {auth.unitId ?? "—"} · {auth.operator?.email ?? "—"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" className="h-11 rounded-xl" onClick={() => void loadCatalog()} disabled={loadingCatalog}>
              <RefreshCw className={loadingCatalog ? "animate-spin" : ""} />
              <span className="hidden sm:inline">Atualizar catálogo</span>
            </Button>
            <Button asChild type="button" variant="ghost" className="h-11 rounded-xl text-muted-foreground">
              <Link href="/">
                <ArrowLeft />
                <span className="hidden sm:inline">Dashboard</span>
              </Link>
            </Button>
          </div>
        </header>

        {error ? (
          <div className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-2 text-sm font-medium text-critical">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_390px] xl:grid-cols-[minmax(0,1fr)_430px]">
          <div className="min-h-0 rounded-2xl border bg-white p-3 shadow-sm sm:p-4">
            <ProductCatalog products={catalog} loading={loadingCatalog} />
          </div>
          <OrderCart onCheckout={() => setCheckoutOpen(true)} />
        </div>
      </div>

      <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} />
    </main>
  );
}
