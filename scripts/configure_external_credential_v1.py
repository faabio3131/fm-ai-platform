"""Registra uma referência de credencial externa sem receber segredo por argumento.

Exemplo:
    export MAPS_SERVER_KEY='<valor real>'
    python -m scripts.configure_external_credential_v1 \
      --admin-email dono@empresa.com \
      --provider google_maps \
      --purpose maps_server_api_key \
      --secret-env MAPS_SERVER_KEY
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
from migrations.runner import assert_schema_current


def _contexto(identidade, *, tenant_id: str, unidade_id: str) -> ContextoExecucao:
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
        origem="cli-configure-external-credential",
        unidades_permitidas=identidade.unidades_permitidas,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Registra referência segura de uma credencial externa."
    )
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument(
        "--secret-env",
        required=True,
        help="Nome da variável de ambiente que contém o segredo; nunca o valor.",
    )
    args = parser.parse_args()

    settings = load_runtime_settings()
    engine = build_engine(settings)
    health = check_database_health(engine)
    if not health.ok:
        raise RuntimeError(health.detail)
    # Migration real é um gate separado; este comando nunca a aplica implicitamente.
    assert_schema_current(engine)

    secret_store = ReferenceSecretStore()
    referencia = env_reference(args.secret_env)
    secret_store.resolve(referencia)
    factory = build_session_factory(engine=engine, commercial=settings.commercial)
    password = getpass.getpass("Senha do administrador: ")

    with factory() as session:
        identidade = ServicoAutenticacao(
            RepositorioIdentidadesSQLAlchemy(session)
        ).autenticar(email=args.admin_email, password=password)
        contexto = _contexto(
            identidade,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )
        credencial = ServicoCredenciaisReferenciadas(
            session, secret_store
        ).rotacionar(
            contexto=contexto,
            provedor=args.provider,
            finalidade=args.purpose,
            nova_referencia=referencia,
        )
        session.commit()

    print(
        "Referência configurada com sucesso | "
        f"tenant={settings.tenant_id} | unidade={settings.unidade_id} | "
        f"provedor={credencial.provedor} | finalidade={credencial.finalidade} | "
        f"versao={credencial.versao}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
