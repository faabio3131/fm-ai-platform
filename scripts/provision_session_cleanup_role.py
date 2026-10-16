"""Provisionamento único, governado, da identidade PostgreSQL para o Cron.

Uso autorizado, uma vez, com segredo forte em variável de ambiente:
    FM_AI_SESSION_CLEANUP_PASSWORD=... \
    python -m scripts.provision_session_cleanup_role --provision

Requer DATABASE_URL administrativo para esta execução SOMENTE. Nunca compartilhar
este DATABASE_URL com o serviço Cron. Não imprime URLs, senhas ou IDs de sessão.
"""
from __future__ import annotations

import argparse
import os

from psycopg import Error, connect, sql

from core.runtime import load_runtime_settings
from scripts.cleanup_expired_operational_sessions import ROLE_NAME


def provision(*, admin_url: str, password: str) -> None:
    if len(password) < 40:
        raise RuntimeError("session_cleanup.secret_too_short")
    if not admin_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        raise RuntimeError("session_cleanup.postgresql_required")
    uri = admin_url.replace("postgresql+psycopg://", "postgresql://", 1)

    try:
        with connect(uri) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", (ROLE_NAME,))
            if cursor.fetchone()[0]:
                raise RuntimeError("session_cleanup.role_already_exists_do_not_rotate_implicitly")
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOINHERIT PASSWORD {} CONNECTION LIMIT 2"
                ).format(sql.Identifier(ROLE_NAME), sql.Literal(password))
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(connection.info.dbname), sql.Identifier(ROLE_NAME)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(ROLE_NAME)
                )
            )
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT (session_id, expira_em), DELETE "
                    "ON TABLE public.fm_operational_sessions_v1 TO {}"
                ).format(sql.Identifier(ROLE_NAME))
            )
            cursor.execute(
                sql.SQL("ALTER ROLE {} SET statement_timeout = '15s'").format(
                    sql.Identifier(ROLE_NAME)
                )
            )
            cursor.execute(
                sql.SQL("ALTER ROLE {} SET lock_timeout = '2s'").format(
                    sql.Identifier(ROLE_NAME)
                )
            )
        print("cleanup_role.provisioned_with_minimum_table_grants")
    except RuntimeError:
        raise
    except Error:
        raise RuntimeError("session_cleanup.provision_failed_check_technical_logs_privately") from None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provision", action="store_true")
    args = parser.parse_args()
    if not args.provision:
        raise RuntimeError("session_cleanup.explicit_provision_flag_required")
    password = os.environ.get("FM_AI_SESSION_CLEANUP_PASSWORD", "")
    provision(admin_url=load_runtime_settings().database_url, password=password)


if __name__ == "__main__":
    main()
