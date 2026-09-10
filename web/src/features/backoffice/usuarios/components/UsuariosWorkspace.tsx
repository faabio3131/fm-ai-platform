"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Save, X, Edit } from "lucide-react";

import { useAuthStore } from "@/features/auth/store/auth-store";
import { API_BASE_URL } from "@/lib/api";

type Papel = "ADMINISTRADOR" | "GERENTE" | "CAIXA" | "GARCOM" | "COZINHA" | "EXPEDICAO" | "ENTREGADOR" | "CLIENTE";

interface Usuario {
  usuario_id: string;
  email: string;
  ativo: boolean;
  papeis: string[];
  unidades: string[];
  unidade_padrao: string;
  acesso_admin_sensivel: boolean;
  permissoes_efetivas: string[];
}

interface Unidade {
  unidade_id: string;
  codigo: string;
  nome_fantasia: string;
}

interface UsuariosWorkspaceState {
  usuarios: Usuario[];
  unidades: Unidade[];
  loading: boolean;
  saving: boolean;
  editing: Usuario | null;
  dialogOpen: boolean;
  form: {
    email: string;
    password: string;
    unidade_padrao_id: string;
    papeis: string[];
    unidades_permitidas: string[];
    acesso_admin_sensivel: boolean;
    admin_pin: string;
  };
  erro: string | null;
}

const PAPIS_DISPONIVEIS: Papel[] = ["ADMINISTRADOR", "GERENTE", "CAIXA", "GARCOM", "COZINHA", "EXPEDICAO", "ENTREGADOR", "CLIENTE"];

export function UsuariosWorkspace() {
  const auth = useAuthStore();
  const [state, setState] = useState<UsuariosWorkspaceState>({
    usuarios: [],
    unidades: [],
    loading: true,
    saving: false,
    editing: null,
    dialogOpen: false,
    form: {
      email: "",
      password: "",
      unidade_padrao_id: "",
      papeis: [],
      unidades_permitidas: [],
      acesso_admin_sensivel: false,
      admin_pin: "",
    },
    erro: null,
  });

  const fetchUnidades = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/admin/empresa`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const data = await res.json();
        setState((s) => ({
          ...s,
          unidades: data.unidades.map((u: any) => ({
            unidade_id: u.unidade_id,
            codigo: u.codigo,
            nome_fantasia: u.nome_fantasia,
          })),
        }));
      }
    } catch {
      // silencioso
    }
  }, []);

  const fetchUsuarios = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, erro: null }));
    try {
      const res = await fetch(`${API_BASE_URL}/v1/admin/usuarios`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const data = await res.json();
        setState((s) => ({ ...s, usuarios: data, loading: false }));
      } else {
        setState((s) => ({ ...s, loading: false, erro: "Falha ao carregar usuários" }));
      }
    } catch {
      setState((s) => ({ ...s, loading: false, erro: "Erro de conexão" }));
    }
  }, []);

  const handleOpenCreate = useCallback(() => {
    const primeiraUnidade = state.unidades[0]?.unidade_id || "";
    setState((s) => ({
      ...s,
      editing: null,
      dialogOpen: true,
      form: {
        email: "",
        password: "",
        unidade_padrao_id: primeiraUnidade,
        papeis: [],
        unidades_permitidas: [primeiraUnidade],
        acesso_admin_sensivel: false,
        admin_pin: "",
      },
      erro: null,
    }));
  }, [state.unidades]);

  const handleOpenEdit = useCallback((usuario: Usuario) => {
    setState((s) => ({
      ...s,
      editing: usuario,
      dialogOpen: true,
      form: {
        email: usuario.email,
        password: "",
        unidade_padrao_id: usuario.unidade_padrao,
        papeis: [...usuario.papeis],
        unidades_permitidas: [...usuario.unidades],
        acesso_admin_sensivel: usuario.acesso_admin_sensivel,
        admin_pin: "",
      },
      erro: null,
    }));
  }, []);

  const handleCloseDialog = useCallback(() => {
    setState((s) => ({ ...s, dialogOpen: false, editing: null, erro: null }));
  }, []);

  const handleChange = useCallback((field: string, value: any) => {
    setState((s) => ({ ...s, form: { ...s.form, [field]: value } }));
  }, []);

  const handleTogglePapel = useCallback((papel: string) => {
    setState((s) => ({
      ...s,
      form: {
        ...s.form,
        papeis: s.form.papeis.includes(papel)
          ? s.form.papeis.filter((p) => p !== papel)
          : [...s.form.papeis, papel],
      },
    }));
  }, []);

  const handleToggleUnidade = useCallback((unidadeId: string) => {
    setState((s) => ({
      ...s,
      form: {
        ...s.form,
        unidades_permitidas: s.form.unidades_permitidas.includes(unidadeId)
          ? s.form.unidades_permitidas.filter((u) => u !== unidadeId)
          : [...s.form.unidades_permitidas, unidadeId],
      },
    }));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!state.form.email || !state.form.unidade_padrao_id || !state.form.unidades_permitidas.length) {
      setState((s) => ({ ...s, erro: "Preencha todos os campos obrigatórios" }));
      return;
    }
    if (!state.editing && !state.form.password) {
      setState((s) => ({ ...s, erro: "Senha é obrigatória para novo usuário" }));
      return;
    }

    setState((s) => ({ ...s, saving: true, erro: null }));

    try {
      const url = state.editing
        ? `${API_BASE_URL}/v1/admin/usuarios/${state.editing.usuario_id}`
        : `${API_BASE_URL}/v1/admin/usuarios`;
      const method = state.editing ? "PUT" : "POST";

      const body = state.editing
        ? {
            papeis: state.form.papeis,
            unidades_permitidas: state.form.unidades_permitidas,
            unidade_padrao_id: state.form.unidade_padrao_id,
            ativo: state.editing.ativo,
            acesso_admin_sensivel: state.form.acesso_admin_sensivel,
            nova_senha: state.form.password || undefined,
          }
        : {
            email: state.form.email,
            password: state.form.password,
            unidade_padrao_id: state.form.unidade_padrao_id,
            papeis: state.form.papeis,
            unidades_permitidas: state.form.unidades_permitidas,
            acesso_admin_sensivel: state.form.acesso_admin_sensivel,
            admin_pin: state.form.admin_pin || undefined,
          };

      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        handleCloseDialog();
        fetchUsuarios();
      } else {
        const err = await res.json().catch(() => ({ erro: "erro_desconhecido" }));
        setState((s) => ({ ...s, saving: false, erro: err.erro || "Falha na operação" }));
      }
    } catch {
      setState((s) => ({ ...s, saving: false, erro: "Erro de conexão" }));
    }
  }, [state.editing, state.form, handleCloseDialog, fetchUsuarios]);

  useEffect(() => {
    fetchUnidades();
    fetchUsuarios();
  }, [fetchUnidades, fetchUsuarios, auth.tenantId, auth.unitId]);

  const inputClass = "mt-1 border-slate-700 bg-slate-950 text-white";

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 p-6 text-slate-100">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Usuários e Permissões</h1>
          <p className="mt-2 text-sm text-slate-400">
            Gerencie usuários, papéis, unidades permitidas e unidade padrão.
          </p>
        </div>
        <Button onClick={handleOpenCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Novo Usuário
        </Button>
      </header>

      {state.erro ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-100">
          <span>{state.erro}</span>
          <Button type="button" variant="outline" size="sm" onClick={fetchUsuarios}>
            Tentar novamente
          </Button>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Lista de Usuários</CardTitle>
        </CardHeader>
        <CardContent>
          {state.loading ? (
            <div className="py-8 text-center text-slate-400">Carregando...</div>
          ) : state.usuarios.length === 0 ? (
            <div className="py-8 text-center text-slate-400">Nenhum usuário cadastrado</div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Papéis</TableHead>
                    <TableHead>Unidades</TableHead>
                    <TableHead>Padrão</TableHead>
                    <TableHead>Admin Sensível</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-[100px]">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {state.usuarios.map((usuario) => (
                    <TableRow key={usuario.usuario_id}>
                      <TableCell>{usuario.email}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {usuario.papeis.map((p) => (
                            <span
                              key={p}
                              className="inline-flex items-center rounded-full bg-blue-500/20 px-2 py-0.5 text-xs text-blue-300"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {usuario.unidades.map((u) => (
                            <span
                              key={u}
                              className="inline-flex items-center rounded-full bg-slate-700 px-2 py-0.5 text-xs"
                            >
                              {u}
                            </span>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>{usuario.unidade_padrao}</TableCell>
                      <TableCell>
                        {usuario.acesso_admin_sensivel ? (
                          <span className="inline-flex items-center rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-300">
                            Sim
                          </span>
                        ) : (
                          <span className="text-slate-400">Não</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {usuario.ativo ? (
                          <span className="inline-flex items-center rounded-full bg-green-500/20 px-2 py-0.5 text-xs text-green-300">
                            Ativo
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-red-500/20 px-2 py-0.5 text-xs text-red-300">
                            Inativo
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleOpenEdit(usuario)}
                          aria-label="Editar usuário"
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={state.dialogOpen} onOpenChange={handleCloseDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{state.editing ? "Editar Usuário" : "Novo Usuário"}</DialogTitle>
          </DialogHeader>
          {state.erro && !state.editing ? (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-100">
              <span>{state.erro}</span>
            </div>
          ) : null}
          <div className="grid gap-4 py-4">
            <label className="block text-sm text-slate-300">
              Email <span className="text-rose-400">*</span>
              <Input
                id="email"
                type="email"
                value={state.form.email}
                onChange={(e) => handleChange("email", e.target.value)}
                disabled={!!state.editing}
                placeholder="usuario@exemplo.com"
                className={`${inputClass} w-full rounded-md border p-2`}
              />
            </label>

            {!state.editing && (
              <label className="block text-sm text-slate-300">
                Senha <span className="text-rose-400">*</span>
                <Input
                  id="password"
                  type="password"
                  value={state.form.password}
                  onChange={(e) => handleChange("password", e.target.value)}
                  placeholder="Mínimo 10 caracteres"
                  className={`${inputClass} w-full rounded-md border p-2`}
                />
              </label>
            )}

            <label className="block text-sm text-slate-300">
              Unidade Padrão <span className="text-rose-400">*</span>
              <select
                value={state.form.unidade_padrao_id}
                onChange={(e) => handleChange("unidade_padrao_id", e.target.value)}
                className={`${inputClass} w-full rounded-md border p-2`}
              >
                {state.unidades.map((u) => (
                  <option key={u.unidade_id} value={u.unidade_id}>
                    {u.nome_fantasia} ({u.codigo})
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm text-slate-300">
              Papéis <span className="text-rose-400">*</span>
              <div className="flex flex-wrap gap-2 mt-1">
                {PAPIS_DISPONIVEIS.map((papel) => (
                  <Button
                    key={papel}
                    type="button"
                    variant={state.form.papeis.includes(papel) ? "default" : "outline"}
                    size="sm"
                    onClick={() => handleTogglePapel(papel)}
                  >
                    {papel}
                  </Button>
                ))}
              </div>
            </label>

            <label className="block text-sm text-slate-300">
              Unidades Permitidas <span className="text-rose-400">*</span>
              <div className="flex flex-wrap gap-2 mt-1">
                {state.unidades.map((u) => (
                  <Button
                    key={u.unidade_id}
                    type="button"
                    variant={state.form.unidades_permitidas.includes(u.unidade_id) ? "default" : "outline"}
                    size="sm"
                    onClick={() => handleToggleUnidade(u.unidade_id)}
                  >
                    {u.nome_fantasia}
                  </Button>
                ))}
              </div>
            </label>

            <label className="block text-sm text-slate-300">
              Acesso Administrativo Sensível
              <select
                value={state.form.acesso_admin_sensivel ? "true" : "false"}
                onChange={(e) => handleChange("acesso_admin_sensivel", e.target.value === "true")}
                className={`${inputClass} w-full rounded-md border p-2 mt-1`}
              >
                <option value="true">Sim</option>
                <option value="false">Não</option>
              </select>
              <p className="mt-1 text-xs text-slate-400">
                Requer permissão "permissao.gerenciar" e step-up administrativo.
              </p>
            </label>

            {state.form.acesso_admin_sensivel && (
              <label className="block text-sm text-slate-300">
                PIN Administrativo (opcional)
                <Input
                  id="admin_pin"
                  type="password"
                  value={state.form.admin_pin}
                  onChange={(e) => handleChange("admin_pin", e.target.value)}
                  placeholder="6-8 dígitos"
                  maxLength={8}
                  className={`${inputClass} w-full rounded-md border p-2 mt-1`}
                />
              </label>
            )}

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={handleCloseDialog}>
                <X className="mr-2 h-4 w-4" />
                Cancelar
              </Button>
              <Button onClick={handleSubmit} disabled={state.saving}>
                <Save className="mr-2 h-4 w-4" />
                {state.saving ? "Salvando..." : state.editing ? "Atualizar" : "Criar"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}