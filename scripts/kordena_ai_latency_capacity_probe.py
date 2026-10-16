"""Isolated AI wait + real HTTP/Postgres execution stress probe; no paid provider calls.

Model network latency is simulated ONLY; authentication, FastAPI, Core tools,
unit-of-work, SQL persistence and AI usage metering are real in ephemeral CI.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import application.gerente_ia_runtime as runtime_module
import http_api.gerente_ia_web as web_module
from core.ai_router import (
    AIModelRouter, CapabilityIA, FalhaRotaTransitoria,
    RotaIA, RespostaModeloIA,
)
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from http_api.frontend_app import build_frontend_http_app
from infra.ai_metering import AIUsageDurableMetering
from migrations.runner import run_migrations
from scripts.kca15_internal_homologation import (
    EMAIL, _create_internal_commercial_state, _ensure_legacy_scope_and_identity,
)

PATH = "/v1/gerente-ia/perguntar"
PAYLOAD = {"pergunta": "Quais pedidos estão atrasados? Mostre até 10."}
RESPONSE = '{"tool":"consultar_atrasos","argumentos":{"limite":10}}'
CURRENT = {"primary_delay": 3.0, "fallback": False, "fallback_delay": 1.5}
STEPS = ((1, 2), (5, 10), (10, 20), (25, 35), (50, 50), (100, 100), (250, 150))
SERVER_EXCEPTIONS = Counter()
SERVER_LOCK = Lock()
POOL = None



def stats(samples: list[float]) -> dict:
    import math
    values = sorted(samples)
    def percentile(p: float):
        return round(1000 * values[max(0, math.ceil(len(values) * p) - 1)], 1) if values else None
    return {"p50_ms": percentile(.50), "p95_ms": percentile(.95),
            "p99_ms": percentile(.99), "max_ms": percentile(1.0)}


class ControlledNetworkWait:
    """Only the external model's inference/wait is simulated."""
    def executar(self, *, rota, solicitacao):
        if rota.provider == "openai":
            time.sleep(CURRENT["primary_delay"])
            if CURRENT["fallback"]:
                raise FalhaRotaTransitoria("bench.simulated_provider_503")
        else:
            time.sleep(CURRENT["fallback_delay"])
        return RespostaModeloIA(conteudo=RESPONSE, input_tokens=100, output_tokens=25)


def router_factory(*, session, contexto, secret_store=None):
    bind = session.get_bind()
    factory = sessionmaker(bind=bind, expire_on_commit=False, future=True)
    return AIModelRouter(
        rotas=(
            RotaIA(configuracao_id="bench--openai", provider="openai",
                   model="simulated-3s-openai", capability=CapabilityIA.TOOL_PLANNING,
                   prioridade=200, price_snapshot_id="bench-unpriced"),
            RotaIA(configuracao_id="bench--gemini", provider="gemini",
                   model="simulated-fallback", capability=CapabilityIA.TOOL_PLANNING,
                   prioridade=100, price_snapshot_id="bench-unpriced"),
        ),
        executor=ControlledNetworkWait(),
        metering=AIUsageDurableMetering(factory),
    )


async def phase(client: httpx.AsyncClient, concurrent: int, count: int) -> dict:
    q = asyncio.Queue()
    for n in range(count):
        q.put_nowait(n)
    observed = []

    async def worker():
        while True:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                return
            begin = time.perf_counter()
            try:
                res = await asyncio.wait_for(client.post(PATH, json=PAYLOAD), timeout=32)
                code = res.status_code
            except (TimeoutError, httpx.HTTPError):
                code = 0
            observed.append((code, time.perf_counter() - begin))
            q.task_done()
    peak_checked_out = 0
    finished = asyncio.Event()

    async def observe_db_pool():
        nonlocal peak_checked_out
        while not finished.is_set():
            if POOL is not None:
                peak_checked_out = max(peak_checked_out, POOL.checkedout())
            await asyncio.sleep(.02)

    observer = asyncio.create_task(observe_db_pool())
    started = time.perf_counter()
    try:
        await asyncio.gather(*(worker() for _ in range(concurrent)))
    finally:
        finished.set()
        await observer
    elapsed = time.perf_counter() - started
    codes = dict(Counter(str(code) for code, _ in observed))
    latencies = [elapsed for _, elapsed in observed]
    return {
        "in_flight": concurrent, "requests": len(observed),
        "http_200": codes.get("200", 0),
        "errors": len(observed) - codes.get("200", 0),
        "status_counts": codes,
        "duration_s": round(elapsed, 2),
        "rps": round(len(observed) / max(elapsed, .001), 2),
        "peak_db_connections_checked_out": peak_checked_out,
        "server_errors_seen": dict(SERVER_EXCEPTIONS),
        **stats(latencies),
    }


async def run() -> dict:
    db = os.environ["DATABASE_URL"]
    if not db.startswith("postgresql") or "127.0.0.1" not in db:
        raise RuntimeError("Isolated localhost PostgreSQL is mandatory")
    if os.getenv("FM_AI_TEST_MODE"):
        raise RuntimeError("Do not hide application behavior behind FM_AI_TEST_MODE")
    engine = create_engine(db, future=True, pool_size=10, max_overflow=10, pool_timeout=8)
    global POOL
    POOL = engine.pool
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    password = os.environ["KCA15_INTERNAL_PASSWORD"]
    _create_internal_commercial_state(factory)
    _ensure_legacy_scope_and_identity(factory, password)
    settings = RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url=db, tenant_id="bench-core", unidade_id="bench-core",
        commercial_access_gate_enabled=True,
        fmcc_control_plane_token=os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"],
    ).validate()
    app = build_frontend_http_app(
        settings=settings, engine=engine, session_factory=factory,
        commercial_access_gate_enabled=True,
    )
    runtime_module.construir_ai_model_router = router_factory
    original_error_handler = web_module._tratar_erro

    def record_server_exception(exc: Exception):
        kinds = []
        seen = set()
        current = exc
        for _ in range(4):
            if current is None or id(current) in seen:
                break
            seen.add(id(current))
            kinds.append(type(current).__module__ + '.' + type(current).__name__)
            current = current.__cause__ or current.__context__
        with SERVER_LOCK:
            SERVER_EXCEPTIONS[' / '.join(kinds)] += 1
        return original_error_handler(exc)

    web_module._tratar_erro = record_server_exception
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": "authenticated Core AI question path with real PostgreSQL 16 and durable AI metering",
        "real_llm_calls": 0, "production_requests": 0, "tenants": 1,
        "artificial_provider_wait_seconds": 3,
        "database_pool_size": 10, "database_max_overflow": 10,
        "transport": "in-process ASGI; runner resources are not Railway",
        "phases": [],
    }
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="https://core-ai-bench.local", timeout=35) as client:
            response = await client.post("/v1/auth/login", json={"email": EMAIL, "senha": password})
            if response.status_code != 200:
                raise RuntimeError(f"bench login HTTP {response.status_code}")
            warmup = await client.post(PATH, json=PAYLOAD)
            if warmup.status_code != 200:
                raise RuntimeError(f"bench authenticated AI preflight HTTP {warmup.status_code}; body={warmup.text[:160]}")
            for concurrency, count in STEPS:
                result = await phase(client, concurrency, count)
                report["phases"].append(result)
                print("SIMULATED_AI_LOAD " + json.dumps(result, sort_keys=True), flush=True)
                if result["errors"] >= max(4, result["requests"] // 5):
                    report["early_stop"] = "errors at or above 20%"
                    break
                if result["p95_ms"] is not None and result["p95_ms"] > 22000:
                    report["early_stop"] = "p95 above 22 sec"
                    break
            CURRENT["fallback"] = True
            CURRENT["primary_delay"] = 0.7
            CURRENT["fallback_delay"] = 2.0
            for concurrency, count in ((1, 2), (10, 20), (50, 50)):
                result = await phase(client, concurrency, count)
                report.setdefault("simulated_transient_failure_fallback", []).append(result)
                print("SIMULATED_FALLBACK " + json.dumps(result, sort_keys=True), flush=True)
                if result["errors"] >= max(4, result["requests"] // 5):
                    break
    finally:
        engine.dispose()
    return report


if __name__ == "__main__":
    path = Path("evidence/kordena-ai-simulated-load-20261016.json")
    path.parent.mkdir(exist_ok=True)
    try:
        out = asyncio.run(run())
        out["status"] = "completed"
    except Exception as exc:
        out = {"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:220]}"}
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        raise
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("AI_CAPACITY_RESULT " + json.dumps(out, sort_keys=True), flush=True)
