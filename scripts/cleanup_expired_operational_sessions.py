"""Worker independente para expurgar sessões expiradas fora do HTTP.

Executar em job/cron isolado, por exemplo:
  python -m scripts.cleanup_expired_operational_sessions

Nunca agendar no middleware, no login ou por requisição.
A expiração e revogação são validadas em tempo real no resolver.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from core.runtime import build_engine, load_runtime_settings
from infra.seguranca.modelos_orm import OperationalSessionORM

BATCH_LIMIT = 500
MAX_BATCHES = 20


def cleanup(*, batch_limit: int = BATCH_LIMIT, max_batches: int = MAX_BATCHES) -> int:
    if batch_limit < 1 or batch_limit > BATCH_LIMIT:
        raise ValueError("batch_limit_invalido")
    if max_batches < 1 or max_batches > MAX_BATCHES:
        raise ValueError("max_batches_invalido")
    engine = build_engine(load_runtime_settings())
    deleted = 0
    try:
        for _ in range(max_batches):
            with engine.begin() as conn:
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
