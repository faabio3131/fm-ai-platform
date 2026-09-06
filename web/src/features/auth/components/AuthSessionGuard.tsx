"use client";

import { Loader2, RefreshCw, ShieldAlert } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  refreshAuthSession,
  useAuthStore,
} from "@/features/auth/store/auth-store";

const PROTECTED_PREFIXES = ["/pdv", "/kds", "/salao"] as const;

function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function AuthSessionGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuthStore();
  const protectedPath = isProtectedPath(pathname);

  useEffect(() => {
    if (auth.status === "idle") {
      void refreshAuthSession().catch(() => undefined);
    }
  }, [auth.status]);

  useEffect(() => {
    if (protectedPath && auth.status === "unauthenticated") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [auth.status, pathname, protectedPath, router]);

  if (!protectedPath) {
    return children;
  }

  if (auth.status === "idle" || auth.status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
        <div className="flex items-center gap-3 text-sm text-slate-300">
          <Loader2 className="size-5 animate-spin text-blue-400" />
          Validando sessão operacional…
        </div>
      </main>
    );
  }

  if (auth.status === "error") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
          <ShieldAlert className="mb-4 size-8 text-amber-400" />
          <h1 className="text-lg font-semibold">Não foi possível validar sua sessão</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            O acesso operacional permanece bloqueado até o servidor confirmar sua identidade.
          </p>
          <Button
            className="mt-5 w-full"
            onClick={() => void refreshAuthSession().catch(() => undefined)}
          >
            <RefreshCw className="size-4" />
            Tentar novamente
          </Button>
        </div>
      </main>
    );
  }

  if (auth.status === "unauthenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        <Loader2 className="size-5 animate-spin" />
      </main>
    );
  }

  return children;
}
