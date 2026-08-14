"""Configura a referência do token PagBank sem receber o segredo por argumento.

Exemplo seguro:
    set PAGBANK_TOKEN=<segredo no ambiente local>
    python -m scripts.configure_pagbank_v1 --admin-email dono@empresa.com

O comando autentica um usuário real, exige ``integracao.gerenciar`` e grava apenas
``env:PAGBANK_TOKEN`` no banco. O valor do token nunca é impresso nem persistido.
"""

from __future__ import annotations

import argparse
import getpass
from datetime import datetime, timezone
from uuid import uuid4

from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import ReferenceSecretStore, env_reference
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.session_guard import build_session_factory
from migrations.runner import run_migrations


def _contexto_operador(identidade, *, tenant_id: str, unidade_id: str) -> ContextoExecucao:
    if identidade.tenant_id != tenant_id or unidade_id not in identidade.unidades_permitidas:
        raise RuntimeError("administrador fora do escopo tenant/unidade do runtime")
    if Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes:
        raise RuntimeError("usuario autenticado nao pode gerenciar integracoes")
    return ContextoExecucao(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id=identidade.usuario_id,
        papeis=identidade.papeis,
        permissoes=identidade.permissoes,
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
        origem="cli-configure-pagbank",
        unidades_permitidas=identidade.unidades_permitidas,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Registra referência segura do token PagBank para a unidade atual."
    )
    parser.add_argument("--admin-email", required=True)
    parser.add_argument(
        "--secret-env",
        default="PAGBANK_TOKEN",
        help="Nome da variável de ambiente que contém o token; nunca o valor.",
    )
    args = parser.parse_args()

    settings = load_runtime_settings()
    engine = build_engine(settings)
    health = check_database_health(engine)
    if not health.ok:
        raise RuntimeError(health.detail)
    run_migrations(engine)

    secret_store = ReferenceSecretStore()
    referencia = env_reference(args.secret_env)
    # Falha antes de autenticar/persistir se a variável não existir ou estiver vazia.
    secret_store.resolve(referencia)

    factory = build_session_factory(engine=engine, commercial=settings.commercial)
    password = getpass.getpass("Senha do administrador: ")

    with factory() as session:
        repo_identidades = RepositorioIdentidadesSQLAlchemy(session)
        identidade = ServicoAutenticacao(repo_identidades).autenticar(
            email=args.admin_email,
            password=password,
        )
        contexto = _contexto_operador(
            identidade,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )
        credencial = ServicoCredenciaisReferenciadas(session, secret_store).rotacionar(
            contexto=contexto,
            provedor="pagbank",
            finalidade="api_token",
            nova_referencia=referencia,
        )
        session.commit()

    print(
        "Referência PagBank configurada com sucesso | "
        f"tenant={settings.tenant_id} | unidade={settings.unidade_id} | "
        f"referencia={credencial.referencia} | versao={credencial.versao}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
