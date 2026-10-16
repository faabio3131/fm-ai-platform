"""Worker independente para expurgar sessões expiradas fora do HTTP.

Executar em job/cron isolado, por exemplo:
  python -m scripts.cleanup_expired_operational_sessions

Nunca agendar no middleware, no login ou por requisição.
A expiração e revogação são validadas em tempo real no resolver.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import delete, select, text

from core.runtime import build_engine, load_runtime_settings
from infra.seguranca.modelos_orm import OperationalSessionORM

BATCH_LIMIT = 500
MAX_BATCHES = 20
ROLE_NAME = "fm_session_cleanup_v1"


def verify_database_role(engine) -> None:
    """Falha fechada se a conexão do job tiver autoridade de aplicação/admin.

    Na execução real o job opera exclusivamente no PostgreSQL. Testes locais
    SQLite mantêm a verificação de TTL, mas não substituem o gate PostgreSQL.
    """
    if engine.dialect.name != "postgresql":
        if os.getenv("FM_AI_ENV", "").lower() in {"staging", "production"}:
            raise RuntimeError("session_cleanup.postgresql_required")
        return

    with engine.connect() as conn:
        actual = conn.execute(text("""
            SELECT current_user AS principal,
                   rolsuper, rolcreaterole, rolcreatedb, rolreplication,
                   has_schema_privilege(current_user, 'public', 'CREATE')
                       AS can_create_schema_objects,
                   has_column_privilege(current_user,
                       'public.fm_operational_sessions_v1',
                       'session_id', 'SELECT') AS can_read_id,
                   has_column_privilege(current_user,
                       'public.fm_operational_sessions_v1',
                       'expira_em', 'SELECT') AS can_read_expiry,
                   has_table_privilege(current_user,
                       'public.fm_operational_sessions_v1',
                       'DELETE') AS can_delete_sessions,
                   has_table_privilege(current_user,
                       'public.fm_operational_sessions_v1',
                       'INSERT,UPDATE,TRUNCATE,REFERENCES,TRIGGER')
                       AS can_mutate_other,
                   has_table_privilege(current_user,
                       'public.fm_usuarios_v1',
                       'SELECT,INSERT,UPDATE,DELETE')
                       AS can_access_users
              FROM pg_roles WHERE rolname = current_user
        """)).mappings().one()
    if (
        actual["principal"] != ROLE_NAME
        or actual["rolsuper"] or actual["rolcreaterole"]
        or actual["rolcreatedb"] or actual["rolreplication"]
        or actual["can_create_schema_objects"]
        or not actual["can_read_id"] or not actual["can_read_expiry"]
        or not actual["can_delete_sessions"]
        or actual["can_mutate_other"] or actual["can_access_users"]
    ):
        raise RuntimeError("session_cleanup.database_role_not_least_privilege")


def cleanup(*, batch_limit: int = BATCH_LIMIT, max_batches: int = MAX_BATCHES) -> int:
    if batch_limit < 1 or batch_limit > BATCH_LIMIT:
        raise ValueError("batch_limit_invalido")
    if max_batches < 1 or max_batches > MAX_BATCHES:
        raise ValueError("max_batches_invalido")
    engine = build_engine(load_runtime_settings())
    deleted = 0
    try:
        verify_database_role(engine)
        for _ in range(max_batches):
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("SET LOCAL lock_timeout = '2000ms'"))
                    conn.execute(text("SET LOCAL statement_timeout = '15000ms'"))
                expiradas = (
                    select(OperationalSessionORM.session_id)
                    .where(OperationalSessionORM.expira_em <= datetime.now(UTC))
                    .order_by(OperationalSessionORM.expira_em)
                    .limit(batch_limit)
                )
                result = conn.execute(
                    delete(OperationalSessionORM).where(
                        OperationalSessionORM.session_id.in_(expiradas)
                    )
                )
                count = result.rowcount
            if not count:
                break
            deleted += count
            if count < batch_limit:
                break
        return deleted
    finally:
        engine.dispose()


if __name__ == "__main__":
    # Não imprimir session_id ou outros dados identificáveis nos logs.
    print(f"expired_sessions_deleted={cleanup()}")
