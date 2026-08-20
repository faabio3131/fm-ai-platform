"""Configura ou troca o PIN administrativo individual de um usuário V1.

Uso:
    python -m scripts.set_admin_pin_v1 --email dono@empresa.com

A senha de login e o PIN são lidos por getpass e nunca aparecem na linha de comando.
A senha normal autentica o titular antes da criação/troca do PIN administrativo.
"""

from __future__ import annotations

import argparse
import getpass

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.seguranca.autenticacao import ServicoAutenticacao
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

    password = getpass.getpass("Senha normal de login: ")
    pin = getpass.getpass("Novo PIN administrativo (6 a 8 digitos): ")
    confirm = getpass.getpass("Confirme o PIN administrativo: ")
    if pin != confirm:
        raise RuntimeError("os PINs nao conferem")

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = ServicoAutenticacao(repo).autenticar(
            email=args.email,
            password=password,
        )
        if identidade.tenant_id != settings.tenant_id:
            raise RuntimeError("usuario fora do tenant configurado")
        repo.definir_pin_admin(usuario_id=identidade.usuario_id, novo_pin=pin)
        session.commit()

    print(f"PIN administrativo configurado com seguranca para: {identidade.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
