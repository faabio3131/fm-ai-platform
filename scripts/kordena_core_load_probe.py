"""Bounded, isolated Core read-path load probe; no external AI calls or production writes."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from http_api.frontend_app import build_frontend_http_app
from migrations.runner import run_migrations
from scripts.kca15_internal_homologation import (
    EMAIL,
    _create_internal_commercial_state,
    _ensure_legacy_scope_and_identity,
)

SCENARIOS = ((1, 24), (5, 50), (10, 75), (25, 100), (50, 100), (100, 100))
TOOL_PATH = "/v1/gerente-ia/tools"
PAYLOAD = {"tool": "consultar_atrasos", "argumentos": {"limite": 10}}


def percentile(samples: list[float], quantile: float) -> float | None:
    if not samples:
        return None
    values = sorted(samples)
    return round(values[max(0, math.ceil(quantile * len(values)) - 1)] * 1000, 2)


async def phase(client: httpx.AsyncClient, concurrency: int, target: int) -> dict:
    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(target):
        queue.put_nowait(i)
    results: list[tuple[int, float, str]] = []

    async def worker() -> None:
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            start = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    client.post(TOOL_PATH, json=PAYLOAD),
                    timeout=15.0,
                )
                status, error = response.status_code, ""
                if status != 200:
                    try:
                        error = str(response.json().get("erro", "http_error"))[:100]
                    except (ValueError, AttributeError):
                        error = "http_error"
            except (TimeoutError, httpx.HTTPError) as exc:
                status, error = 0, type(exc).__name__
            finally:
                queue.task_done()
            results.append((status, time.perf_counter() - start, error))

    start = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    duration = time.perf_counter() - start
    latencies = [latency for _, latency, _ in results]
    counts = Counter(str(status) for status, _, _ in results)
    reasons = Counter(error for status, _, error in results if status != 200)
    successes = counts.get("200", 0)
    return {
        "concurrency": concurrency,
        "target_requests": target,
        "completed_requests": len(results),
        "successes": successes,
        "errors": len(results) - successes,
        "error_rate_pct": round(100 * (len(results) - successes) / max(1, len(results)), 2),
        "duration_s": round(duration, 3),
        "throughput_rps": round(len(results) / max(duration, 0.001), 2),
        "successful_rps": round(successes / max(duration, 0.001), 2),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "max_ms": percentile(latencies, 1.0),
        "statuses": dict(counts),
        "errors_by_type": dict(reasons),
    }


async def measure() -> dict:
    assert not os.getenv("FM_AI_TEST_MODE"), "This runs without FM_AI_TEST_MODE"
    db = os.environ["DATABASE_URL"]
    assert db.startswith("postgresql") and "127.0.0.1" in db, "Ephemeral local PostgreSQL only"
    password = os.environ["KCA15_INTERNAL_PASSWORD"]
    engine = create_engine(db, future=True, pool_size=10, max_overflow=10, pool_timeout=8)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _create_internal_commercial_state(factory)
    _ensure_legacy_scope_and_identity(factory, password)
    settings = RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url=db,
        tenant_id="core-load-test-bootstrap",
        unidade_id="core-load-test-bootstrap",
        commercial_access_gate_enabled=True,
        fmcc_control_plane_token=os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"],
    ).validate()
    app = build_frontend_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        commercial_access_gate_enabled=True,
    )
    report = {
        "name": "Kordena Core real-operational read-path probe",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": "POST /v1/gerente-ia/tools (consultar_atrasos)",
        "environment": "isolated GitHub Actions runner, localhost ASGI + ephemeral PostgreSQL 16",
        "ai_provider_calls": 0,
        "production_traffic": 0,
        "real_customer_data": False,
        "limitations": [
            "ASGI in-process transport; not production network, TLS, CDN or Railway sizing",
            "One internal tenant and unit, read tool with persistent audit writes",
            "Does not measure LLM inference, Gemini/OpenAI rate limits, paid tokens or fallback",
            "Concurrency is in-flight HTTP tasks, not real-world registered users",
        ],
        "phases": [],
    }
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://core-load.local", timeout=20.0
        ) as client:
            login = await client.post(
                "/v1/auth/login", json={"email": EMAIL, "senha": password}
            )
            if login.status_code != 200:
                raise RuntimeError(f"Internal login failed: HTTP {login.status_code}")
            probe = await client.post(TOOL_PATH, json=PAYLOAD)
            if probe.status_code != 200:
                raise RuntimeError(f"Core preflight failed: HTTP {probe.status_code}; {probe.text[:120]}")
            for concurrency, target in SCENARIOS:
                item = await phase(client, concurrency, target)
                report["phases"].append(item)
                print("LOAD_PHASE " + json.dumps(item, sort_keys=True), flush=True)
                if item["errors"] >= max(5, item["completed_requests"] // 4):
                    report["early_stop_reason"] = "error budget exceeded"
                    break
                if item["p95_ms"] is not None and item["p95_ms"] > 12000:
                    report["early_stop_reason"] = "p95 latency exceeded 12 seconds"
                    break
    finally:
        engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/kordena-core-load-20261016.json")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = asyncio.run(measure())
    except Exception as exc:
        report = {
            "name": "Kordena Core real-operational read-path probe",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "setup_or_execution_failed",
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            "phases": [],
        }
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        raise
    report["status"] = "measurement_completed"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("CORE_LOAD_RESULT " + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
