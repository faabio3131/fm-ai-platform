"""Ephemeral E2E FastAPI server with a real migrated SQLite database.

Only for local CI: creates a TEST tenant/operator/product/order and hosts the
actual FastAPI application. Never runs against an external DB or deployment.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
import uvicorn
from fastapi.testclient import TestClient
from tests.api.test_central_pedidos_http_contract import (
    _infra, _login, _criar_pedido_pdv,
)

patch = pytest.MonkeyPatch()
client: TestClient = _infra(patch)
_login(client)
created = _criar_pedido_pdv(client)
order_id = created["comanda"]["pedido_id"]
print(f"E2E seeded isolated order {order_id}", flush=True)
uvicorn.run(client.app, host="127.0.0.1", port=8000, log_level="warning")
