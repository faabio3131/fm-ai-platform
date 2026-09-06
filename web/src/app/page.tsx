"use client";

import { Activity, Database, RefreshCw, ShieldCheck, ShoppingCart } from "lucide-react";
import Link from "next/link";
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

export default function Home() {
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

  async function validateBackend() {
    setConnection("checking");
    setError(null);

    try {
      const result = await checkBackendHealth();
      setHealth(result);
      setConnection(result.health.ok ? "online" : "offline");
    } catch (caught) {
      setHealth(null);
      setConnection("offline");
      setError(caught instanceof Error ? caught.message : "Falha desconhecida");
    }
  }

  const badgeClass =
    connection === "online"
      ? "border-success/30 bg-success/10 text-success"
      : connection === "offline"
        ? "border-critical/30 bg-critical/10 text-critical"
        : "border-warning/30 bg-warning/10 text-warning";

  return (
    <main className="min-h-screen bg-background px-6 py-10 text-foreground lg:px-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Kordena Enterprise
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">
              Frontend foundation status
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Next.js App Router, Tailwind CSS e shadcn/ui desacoplados do runtime
              Streamlit legado.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={badgeClass}>
              {connection === "online"
                ? "Backend online"
                : connection === "offline"
                  ? "Backend offline"
                  : "Validando conexão"}
            </Badge>
            <Button asChild className="h-10 rounded-xl">
              <Link href="/pdv">
                <ShoppingCart />
                Abrir PDV Touch
              </Link>
            </Button>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardDescription>API base</CardDescription>
                <Activity className="size-4 text-primary" />
              </div>
              <CardTitle className="text-base">FastAPI</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="break-all font-mono text-sm text-muted-foreground">
                {API_BASE_URL}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardDescription>Health contract</CardDescription>
                <Database className="size-4 text-success" />
              </div>
              <CardTitle className="text-base">{health?.endpoint ?? "/health/live"}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
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
                <ShieldCheck className="size-4 text-primary" />
              </div>
              <CardTitle className="text-base">Tenant-aware HTTP</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Authorization, tenant e unidade são injetados pelo cliente base.
              </p>
            </CardContent>
          </Card>
        </section>

        <Card>
          <CardHeader>
            <CardTitle>Conectividade local</CardTitle>
            <CardDescription>
              O contrato preferencial é /health/live. Enquanto o backend V1 mantém
              /healthz como rota canônica, o cliente usa fallback somente em HTTP 404.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium">
                Estado: {connection === "online" ? "conectado" : connection === "checking" ? "verificando" : "indisponível"}
              </p>
              {error ? (
                <p className="mt-1 break-all text-sm text-critical">{error}</p>
              ) : (
                <p className="mt-1 text-sm text-muted-foreground">
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
    </main>
  );
}
