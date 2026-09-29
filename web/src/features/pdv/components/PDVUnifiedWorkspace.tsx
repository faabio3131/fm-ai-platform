"use client";

import { ArrowLeft, RefreshCw, ShieldAlert, Store } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CouvertArtisticoPanel } from "@/features/pdv/components/CouvertArtisticoPanel";
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
    const timeoutId = window.setTimeout(() => {
      cartActions.reset();
      setCheckoutOpen(false);
      void loadCatalog();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, allowed]);

  if (auth.status === "authenticated" && !allowed) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#06101d] px-6">
        <div className="w-full max-w-md rounded-2xl border border-slate-700/60 bg-[linear-gradient(145deg,#0f1e33,#081421)] p-6 text-slate-100 shadow-[0_30px_80px_-38px_rgba(0,0,0,0.9)]">
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
    <main className="min-h-screen bg-[#06101d] p-2.5 text-slate-100 sm:p-3 lg:p-4">
      <div className="mx-auto flex min-h-[calc(100vh-1.5rem)] max-w-[1800px] flex-col gap-2.5">
        <header className="flex min-h-14 flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-700/60 bg-[linear-gradient(145deg,rgba(15,30,51,0.97),rgba(8,20,36,0.97))] px-3.5 py-2.5 shadow-[0_18px_44px_-30px_rgba(0,0,0,0.78)]">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white">
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
            <Button type="button" variant="outline" className="h-9 rounded-xl" onClick={() => void loadCatalog()} disabled={loadingCatalog}>
              <RefreshCw className={loadingCatalog ? "animate-spin" : ""} />
              <span className="hidden sm:inline">Atualizar catálogo</span>
            </Button>
            <Button asChild type="button" variant="ghost" className="h-9 rounded-xl text-muted-foreground">
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

        <CouvertArtisticoPanel />

        <div className="grid min-h-0 flex-1 gap-2.5 lg:grid-cols-[minmax(0,1fr)_370px] xl:grid-cols-[minmax(0,1fr)_410px]">
          <div className="min-h-0 rounded-2xl border border-slate-700/60 bg-[linear-gradient(145deg,rgba(15,30,51,0.97),rgba(8,20,36,0.97))] p-2.5 shadow-[0_18px_44px_-30px_rgba(0,0,0,0.78)] sm:p-3">
            <ProductCatalog products={catalog} loading={loadingCatalog} />
          </div>
          <OrderCart onCheckout={() => setCheckoutOpen(true)} />
        </div>
      </div>

      <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} />
    </main>
  );
}
