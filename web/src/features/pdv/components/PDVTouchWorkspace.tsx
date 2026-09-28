"use client";

import { ArrowLeft, LogOut, RefreshCw, ShieldCheck, Store } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { CheckoutModal } from "@/features/pdv/components/CheckoutModal";
import { OrderCart } from "@/features/pdv/components/OrderCart";
import { ProductCatalog } from "@/features/pdv/components/ProductCatalog";
import {
  clearPdvSession,
  configurePdvSession,
  fetchCatalog,
  PdvApiError,
  type CatalogItem,
} from "@/features/pdv/services/pdv-api";
import { cartActions } from "@/features/pdv/store/cart-store";

export function PDVTouchWorkspace() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [connected, setConnected] = useState(false);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [unitId, setUnitId] = useState("");

  async function loadCatalog() {
    setLoadingCatalog(true);
    setError(null);
    try {
      const products = await fetchCatalog();
      setCatalog(products);
      return true;
    } catch (caught) {
      if (caught instanceof PdvApiError) {
        setError(caught.code ? `${caught.message} · ${caught.code}` : caught.message);
      } else {
        setError(caught instanceof Error ? caught.message : "Falha ao carregar o catálogo do PDV.");
      }
      return false;
    } finally {
      setLoadingCatalog(false);
    }
  }

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    try {
      configurePdvSession({ email, password, tenantId, unitId });
      const ok = await loadCatalog();
      if (ok) {
        setConnected(true);
        setPassword("");
      } else {
        clearPdvSession();
      }
    } catch (caught) {
      clearPdvSession();
      setError(caught instanceof Error ? caught.message : "Falha ao configurar a sessão do PDV.");
    }
  }

  function disconnect() {
    clearPdvSession();
    cartActions.reset();
    setCatalog([]);
    setConnected(false);
    setCheckoutOpen(false);
    setError(null);
    setPassword("");
  }

  if (!connected) {
    return (
      <main className="kordena-page-dark min-h-screen px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
        <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl items-center justify-center">
          <Card className="w-full max-w-xl border-white/10 bg-slate-950/80 shadow-2xl shadow-black/30">
            <CardHeader className="space-y-4 border-b border-white/10 bg-slate-950/90 text-white">
              <div className="flex items-center justify-between gap-3">
                <div className="flex size-12 items-center justify-center rounded-2xl bg-primary text-white">
                  <Store className="size-6" />
                </div>
                <Badge className="border border-white/10 bg-white/10 text-white hover:bg-white/10">
                  PDV Touch V1
                </Badge>
              </div>
              <div>
                <CardTitle className="text-2xl text-white">Abrir sessão operacional</CardTitle>
                <CardDescription className="mt-2 text-slate-400">
                  As credenciais permanecem apenas em memória durante esta sessão do navegador e são usadas exclusivamente no contrato canônico do PDV.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-6">
              <form className="space-y-4" onSubmit={(event) => void connect(event)}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-1.5 text-sm font-medium">
                    Tenant
                    <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="tenant-id" required className="h-12" />
                  </label>
                  <label className="space-y-1.5 text-sm font-medium">
                    Unidade
                    <Input value={unitId} onChange={(event) => setUnitId(event.target.value)} placeholder="unidade-id" required className="h-12" />
                  </label>
                </div>
                <label className="block space-y-1.5 text-sm font-medium">
                  Operador
                  <Input autoComplete="username" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="caixa@empresa.com" required className="h-12" />
                </label>
                <label className="block space-y-1.5 text-sm font-medium">
                  Senha
                  <Input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required className="h-12" />
                </label>

                {error ? (
                  <div className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm font-medium text-critical">
                    {error}
                  </div>
                ) : null}

                <Button type="submit" className="h-13 w-full rounded-xl text-base font-bold" disabled={loadingCatalog}>
                  {loadingCatalog ? <RefreshCw className="animate-spin" /> : <ShieldCheck />}
                  {loadingCatalog ? "Validando sessão..." : "Entrar no PDV"}
                </Button>
                <Button asChild type="button" variant="ghost" className="h-11 w-full">
                  <Link href="/">
                    <ArrowLeft />
                    Voltar ao dashboard
                  </Link>
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  return (
    <main className="kordena-page-dark h-screen overflow-hidden p-3 text-slate-100 sm:p-4 lg:p-5">
      <div className="mx-auto flex h-full max-w-[1800px] flex-col gap-3">
        <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-950/80 px-4 py-3 shadow-xl shadow-black/20 backdrop-blur-xl">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#2563eb] to-[#0ea5e9] text-white shadow-lg shadow-blue-950/30">
              <Store className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-lg font-black tracking-tight text-white">PDV Touchscreen</h1>
                <Badge className="hidden bg-[#10b981]/10 text-[#10b981] hover:bg-[#10b981]/10 sm:inline-flex">
                  Online
                </Badge>
              </div>
              <p className="truncate text-xs text-slate-500">
                {tenantId} · {unitId} · contrato /v1/pdv
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" className="h-11 rounded-xl" onClick={() => void loadCatalog()} disabled={loadingCatalog}>
              <RefreshCw className={loadingCatalog ? "animate-spin" : ""} />
              <span className="hidden sm:inline">Atualizar catálogo</span>
            </Button>
            <Button type="button" variant="ghost" className="h-11 rounded-xl text-slate-400 hover:bg-white/[0.06] hover:text-white" onClick={disconnect}>
              <LogOut />
              <span className="hidden sm:inline">Encerrar</span>
            </Button>
          </div>
        </header>

        {error ? (
          <div className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-2 text-sm font-medium text-critical">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_390px] xl:grid-cols-[minmax(0,1fr)_430px]">
          <div className="min-h-0 rounded-2xl border border-white/10 bg-slate-950/70 p-3 shadow-xl shadow-black/20 backdrop-blur-xl sm:p-4">
            <ProductCatalog products={catalog} loading={loadingCatalog} />
          </div>
          <OrderCart onCheckout={() => setCheckoutOpen(true)} />
        </div>
      </div>

      <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} />
    </main>
  );
}
