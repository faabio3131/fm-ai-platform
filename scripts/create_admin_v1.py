"""Cria o primeiro administrador da V1 sem credenciais hardcoded.

Uso:
    python -m scripts.create_admin_v1 --email dono@empresa.com

Senha e PIN administrativo são lidos por getpass, nunca por argumento de linha de
comando. O banco e o escopo tenant/unidade vêm do contrato comercial de runtime.
"""

from __future__ import annotations

import argparse
import getpass

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.seguranca.permissoes import Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    load_dotenv()
    settings = load_runtime_settings()
    engine = build_engine(settings)
    health = check_database_health(engine)
    if not health.ok:
        raise RuntimeError(health.detail)
    run_migrations(engine)

    password = getpass.getpass("Senha normal do administrador: ")
    confirm = getpass.getpass("Confirme a senha normal: ")
    if password != confirm:
        raise RuntimeError("as senhas nao conferem")

    admin_pin = getpass.getpass("PIN administrativo individual (6 a 8 digitos): ")
    admin_pin_confirm = getpass.getpass("Confirme o PIN administrativo: ")
    if admin_pin != admin_pin_confirm:
        raise RuntimeError("os PINs administrativos nao conferem")

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo.criar_usuario(
            email=args.email,
            password=password,
            admin_pin=admin_pin,
            tenant_id=settings.tenant_id,
            unidade_padrao_id=settings.unidade_id,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(settings.unidade_id,),
        )
        session.commit()

    print(
        f"Administrador criado: {identidade.email} | tenant={identidade.tenant_id} | "
        f"unidade={identidade.unidade_id} | PIN administrativo configurado"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
