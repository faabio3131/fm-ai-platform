"""Benchmark isolado do custo de reflection nas leituras de catálogo/validação de venda.

PostgreSQL local efêmero obrigatório. A/B cold-vs-warm no MESMO Engine.
Não mede a transação integral de venda, apenas os SQLs da ponte legada.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from infra.legacy_product_scope import (
    invalidar_cache_reflexao_legada,
    listar_produtos_legados,
    obter_produto_por_id_legado,
)
from migrations.runner import run_migrations


def _medir(engine, factory, action):
    sql: list[str] = []

    def registrar(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)

    event.listen(engine, "before_cursor_execute", registrar)
    start = time.perf_counter()
    try:
        with factory() as session:
            result = action(session)
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        event.remove(engine, "before_cursor_execute", registrar)
    return result, len(sql), round(duration_ms, 3)


def _fase(engine, factory, name, action):
    invalidar_cache_reflexao_legada(engine)
    first, cold_queries, cold_ms = _medir(engine, factory, action)
    repeated = [_medir(engine, factory, action) for _ in range(15)]
    warm_queries = [item[1] for item in repeated]
    warm_ms = [item[2] for item in repeated]
    if cold_queries <= max(warm_queries):
        raise AssertionError(f"no metadata SQL reduction: {name}")
    if min(warm_queries) != max(warm_queries):
        raise AssertionError(f"unstable warm SQL count: {name}")
    if len(first) == 0:
        raise AssertionError(f"empty result: {name}")
    return {
        "operation": name,
        "cold_sql": cold_queries,
        "warm_sql": warm_queries[0],
        "saved_sql_per_request_after_warmup": cold_queries - warm_queries[0],
        "cold_ms": cold_ms,
        "warm_ms_median": round(statistics.median(warm_ms), 3),
        "warm_samples": len(warm_ms),
    }


def main():
    uri = os.environ["DATABASE_URL"]
    if not uri.startswith("postgresql") or "127.0.0.1" not in uri:
        raise RuntimeError("Benchmark exclusivo em PostgreSQL efêmero localhost")
    engine = create_engine(uri, pool_size=10, max_overflow=10, pool_timeout=8)
    try:
        run_migrations(engine)
        with engine.begin() as conn:
            loja_id = conn.execute(
                text(
                    "INSERT INTO lojas (nome_fantasia) "
                    "VALUES ('Benchmark isolado') RETURNING id"
                )
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO fm_unidade_loja_legacy_v1 "
                    "(tenant_id, unidade_id, loja_id, ativo) "
                    "VALUES ('cache-tenant', 'cache-unit', :loja, TRUE)"
                ),
                {"loja": loja_id},
            )
            produto_id = conn.execute(
                text(
                    "INSERT INTO produtos (nome, categoria, preco_venda, loja_id) "
                    "VALUES ('Produto benchmark', 'Teste', 23.5, :loja) RETURNING id"
                ),
                {"loja": str(loja_id)},
            ).scalar_one()
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": "isolated PostgreSQL",
            "external_provider_calls": 0,
            "production_requests": 0,
            "scope": "legacy structural reflection only (not entire API or sale)",
            "operations": [
                _fase(
                    engine, factory, "catalog_list",
                    lambda session: listar_produtos_legados(
                        session, tenant_id="cache-tenant", unidade_id="cache-unit"
                    ),
                ),
                _fase(
                    engine, factory, "product_sale_lookup",
                    lambda session: [
                        obter_produto_por_id_legado(
                            session, tenant_id="cache-tenant",
                            unidade_id="cache-unit", produto_id=int(produto_id)
                        )
                    ],
                ),
            ],
        }
        path = Path("evidence/kordena-legacy-reflection-pg16.json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print("LEGACY_REFLECTION_BENCH " + json.dumps(report, sort_keys=True))
    finally:
        invalidar_cache_reflexao_legada(engine)
        engine.dispose()


if __name__ == "__main__":
    main()
