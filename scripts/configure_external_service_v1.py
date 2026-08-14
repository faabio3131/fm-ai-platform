"""Configura e consulta serviços externos por tenant/unidade autenticados."""

from __future__ import annotations

import argparse
import getpass
from datetime import datetime, timezone
from uuid import uuid4

from core.integracoes import AmbienteIntegracao, ServicoConfiguracoesExternas
from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.seguranca.auditoria import RepositorioAuditoria
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.session_guard import build_session_factory
from migrations.runner import assert_schema_current


def _pares(valores: list[str], nome: str) -> dict[str, str]:
    resultado: dict[str, str] = {}
    for item in valores:
        chave, separador, valor = item.partition("=")
        if not separador or not chave.strip() or not valor.strip():
            raise ValueError(f"{nome} deve usar chave=valor")
        if chave.strip() in resultado:
            raise ValueError(f"{nome} duplicado: {chave.strip()}")
        resultado[chave.strip()] = valor.strip()
    return resultado


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
        origem="cli-configure-external-service",
        unidades_permitidas=identidade.unidades_permitidas,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control plane seguro para serviços externos da V1."
    )
    parser.add_argument("--admin-email", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    configurar = subparsers.add_parser("configure")
    configurar.add_argument("--config-id", required=True)
    configurar.add_argument("--service", required=True)
    configurar.add_argument("--provider", required=True)
    configurar.add_argument("--external-account", required=True)
    configurar.add_argument(
        "--environment",
        choices=[item.value for item in AmbienteIntegracao],
        default=AmbienteIntegracao.HOMOLOGACAO.value,
    )
    configurar.add_argument("--param", action="append", default=[])
    configurar.add_argument("--credential", action="append", default=[])
    configurar.add_argument("--enable", action="store_true")
    configurar.add_argument("--expected-version", type=int, default=0)

    status = subparsers.add_parser("status")
    status.add_argument("--config-id", required=True)

    homologar = subparsers.add_parser("homologate")
    homologar.add_argument("--config-id", required=True)
    homologar.add_argument("--evidence-ref", required=True)
    homologar.add_argument("--expected-version", type=int, required=True)
    return parser


def _servico(session, auditoria: RepositorioAuditoria) -> ServicoConfiguracoesExternas:
    return ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(
            session, ReferenceSecretStore()
        ),
        auditoria=auditoria,
    )


def main() -> int:
    args = _parser().parse_args()
    settings = load_runtime_settings()
    engine = build_engine(settings)
    health = check_database_health(engine)
    if not health.ok:
        raise RuntimeError(health.detail)
    # Migration real é um gate separado; este comando nunca a aplica implicitamente.
    assert_schema_current(engine)
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
        servico = _servico(session, RepositorioAuditoriaSQLAlchemy(session))

        if args.command == "configure":
            configuracao = servico.configurar(
                contexto=contexto,
                configuracao_id=args.config_id,
                servico=args.service,
                provedor=args.provider,
                conta_externa=args.external_account,
                ambiente=AmbienteIntegracao(args.environment),
                parametros_publicos=_pares(args.param, "param"),
                finalidades_credenciais=_pares(args.credential, "credential"),
                habilitada=args.enable,
                versao_esperada=args.expected_version,
            )
            session.commit()
            print(
                f"Configuração salva | id={configuracao.configuracao_id} | "
                f"versao={configuracao.versao}"
            )
        elif args.command == "homologate":
            configuracao = servico.registrar_homologacao(
                contexto=contexto,
                configuracao_id=args.config_id,
                evidencia_ref=args.evidence_ref,
                versao_esperada=args.expected_version,
            )
            session.commit()
            print(
                f"Homologação registrada | id={configuracao.configuracao_id} | "
                f"versao={configuracao.versao}"
            )
        else:
            status = servico.avaliar(
                contexto=contexto, configuracao_id=args.config_id
            )
            print(
                f"Estado={status.estado.value} | "
                f"faltam_parametros={','.join(status.faltam_parametros) or '-'} | "
                f"faltam_finalidades={','.join(status.faltam_finalidades) or '-'} | "
                f"faltam_credenciais={','.join(status.faltam_credenciais) or '-'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
