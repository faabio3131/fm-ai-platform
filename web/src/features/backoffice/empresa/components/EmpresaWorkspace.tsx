"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  abrirCadastroEmpresa, criarUnidade, salvarEmpresa, salvarUnidade,
  type CadastroEmpresa, type Unidade,
} from "@/features/backoffice/empresa/services/empresa-api";

const inputClass = "mt-1 border-slate-700 bg-slate-950 text-white";

function Campo({ name, label, value = "", required = false, multiline = false }: {
  name: string; label: string; value?: string; required?: boolean; multiline?: boolean;
}) {
  return <label className="block text-sm text-slate-300">{label}
    {multiline ? <textarea name={name} defaultValue={value} className={`${inputClass} w-full rounded-md border p-2`} />
      : <Input name={name} defaultValue={value} required={required} className={inputClass} />}
  </label>;
}

function CamposUnidade({ unidade }: { unidade?: Unidade }) {
  return <div className="grid gap-4 sm:grid-cols-2">
    {!unidade ? <Campo name="unidade_id" label="ID técnico da unidade" required /> : null}
    <Campo name="codigo" label="Código comercial" value={unidade?.codigo} required />
    <Campo name="nome_fantasia" label="Nome fantasia" value={unidade?.nome_fantasia} required />
    <label className="block text-sm text-slate-300">Tipo
      <select name="tipo" defaultValue={unidade?.tipo ?? "filial"} className={`${inputClass} w-full rounded-md border p-2`}>
        <option value="filial">Filial</option><option value="matriz">Matriz</option><option value="unidade">Unidade</option>
      </select>
    </label>
    {unidade ? <>
      <Campo name="documento_fiscal" label="Documento fiscal" value={unidade.documento_fiscal} />
      <Campo name="telefone" label="Telefone comercial" value={unidade.telefone} />
      <Campo name="email" label="E-mail comercial" value={unidade.email} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="ativa" defaultChecked={unidade.ativa} />Unidade ativa</label>
    </> : null}
    <Campo name="endereco" label="Endereço comercial" value={unidade?.endereco} multiline />
    <Campo name="horarios" label="Horários de funcionamento" value={unidade?.horarios} multiline />
  </div>;
}

function texto(form: FormData, name: string): string {
  return String(form.get(name) ?? "");
}

function CadastroWorkspace() {
  const [cadastro, setCadastro] = useState<CadastroEmpresa | null>(null);
  const [selecionada, setSelecionada] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const dados = await abrirCadastroEmpresa();
      setCadastro(dados);
      setSelecionada((atual) => dados.unidades.some(u => u.unidade_id === atual) ? atual : "");
    } catch (error) {
      setCadastro(null);
      setErro(error instanceof Error ? error.message : "Não foi possível carregar o cadastro.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timer);
  }, [carregar]);

  async function executar(operacao: () => Promise<unknown>, mensagem: string) {
    setBusy(true); setErro(null); setAviso(null);
    try {
      await operacao();
      await carregar();
      setAviso(mensagem);
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível salvar o cadastro.");
    } finally { setBusy(false); }
  }

  function atualizarEmpresa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!cadastro) return;
    const form = new FormData(event.currentTarget);
    const payload = {
      nome_exibicao: texto(form, "nome_exibicao"), moeda: texto(form, "moeda"),
      timezone: texto(form, "timezone"), ativa: form.has("ativa"), versao: cadastro.empresa.versao,
    };
    void executar(() => salvarEmpresa(payload), "Empresa atualizada.");
  }

  const unidade = cadastro?.unidades.find(u => u.unidade_id === selecionada);

  function atualizarUnidade(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!unidade) return;
    const form = new FormData(event.currentTarget);
    const payload = {
      codigo: texto(form, "codigo"), nome_fantasia: texto(form, "nome_fantasia"), tipo: texto(form, "tipo"),
      documento_fiscal: texto(form, "documento_fiscal"), telefone: texto(form, "telefone"), email: texto(form, "email"),
      endereco: texto(form, "endereco"), horarios: texto(form, "horarios"), ativa: form.has("ativa"), versao: unidade.versao,
    };
    void executar(() => salvarUnidade(unidade.unidade_id, payload), "Unidade atualizada.");
  }

  function novaUnidade(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      unidade_id: texto(form, "unidade_id"), codigo: texto(form, "codigo"), nome_fantasia: texto(form, "nome_fantasia"),
      tipo: texto(form, "tipo"), endereco: texto(form, "endereco"), horarios: texto(form, "horarios"),
    };
    void executar(() => criarUnidade(payload), "Unidade cadastrada.");
  }

  return <main className="mx-auto w-full max-w-5xl space-y-6 p-6 text-slate-100">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold">Empresa e Unidades</h1>
        <p className="mt-2 text-sm text-slate-400">Administre os cadastros da empresa. Para trocar a unidade de trabalho, use o seletor no cabeçalho.</p></div>
      <Button onClick={() => void carregar()} disabled={loading || busy}>Recarregar</Button>
    </header>
    {erro ? <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">{erro}</p> : null}
    {aviso ? <p role="status" className="text-emerald-300">{aviso}</p> : null}
    {loading ? <p role="status">Carregando cadastro…</p> : cadastro ? <>
      <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="text-xl font-semibold">Empresa</h2>
        <form key={cadastro.empresa.versao} onSubmit={atualizarEmpresa}>
          <fieldset disabled={busy} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo name="nome_exibicao" label="Nome da empresa" value={cadastro.empresa.nome_exibicao} required />
              <Campo name="moeda" label="Moeda" value={cadastro.empresa.moeda} required />
              <Campo name="timezone" label="Timezone" value={cadastro.empresa.timezone} required />
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="ativa" defaultChecked={cadastro.empresa.ativa} />Empresa ativa</label>
            </div>
            <Button type="submit">Salvar empresa</Button>
          </fieldset>
        </form>
      </section>
      <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="text-xl font-semibold">Matriz e filiais</h2>
        {cadastro.unidades.length === 0 ? <p>Nenhuma unidade cadastrada.</p> : <>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm">
            <thead><tr>{["Unidade", "Código", "Nome", "Tipo", "Ativa", "Versão"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead>
            <tbody>{cadastro.unidades.map(u => <tr key={u.unidade_id} className="border-t border-slate-800">
              {[u.unidade_id, u.codigo, u.nome_fantasia, u.tipo, u.ativa ? "Sim" : "Não", String(u.versao)].map((valor, index) => <td key={index} className="p-2">{valor}</td>)}
            </tr>)}</tbody>
          </table></div>
          <label className="block text-sm">Editar cadastro de unidade
            <select value={selecionada} onChange={event => setSelecionada(event.target.value)} disabled={busy} className={`${inputClass} w-full rounded-md border p-2`}>
              <option value="">Selecione um cadastro</option>
              {cadastro.unidades.map(u => <option key={u.unidade_id} value={u.unidade_id}>{u.nome_fantasia} · {u.unidade_id}</option>)}
            </select>
          </label>
          {unidade ? <form key={`${unidade.unidade_id}:${unidade.versao}`} onSubmit={atualizarUnidade}>
            <fieldset disabled={busy} className="space-y-4"><CamposUnidade unidade={unidade} /><Button type="submit">Salvar unidade</Button></fieldset>
          </form> : null}
        </>}
      </section>
      <details className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <summary className="cursor-pointer font-semibold">Cadastrar nova filial/unidade</summary>
        <form className="mt-4" onSubmit={novaUnidade}><fieldset disabled={busy} className="space-y-4">
          <CamposUnidade /><Button type="submit">Criar unidade</Button>
        </fieldset></form>
      </details>
    </> : null}
  </main>;
}

export function EmpresaWorkspace() {
  const auth = useAuthStore();
  if (auth.status !== "authenticated") return <p>Carregando sessão…</p>;
  if (!auth.permissions.includes("admin.acessar") || !auth.permissions.includes("configuracao.alterar")) {
    return <p role="alert">Sua conta não possui acesso ao cadastro administrativo.</p>;
  }
  return <CadastroWorkspace key={`${auth.tenantId}:${auth.unitId}`} />;
}
