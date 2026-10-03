"use client";

import { Activity, Database, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  API_BASE_URL,
  checkBackendHealth,
  type BackendHealthResult,
} from "@/lib/api";

type ConnectionState = "checking" | "online" | "offline";

export default function SystemHealthPage() {
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [health, setHealth] = useState<BackendHealthResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void checkBackendHealth()
      .then((result) => {
        if (cancelled) return;
        setHealth(result);
        setConnection(result.health.ok ? "online" : "offline");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setHealth(null);
        setConnection("offline");
        setError(caught instanceof Error ? caught.message : "Falha desconhecida");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function validateBackend(): Promise<void> {
    setConnection("checking");
    setError(null);

    try {
      const result = await checkBackendHealth();
      setHealth(result);
      setConnection(result.health.ok ? "online" : "offline");
    } catch (caught: unknown) {
      setHealth(null);
      setConnection("offline");
      setError(caught instanceof Error ? caught.message : "Falha desconhecida");
    }
  }

  const badgeClass =
    connection === "online"
      ? "border-emerald-300/20 bg-emerald-400/[0.08] text-emerald-200"
      : connection === "offline"
        ? "border-red-300/20 bg-red-500/[0.08] text-red-200"
        : "border-amber-300/20 bg-amber-400/[0.08] text-amber-200";

  return (
    <div className="kordena-page-dark min-h-full px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <header className="relative overflow-hidden rounded-[2rem] border border-sky-400/15 bg-[linear-gradient(135deg,rgba(47,124,246,0.16),rgba(14,165,233,0.05)_48%,rgba(8,17,31,0.96))] p-6 shadow-[0_28px_70px_-42px_rgba(47,124,246,0.64)] sm:flex sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-sky-300">
              Área protegida
            </p>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-50">
              Saúde do sistema
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Diagnóstico técnico de conectividade do frontend com o backend. Esta informação permanece fora da home comercial.
            </p>
          </div>
          <Badge variant="outline" className={badgeClass}>
            {connection === "online"
              ? "Backend online"
              : connection === "offline"
                ? "Backend indisponível"
                : "Validando conexão"}
          </Badge>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardDescription>API base</CardDescription>
                <Activity className="size-4 text-sky-300" />
              </div>
              <CardTitle className="text-base">FastAPI</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="break-all font-mono text-sm text-slate-400">{API_BASE_URL}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardDescription>Health contract</CardDescription>
                <Database className="size-4 text-emerald-300" />
              </div>
              <CardTitle className="text-base">{health?.endpoint ?? "/health/live"}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-slate-400">
                {health?.health.backend
                  ? `Backend: ${health.health.backend}`
                  : "Aguardando resposta do backend"}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardDescription>Security boundary</CardDescription>
                <ShieldCheck className="size-4 text-sky-300" />
              </div>
              <CardTitle className="text-base">Tenant-aware HTTP</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-slate-400">
                A identidade e o escopo operacional são validados pela sessão assinada no backend.
              </p>
            </CardContent>
          </Card>
        </section>

        <Card>
          <CardHeader>
            <CardTitle>Conectividade</CardTitle>
            <CardDescription>
              O cliente tenta o contrato preferencial e preserva o fallback legado somente quando aplicável.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-100">
                Estado: {connection === "online" ? "conectado" : connection === "checking" ? "verificando" : "indisponível"}
              </p>
              {error ? (
                <p className="mt-1 break-all text-sm text-red-300">{error}</p>
              ) : (
                <p className="mt-1 text-sm text-slate-400">
                  {health?.endpoint
                    ? `Resposta validada via ${health.endpoint}`
                    : "Nenhuma resposta validada ainda"}
                </p>
              )}
            </div>
            <Button onClick={() => void validateBackend()} disabled={connection === "checking"}>
              <RefreshCw className={connection === "checking" ? "animate-spin" : ""} />
              Revalidar
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
