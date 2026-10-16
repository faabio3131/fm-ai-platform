"""Diagnóstico auditável de cada comando SQL do checkout PDV completo.

Somente PostgreSQL local descartável, dados sintéticos e provedor externo desligado.
Captura assinatura SQL e origem do call stack, nunca parâmetros nem credenciais.
Não altera código de produção ou efeitos financeiros.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from http_api.frontend_app import build_frontend_http_app
from migrations.runner import run_migrations
from scripts.kca15_internal_homologation import (
    EMAIL,
    _create_internal_commercial_state,
    _ensure_legacy_scope_and_identity,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("evidence/kordena-pdv-sql-70-attribution-pg16.json")
APPLICATION_ROOTS = ("http_api/", "application/", "core/", "infra/")


def _origem():
    frames = []
    frame = sys._getframe(1)
    while frame is not None:
        try:
            rel = Path(frame.f_code.co_filename).resolve().relative_to(ROOT)
            path = rel.as_posix()
            if path.startswith(APPLICATION_ROOTS):
                frames.append(f"{path}:{frame.f_code.co_name}:{frame.f_lineno}")
        except ValueError:
            pass
        frame = frame.f_back
    return frames


def _fase(frames):
    stack = "\n".join(frames)
    if "http_api/pdv.py:_montar_pedido:" in stack:
        return "02_montagem_catalogo_precheckout"
    if "application/checkout.py:executar_checkout_v1:" in stack:
        return "03_checkout_transacional"
    if "http_api/pdv.py:_contexto_pdv:" in stack:
        return "01_autorizacao_rota_pdv"
    if "http_api/pdv.py:_resposta_checkout:" in stack:
        return "04_montagem_resposta"
    if "http_api/frontend_app.py:commercial_access_gate:" in stack:
        return "00_gate_comercial_middleware"
    return "99_outros"


def _objeto_sql(sql):
    match = re.search(
        r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+[\"']?([a-zA-Z_][a-zA-Z_0-9.]*)",
        sql, flags=re.IGNORECASE,
    )
    return match.group(1).lower().replace('"', "") if match else "(controle/sem_tabela)"


def _categoria(frames, tabela, sql):
    stack = "\n".join(frames)
    if "http_api/auth.py:_limpar_expiradas_db:" in stack:
        return "autenticacao_limpeza_sessoes"
    if "http_api/auth.py:" in stack or "infra/seguranca/adaptador_sqlalchemy.py:" in stack:
        return "autenticacao_sessao_identidade"
    if "commercial_access" in stack or "comercial" in tabela or "entitlement" in tabela:
        return "gate_entitlement_comercial"
    if tabela == "fm_unidade_loja_legacy_v1" or "legacy_product_scope.py:resolver_loja_id_legada" in stack:
        return "catalogo_resolucao_escopo"
    if tabela == "produtos":
        return "catalogo_produtos"
    if "outbox" in tabela or "outbox" in stack:
        return "outbox_eventos"
    if "auditoria" in tabela or "auditoria" in stack:
        return "auditoria"
    if "pagament" in tabela or "/pagamentos/" in stack:
        return "pagamento"
    if "pedido" in tabela or "/pedidos/" in stack:
        return "pedido"
    if "pdv" in tabela:
        return "pdv_integracao"
    if "catalog" in stack or "legacy" in stack:
        return "catalogo_outros"
    return "outros_exigir_inspecao"


def _comando(sql):
    start = sql.lstrip().upper()
    for command in ("SELECT", "INSERT", "UPDATE", "DELETE", "SAVEPOINT", "RELEASE"):
        if start.startswith(command):
            return command
    return start.split(None, 1)[0] if start else "UNKNOWN"


def _coletar_requisicao(client, engine, produto_id, *, key):
    entries = []
    times = {}

    def before(conn, cursor, statement, parameters, context, executemany):
        frames = _origem()
        table = _objeto_sql(statement)
        signature = " ".join(statement.split())
        digest = hashlib.sha256(signature.encode()).hexdigest()[:14]
        entries.append({
            "index": len(entries) + 1,
            "verb": _comando(statement),
            "table": table,
            "phase": _fase(frames),
            "category": _categoria(frames, table, statement),
            "caller": frames[0] if frames else "(sem_codigo_app)",
            "trace": frames[:10],
            "fingerprint": digest,
            "sql_ms": None,
        })
        times[id(context)] = time.perf_counter()

    def after(conn, cursor, statement, parameters, context, executemany):
        start = times.pop(id(context), None)
        if start is not None and entries:
            entries[-1]["sql_ms"] = round(
                (time.perf_counter() - start) * 1000, 3
            )

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)
    start = time.perf_counter()
    try:
        response = client.post(
            "/v1/pdv/checkout",
            headers={"Idempotency-Key": key},
            json={
                "itens": [{"produto_id": produto_id, "quantidade": 1}],
                "metodo_pagamento": "dinheiro",
                "desconto": "0.00",
            },
        )
    finally:
        duration = round((time.perf_counter() - start) * 1000, 3)
        event.remove(engine, "before_cursor_execute", before)
        event.remove(engine, "after_cursor_execute", after)
    if response.status_code not in (200, 201):
        raise AssertionError(f"Checkout HTTP {response.status_code}: {response.text[:180]}")
    return {
        "http": response.status_code,
        "duration_ms": duration,
        "sql_count": len(entries),
        "total": response.json()["comanda"]["total"],
        "pedido_id": response.json()["comanda"]["pedido_id"],
        "idempotente": response.json()["idempotente"],
        "phase_count": dict(sorted(Counter(e["phase"] for e in entries).items())),
        "category_count": dict(sorted(Counter(e["category"] for e in entries).items())),
        "command_count": dict(sorted(Counter(e["verb"] for e in entries).items())),
        "tables": dict(sorted(Counter(e["table"] for e in entries).items())),
        "entries": entries,
    }


def _resumir(samples):
    return {
        "count": len(samples),
        "sql_per_request": [r["sql_count"] for r in samples],
        "sql_median": statistics.median(r["sql_count"] for r in samples),
        "duration_ms": [r["duration_ms"] for r in samples],
        "duration_ms_median_with_trace_overhead": round(
            statistics.median(r["duration_ms"] for r in samples), 3
        ),
        "category_medians": {
            key: statistics.median(r["category_count"].get(key, 0) for r in samples)
            for key in sorted(set().union(*(r["category_count"] for r in samples)))
        },
        "phase_medians": {
            key: statistics.median(r["phase_count"].get(key, 0) for r in samples)
            for key in sorted(set().union(*(r["phase_count"] for r in samples)))
        },
    }


def _repetidas(sale):
    groups = defaultdict(list)
    for row in sale["entries"]:
        groups[(row["fingerprint"], row["table"], row["category"])].append(row)
    result = [
        {
            "fingerprint": key[0],
            "table": key[1],
            "category": key[2],
            "count": len(rows),
            "verb": rows[0]["verb"],
            "example_caller": rows[0]["caller"],
            "indices": [row["index"] for row in rows],
        }
        for key, rows in groups.items()
    ]
    return sorted(result, key=lambda row: (-row["count"], row["table"], row["fingerprint"]))


def main():
    uri = os.environ["DATABASE_URL"]
    if not uri.startswith("postgresql") or "127.0.0.1" not in uri:
        raise RuntimeError("Somente PostgreSQL descartavel local")
    password = os.environ["KCA15_INTERNAL_PASSWORD"]
    engine = create_engine(uri, pool_size=10, max_overflow=10, pool_timeout=8)
    try:
        run_migrations(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        _create_internal_commercial_state(factory)
        _ensure_legacy_scope_and_identity(factory, password)
        settings = RuntimeSettings(
            environment=RuntimeEnvironment.STAGING,
            database_url=uri,
            tenant_id="pdv-profiler-bootstrap",
            unidade_id="pdv-profiler-bootstrap",
            commercial_access_gate_enabled=True,
            fmcc_control_plane_token=os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"],
        ).validate()
        app = build_frontend_http_app(
            settings=settings, engine=engine, session_factory=factory,
            commercial_access_gate_enabled=True,
        )
        client = TestClient(app, base_url="https://pdv-profiler.local")
        login = client.post("/v1/auth/login", json={"email": EMAIL, "senha": password})
        assert login.status_code == 200, f"login failed {login.status_code}"
        catalog = client.get("/v1/pdv/produtos")
        assert catalog.status_code == 200, f"catalog failed {catalog.status_code}"
        product = next(
            row for row in catalog.json()["produtos"] if row["nome"] == "Produto KCA-15"
        )

        # Aquecer metadata e path de auth antes das amostras.
        warm = _coletar_requisicao(
            client, engine, product["id"], key=str(uuid4())
        )
        new_sales = [
            _coletar_requisicao(client, engine, product["id"], key=str(uuid4()))
            for _ in range(3)
        ]
        replay_key = str(uuid4())
        original = _coletar_requisicao(client, engine, product["id"], key=replay_key)
        repeated = _coletar_requisicao(client, engine, product["id"], key=replay_key)
        assert original["http"] == 201 and repeated["http"] == 200
        assert repeated["idempotente"]
        assert original["pedido_id"] == repeated["pedido_id"]
        assert all(x["http"] == 201 and x["total"] == original["total"] for x in new_sales)

        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "env": "PostgreSQL16 CI ephemeral; no customer data; no external calls",
            "method": "SQLAlchemy before/after_cursor_execute + Python callstacks",
            "note": (
                "Stack instrumentation inflates elapsed wall time. "
                "SQL params are never logged. Aggregate attribution may contain "
                "'outros_exigir_inspecao' until code owners review."
            ),
            "warmup_sql_count": warm["sql_count"],
            "new_sales": _resumir(new_sales),
            "replay": {
                "first_sql_count": original["sql_count"],
                "second_sql_count": repeated["sql_count"],
                "same_order": original["pedido_id"] == repeated["pedido_id"],
                "second_idempotent": repeated["idempotente"],
                "second_category_count": repeated["category_count"],
                "second_phase_count": repeated["phase_count"],
            },
            "top_repeated_sql": _repetidas(new_sales[0])[:35],
            "full_new_sale_trace": new_sales[0]["entries"],
            "full_replay_trace": repeated["entries"],
        }
        OUTPUT.parent.mkdir(exist_ok=True)
        OUTPUT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        summary = {key: value for key, value in report.items()
                   if not key.startswith("full_")}
        print("PDV_SQL_ATTRIBUTION " + json.dumps(summary, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
