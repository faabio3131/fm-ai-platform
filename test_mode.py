"""Modo de teste isolado para execução funcional/E2E segura.

Ativado exclusivamente por ``FM_AI_TEST_MODE=1``. Nunca é ligado por padrão.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

TEST_MODE_ENV = "FM_AI_TEST_MODE"


def is_test_mode() -> bool:
    return os.getenv(TEST_MODE_ENV) == "1"


@dataclass(frozen=True)
class RuntimeConfig:
    enabled: bool
    root_dir: Path | None
    database_url: str
    files_dir: Path


def build_runtime(
    default_database_url: str = "sqlite:///./banco_erp_local.db",
) -> RuntimeConfig:
    if not is_test_mode():
        return RuntimeConfig(False, None, default_database_url, Path("imagens"))

    root = Path(
        os.getenv("FM_AI_TEST_TMPDIR") or tempfile.mkdtemp(prefix="fm_ai_test_")
    )
    root.mkdir(parents=True, exist_ok=True)
    files_dir = root / "files"
    files_dir.mkdir(exist_ok=True)
    db_path = root / "fm_ai_test.sqlite3"

    if os.getenv("FM_AI_TEST_KEEP_TMP") != "1":
        atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))

    return RuntimeConfig(True, root, f"sqlite:///{db_path}", files_dir)


def reset_database(engine: Any, base: Any) -> None:
    if not is_test_mode():
        raise RuntimeError("Reset do banco só é permitido com FM_AI_TEST_MODE=1.")
    base.metadata.drop_all(bind=engine)
    base.metadata.create_all(bind=engine, checkfirst=True)


def prepare_legacy_scope(
    engine: Any,
    *,
    tenant_id: str,
    unidade_id: str,
) -> None:
    """Cria um vínculo explícito e determinístico somente no sandbox de teste."""
    if not is_test_mode():
        raise RuntimeError("Escopo legado de teste só pode existir no sandbox.")

    from sqlalchemy import text

    from migrations.legacy_catalog_unit_scope_v1 import (
        upgrade_legacy_catalog_unit_scope_v1,
    )
    from migrations.legacy_store_baseline_v1 import (
        upgrade_legacy_store_baseline_v1,
    )
    from migrations.product_unit_scope_compat_v1 import (
        upgrade_product_unit_scope_compat_v1,
    )
    from migrations.unit_legacy_store_mapping_v1 import (
        upgrade_unit_legacy_store_mapping_v1,
    )

    with engine.begin() as connection:
        upgrade_legacy_store_baseline_v1(connection)
        upgrade_unit_legacy_store_mapping_v1(connection)
        upgrade_product_unit_scope_compat_v1(connection)

        existente = connection.execute(
            text(
                "SELECT loja_id FROM fm_unidade_loja_legacy_v1 "
                "WHERE tenant_id = :tenant_id AND unidade_id = :unidade_id "
                "AND ativo = TRUE"
            ),
            {"tenant_id": tenant_id, "unidade_id": unidade_id},
        ).scalar_one_or_none()
        if existente is None:
            loja_id = connection.execute(
                text("SELECT COALESCE(MAX(id), 0) + 1 FROM lojas")
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO lojas (id, nome_fantasia) "
                    "VALUES (:loja_id, 'Loja Sandbox')"
                ),
                {"loja_id": loja_id},
            )
            connection.execute(
                text(
                    "INSERT INTO fm_unidade_loja_legacy_v1 "
                    "(tenant_id, unidade_id, loja_id, ativo) "
                    "VALUES (:tenant_id, :unidade_id, :loja_id, TRUE)"
                ),
                {
                    "tenant_id": tenant_id,
                    "unidade_id": unidade_id,
                    "loja_id": loja_id,
                },
            )
        else:
            loja_id = existente

        connection.execute(
            text(
                "UPDATE produtos SET loja_id = :loja_id "
                "WHERE loja_id IS NULL"
            ),
            {"loja_id": loja_id},
        )
        upgrade_legacy_catalog_unit_scope_v1(connection)


def mock_generate_content(*, contents: Any, **_: Any) -> Any:
    text = str(contents).lower()
    if "fm_ai_mock_400" in text:
        raise RuntimeError("Gemini mock: erro 400")
    if "fm_ai_mock_403" in text:
        raise RuntimeError("Gemini mock: erro 403")
    if "fm_ai_mock_404" in text:
        raise RuntimeError("Gemini mock: erro 404")
    if "fm_ai_mock_429" in text:
        raise RuntimeError("Gemini mock: erro 429")
    if "fm_ai_mock_invalid" in text:
        return SimpleNamespace(text="{resposta inválida")
    if ("assistente de atendimento" in text or "assistente virtual" in text or "mica" in text):
        return SimpleNamespace(
            text=json.dumps(
                {
                    "cliente_nome": "Cliente Playwright",
                    "itens": [{"nome_produto": "Burger Teste", "quantidade": 1}],
                    "resposta_whatsapp": "Pedido confirmado em sandbox. Pix de teste gerado.",
                }
            )
        )
    return SimpleNamespace(
        text=json.dumps(
            [
                {
                    "nome": "Burger IA Teste",
                    "categoria": "Hambúrgueres",
                    "preco": 31.90,
                    "ingredientes": "pão, carne e queijo",
                },
                {
                    "nome": "Batata IA Teste",
                    "categoria": "Porções",
                    "preco": 18.50,
                    "ingredientes": "batata e sal",
                },
            ]
        )
    )


def mock_upload_file(*_: Any, **__: Any) -> str:
    return "fm-ai-test-upload://audio-ou-imagem-simulada"


def mock_whatsapp_send(phone: str, message: str) -> dict[str, Any]:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        return {"ok": False, "status_code": 400, "message": "Número inválido (mock)"}
    if "FM_AI_MOCK_WHATSAPP_FAIL" in message:
        return {
            "ok": False,
            "status_code": 503,
            "message": "Falha simulada de WhatsApp",
        }
    return {"ok": True, "status_code": 200, "message": "Envio WhatsApp simulado"}


def seed_database(
    session_factory: Any,
    models: dict[str, Any],
    *,
    tenant_id: str,
    unidade_id: str,
) -> None:
    if not is_test_mode():
        return
    prepare_legacy_scope(
        session_factory.kw["bind"],
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )
    db = session_factory()
    try:
        from infra.legacy_product_scope import (
            inserir_ficha_tecnica_legada,
            inserir_insumo_legado,
            inserir_produto_legado,
            listar_produtos_legados,
        )

        if listar_produtos_legados(
            db,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
        ):
            return
        Usuario = models["Usuario"]
        Cliente = models["Cliente"]
        Venda = models["Venda"]
        ConfiguracaoMeta = models["ConfiguracaoMeta"]
        ContatoGerencial = models["ContatoGerencial"]
        db.add(Usuario(email="admin.test@fm.ai", senha_hash="test-only"))
        carne_id = inserir_insumo_legado(
            db,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            valores={
                "nome": "Carne Teste",
                "unidade_medida": "un",
                "saldo_atual": 50,
                "estoque_minimo": 5,
                "custo_unitario": 7,
                "data_validade": datetime.now(timezone.utc) + timedelta(days=20),
            },
        )
        pao_id = inserir_insumo_legado(
            db,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            valores={
                "nome": "Pão Teste",
                "unidade_medida": "un",
                "saldo_atual": 50,
                "estoque_minimo": 5,
                "custo_unitario": 2,
                "data_validade": datetime.now(timezone.utc) + timedelta(days=5),
                "dias_alerta_vencimento": 7,
            },
        )
        cliente = Cliente(
            nome="Cliente Teste",
            whatsapp="5511999990001",
            ultima_compra=datetime.now(timezone.utc) - timedelta(days=30),
            total_gasto=100,
            saldo_cashback=10,
            status="Inativo",
        )
        produto_id = inserir_produto_legado(
            db,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            valores={
                "nome": "Burger Teste",
                "categoria": "Hambúrgueres",
                "preco_venda": 29.90,
                "custo_total_cmv": 9.0,
                "margem_exibicao": "69.9%",
            },
        )
        db.add_all(
            [
                cliente,
                ConfiguracaoMeta(
                    gateway_provider="Mercado Pago",
                    gateway_pix_key="sandbox-pix",
                    gateway_api_key=None,
                ),
                ContatoGerencial(
                    nome="Gerente Teste", whatsapp="5511999990002", cargo="Gerente"
                ),
            ]
        )
        db.commit()
        inserir_ficha_tecnica_legada(
            db,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            produto_id=produto_id,
            insumo_id=carne_id,
            quantidade=1,
        )
        inserir_ficha_tecnica_legada(
            db,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            produto_id=produto_id,
            insumo_id=pao_id,
            quantidade=1,
        )
        db.add(
            Venda(
                produto_id=produto_id,
                cliente_id=cliente.id,
                quantidade=1,
                valor_total=29.90,
                custo_total=9.0,
                forma_pagamento="Dinheiro Em Espécie",
            )
        )
        db.commit()
    finally:
        db.close()
