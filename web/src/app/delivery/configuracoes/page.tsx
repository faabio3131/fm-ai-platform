"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import { useAuthStore } from "@/features/auth/store/auth-store";

export default function ConfiguracoesEntregaPage() {
  const auth = useAuthStore();
  const autorizado = auth.permissions.includes("admin.acessar");
  const [limite, setLimite] = useState("10");
  const [estado, setEstado] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (auth.status !== "authenticated" || !autorizado) return;
    let ativo = true;
    void fetch(`${API_BASE_URL}/v1/delivery/configuracoes/alcance`, {
      credentials: "include", cache: "no-store",
    }).then(async (res) => {
      if (!res.ok) throw new Error("Não foi possível consultar o limite configurado.");
      return res.json() as Promise<{ limite_km: number | null }>;
    }).then((dados) => {
      if (ativo) setLimite(String(dados.limite_km ?? 10));
    }).catch((erro: unknown) => {
      if (ativo) setEstado(erro instanceof Error ? erro.message : "Consulta indisponível.");
    });
    return () => { ativo = false; };
  }, [auth.status, auth.unitId, autorizado]);

  async function salvar() {
    const valor = Number(limite);
    if (!Number.isInteger(valor) || valor < 1 || valor > 200) {
      setEstado("Informe um alcance inteiro entre 1 e 200 km.");
      return;
    }
    setSalvando(true);
    setEstado("");
    try {
      const resposta = await fetch(`${API_BASE_URL}/v1/delivery/configuracoes/alcance`, {
        method: "PUT", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limite_km: valor }),
      });
      if (!resposta.ok) throw new Error(resposta.status === 403
        ? "Acesse a Área do Proprietário e realize a reautenticação administrativa."
        : "Não foi possível salvar a política de alcance.");
      setEstado("Alcance de entrega salvo nesta unidade.");
    } catch (erro) {
      setEstado(erro instanceof Error ? erro.message : "Falha ao salvar alcance.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6 text-white">
      <Link href="/delivery" className="text-sm text-sky-300">← Voltar para Entregas</Link>
      <h1 className="text-2xl font-bold">Alcance de entrega</h1>
      <p className="text-sm text-slate-300">O limite é calculado pela distância real do percurso retornada pelo Google Maps Routes, nunca por linha reta. Cada unidade possui configuração própria.</p>
      {!autorizado ? <p>Somente proprietário ou administrador autorizado pode alterar esta política.</p> : (
        <section className="space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-6">
          <label htmlFor="alcance-km" className="block font-medium">Alcance máximo por percurso (km)</label>
          <input id="alcance-km" type="number" min={1} max={200} step={1} value={limite}
            onChange={(e) => setLimite(e.target.value)}
            className="w-full rounded-lg border border-slate-600 bg-slate-950 px-4 py-3" />
          <div className="flex flex-wrap gap-2">
            {[5, 10, 20, 30, 50].map((km) => (
              <button key={km} type="button" onClick={() => setLimite(String(km))}
                className="rounded-lg border border-slate-600 px-3 py-2 text-sm">{km} km</button>
            ))}
          </div>
          <button type="button" disabled={salvando} onClick={() => void salvar()}
            className="rounded-lg bg-blue-600 px-4 py-3 font-medium disabled:opacity-50">
            {salvando ? "Salvando..." : "Salvar alcance da unidade"}
          </button>
          <p aria-live="polite" className="text-sm text-sky-200">{estado}</p>
        </section>
      )}
      <p className="text-sm text-amber-200">Se o Google Maps não calcular uma rota válida, a IA não aprovará o frete automaticamente. O gestor deverá combinar o atendimento diretamente com o entregador, fora da cotação automática.</p>
    </main>
  );
}
