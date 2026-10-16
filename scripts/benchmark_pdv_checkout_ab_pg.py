"""A/B do checkout HTTP integral: catálogo varrido vs busca scoped por IDs.

Banco PostgreSQL 16 local descartável, credenciais de homologação isoladas.
Sem pagamentos externos, IA paga, dados de clientes ou tráfego de produção.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from http_api.frontend_app import build_frontend_http_app
import http_api.pdv as pdv_api
from infra.legacy_product_scope import listar_produtos_legados as scoped_legacy_list
from migrations.runner import run_migrations
from scripts.kca15_internal_homologation import (
    EMAIL,
    LOJA_ID,
    _create_internal_commercial_state,
    _ensure_legacy_scope_and_identity,
)


def _medir(client, engine, produto_id, *, n=5):
    samples: list[dict] = []

    def registrar(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    for i in range(n):
        queries: list[str] = []
        event.listen(engine, "before_cursor_execute", registrar)
        start = time.perf_counter()
        try:
            resp = client.post(
                "/v1/pdv/checkout",
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "itens": [{"produto_id": produto_id, "quantidade": 1}],
                    "metodo_pagamento": "dinheiro",
                    "desconto": "0.00",
                },
            )
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            event.remove(engine, "before_cursor_execute", registrar)
        if resp.status_code != 201:
            raise AssertionError(
                f"checkout HTTP {resp.status_code}: {resp.text[:180]}"
            )
        produto_sql = [
            query for query in queries
            if "SELECT" in query and "FROM produtos" in query
        ]
        if len(produto_sql) != 1:
            raise AssertionError(f"Expected one product SELECT, got {len(produto_sql)}")
        samples.append({
            "elapsed_ms": round(elapsed, 3),
            "sql_count": len(queries),
            "product_scoped_by_id": "produtos.id IN" in produto_sql[0],
            "total": resp.json()["comanda"]["total"],
        })
    return {
        "samples": len(samples),
        "sql_count": [s["sql_count"] for s in samples],
        "median_ms": round(statistics.median(s["elapsed_ms"] for s in samples), 3),
        "p95_ms_sample": round(sorted(s["elapsed_ms"] for s in samples)[-1], 3),
        "product_sql_scoped": all(s["product_scoped_by_id"] for s in samples),
        "totals": sorted({s["total"] for s in samples}),
    }


def main() -> None:
    url = os.environ["DATABASE_URL"]
    if not url.startswith("postgresql") or "127.0.0.1" not in url:
        raise RuntimeError("Only disposable localhost PostgreSQL is allowed")
    password = os.environ["KCA15_INTERNAL_PASSWORD"]
    engine = create_engine(url, pool_size=10, max_overflow=10, pool_timeout=8)
    try:
        run_migrations(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        _create_internal_commercial_state(factory)
        _ensure_legacy_scope_and_identity(factory, password)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO produtos "
                    "(nome, categoria, preco_venda, loja_id, ativo) "
                    "VALUES (:name, 'CargaTeste', 30.0, :loja, TRUE)"
                ),
                [
                    {"name": f"Checkout A/B {i}", "loja": str(LOJA_ID)}
                    for i in range(1200)
                ],
            )

        config = RuntimeSettings(
            environment=RuntimeEnvironment.STAGING,
            database_url=url,
            tenant_id="batch-checkout-bootstrap",
            unidade_id="batch-checkout-bootstrap",
            commercial_access_gate_enabled=True,
            fmcc_control_plane_token=os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"],
        ).validate()
        app = build_frontend_http_app(
            settings=config,
            engine=engine,
            session_factory=factory,
            commercial_access_gate_enabled=True,
        )
        client = TestClient(app, base_url="https://checkout-benchmark.local")
        login = client.post(
            "/v1/auth/login", json={"email": EMAIL, "senha": password}
        )
        if login.status_code != 200:
            raise RuntimeError(f"login failed: {login.status_code}")
        catalog = client.get("/v1/pdv/produtos")
        if catalog.status_code != 200:
            raise RuntimeError(f"catalog failed: {catalog.status_code}")
        product = next(
            row for row in catalog.json()["produtos"]
            if row["nome"] == "Produto KCA-15"
        )
        identity = product["id"]

        def baseline_unfiltered(session, *, tenant_id, unidade_id, produto_ids=None):
            return scoped_legacy_list(
                session, tenant_id=tenant_id, unidade_id=unidade_id
            )

        # Mesma build, mesmo banco e mesmo caminho HTTP; única diferença é
        # retirar o predicado de ID do catálogo para reproduzir a versão antiga.
        pdv_api.listar_produtos_legados = baseline_unfiltered
        try:
            baseline = _medir(client, engine, identity)
        finally:
            pdv_api.listar_produtos_legados = scoped_legacy_list
        optimized = _medir(client, engine, identity)
        if baseline["product_sql_scoped"] or not optimized["product_sql_scoped"]:
            raise AssertionError("A/B did not isolate the intended query")
        if baseline["totals"] != optimized["totals"]:
            raise AssertionError("checkout financial result changed")
        report = {
            "captured_at": datetime.now(UTC).isoformat(),
            "environment": "ephemeral PostgreSQL 16 / FastAPI TestClient",
            "catalog_extra_products": 1200,
            "actual_sale_with_payment": True,
            "provider_real_calls": 0,
            "commercial_customers": 0,
            "baseline_full_catalog": baseline,
            "scoped_ids": optimized,
            "limitations": [
                "A/B phases sequential, not randomized under concurrent load",
                "GitHub CI sizing is not Railway performance",
                "Both paths still incur authentication and checkout SQL",
            ],
        }
        path = Path("evidence/kordena-pdv-checkout-ab-pg16.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print("PDV_CHECKOUT_AB " + json.dumps(report, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
