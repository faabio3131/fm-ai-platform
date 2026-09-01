"""Reconcilia explicitamente uma loja legada antes da migration 0027."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Mapping, Sequence

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from application.legacy_store_reconciliation import (
    ErroReconciliacaoLojaLegada,
    SolicitacaoReconciliacaoLoja,
    reconciliar_loja_legada,
)
from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.erros import ErroSeguranca
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

_REQUIRED_ENV = (
    "FM_AI_ENV",
    "DATABASE_URL",
    "FM_AI_TENANT_ID",
    "FM_AI_UNIDADE_ID",
)
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_LOCAL_DATABASE_DEFAULT = "sqlite:///./banco_erp_local.db"
_LOCAL_SCOPE_DEFAULTS = frozenset({"tenant-local", "unidade-local"})


class ErroConfiguracaoReconciliacao(RuntimeError):
    """Configuração explícita do comando está ausente ou insegura."""


def _exigir_ambiente_explicito(environ: Mapping[str, str]) -> None:
    ausentes = [chave for chave in _REQUIRED_ENV if not environ.get(chave, "").strip()]
    if ausentes:
        raise ErroConfiguracaoReconciliacao("configuração obrigatória ausente")

    ambiente = environ["FM_AI_ENV"].strip().casefold()
    if ambiente in {"test", "testing"}:
        raise ErroConfiguracaoReconciliacao("ambiente não autorizado")
    if environ.get("FM_AI_TEST_MODE", "").strip().casefold() in _TRUTHY:
        raise ErroConfiguracaoReconciliacao("modo de teste não autorizado")

    database_url = environ["DATABASE_URL"].strip()
    if database_url.casefold() == _LOCAL_DATABASE_DEFAULT:
        raise ErroConfiguracaoReconciliacao("fallback local não autorizado")
    if (
        environ["FM_AI_TENANT_ID"].strip().casefold() in _LOCAL_SCOPE_DEFAULTS
        or environ["FM_AI_UNIDADE_ID"].strip().casefold() in _LOCAL_SCOPE_DEFAULTS
    ):
        raise ErroConfiguracaoReconciliacao("escopo local padrão não autorizado")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconciliação governada de ownership da loja legada."
    )
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--unidade-id", required=True)
    parser.add_argument("--loja-id", required=True, type=int)
    parser.add_argument("--loja-nome")
    return parser


def _executar(args: argparse.Namespace, engine: Engine) -> tuple[str, str]:
    password = getpass.getpass("Senha do administrador: ")
    with Session(engine) as session:
        identidade = ServicoAutenticacao(
            RepositorioIdentidadesSQLAlchemy(session)
        ).autenticar(email=args.admin_email, password=password)

    resultado = reconciliar_loja_legada(
        engine,
        SolicitacaoReconciliacaoLoja(
            tenant_id=args.tenant_id,
            unidade_id=args.unidade_id,
            loja_id=args.loja_id,
            loja_nome=args.loja_nome,
        ),
        identidade=identidade,
    )
    return resultado.estado, resultado.correlation_id


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine: Engine | None = None
    try:
        _exigir_ambiente_explicito(os.environ)
        settings = load_runtime_settings()
        if (
            args.tenant_id.strip() != settings.tenant_id
            or args.unidade_id.strip() != settings.unidade_id
        ):
            raise ErroConfiguracaoReconciliacao("escopo divergente")

        engine = build_engine(settings)
        health = check_database_health(engine)
        if not health.ok:
            raise ErroConfiguracaoReconciliacao("banco indisponível")

        estado, correlation_id = _executar(args, engine)
        print(
            "Reconciliação concluída | "
            f"estado={estado} | correlation_id={correlation_id}"
        )
        return 0
    except ErroConfiguracaoReconciliacao:
        print("Reconciliação negada: configuração insegura ou incompleta.", file=sys.stderr)
        return 2
    except (ErroSeguranca, ErroReconciliacaoLojaLegada):
        print("Reconciliação negada: autenticação, autorização ou estado inválido.", file=sys.stderr)
        return 3
    except SQLAlchemyError:
        print("Reconciliação indisponível por erro de persistência.", file=sys.stderr)
        return 4
    except (OSError, RuntimeError, ValueError):
        print("Reconciliação não concluída.", file=sys.stderr)
        return 5
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
