"""Seed comercial determinístico do E2E do Delivery Próprio F11-E."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("Seed Delivery F11-E so pode executar em teste isolado")
if os.environ.get("FM_AI_DELIVERY_V1") != "1":
    raise RuntimeError("Seed Delivery F11-E requer FM_AI_DELIVERY_V1=1")

from core.delivery.modelos import AreaEntrega
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel
from infra.crm.enderecos_sqlalchemy import EncryptedSQLAlchemyAddressStore
from infra.delivery.politica_sqlalchemy import RepositorioPoliticaEntregaSQLAlchemy
from migrations.runner import run_migrations

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no E2E Delivery")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Delivery fora da raiz temporaria permitida")

TMPDIR.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists():
    DB_PATH.unlink()

engine = create_engine(
    f"sqlite+pysqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
run_migrations(engine)

TENANT = "tenant-delivery-e2e"
UNIDADE = "unidade-delivery-e2e"
AGORA = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)


def identidade() -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="admin-delivery-e2e",
        email="admin-delivery-e2e@example.invalid",
        senha_hash="hash-test-delivery-e2e",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({UNIDADE}),
        ativo=True,
    )


with Session(engine) as session:
    session.execute(
        text("INSERT INTO lojas (id, nome_fantasia) VALUES (1, 'Loja Delivery E2E')")
    )
    session.execute(
        text(
            "INSERT INTO fm_unidade_loja_legacy_v1 "
            "(tenant_id, unidade_id, loja_id, ativo) "
            "VALUES (:tenant, :unidade, 1, TRUE)"
        ),
        {"tenant": TENANT, "unidade": UNIDADE},
    )
    session.execute(
        text(
            "INSERT INTO produtos "
            "(id, nome, categoria, descricao_bruta, descricao_ai, preco_venda, "
            "custo_total_cmv, margem_exibicao, imagem_path, loja_id) "
            "VALUES (1, 'Burger Delivery Comercial', 'Lanches', '', '', 32.00, "
            "12.00, '', NULL, 1)"
        )
    )
    session.execute(
        text(
            "INSERT INTO insumos "
            "(id, nome, unidade_medida, saldo_atual, estoque_minimo, custo_unitario, "
            "data_fabricacao, data_validade, dias_alerta_vencimento, loja_id) "
            "VALUES (1, 'Burger Base E2E', 'un', 30, 2, 12.00, NULL, NULL, 15, 1)"
        )
    )
    session.execute(
        text(
            "INSERT INTO fichas_tecnicas "
            "(id, produto_id, insumo_id, quantidade_utilizada) VALUES (1, 1, 1, 1)"
        )
    )

    clientes = (
        ("cliente-delivery-a", "01001000", "Rua Cliente A, 10 - Centro - São Paulo/SP"),
        ("cliente-delivery-b", "99999999", "Rua Fora da Área, 20 - São Paulo/SP"),
        ("cliente-delivery-c", "01002000", "Rua Cliente C, 30 - Centro - São Paulo/SP"),
    )
    for indice, (cliente_id, _cep, _endereco) in enumerate(clientes, start=1):
        session.execute(
            text(
                "INSERT INTO crm_clientes_v1 "
                "(tenant_id, unidade_id, cliente_id, origem, marketplace_origem, "
                "criado_em, versao) VALUES "
                "(:tenant, :unidade, :cliente, 'delivery_proprio', NULL, :agora, 1)"
            ),
            {
                "tenant": TENANT,
                "unidade": UNIDADE,
                "cliente": cliente_id,
                "agora": AGORA.replace(microsecond=indice),
            },
        )
        session.execute(
            text(
                "INSERT INTO crm_cliente_contatos_v1 "
                "(tenant_id, unidade_id, cliente_id, canal, referencia) VALUES "
                "(:tenant, :unidade, :cliente, 'whatsapp', :referencia)"
            ),
            {
                "tenant": TENANT,
                "unidade": UNIDADE,
                "cliente": cliente_id,
                "referencia": f"contact://{cliente_id}",
            },
        )

    politica = RepositorioPoliticaEntregaSQLAlchemy(session)
    politica.configurar_origem(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        endereco_texto="Rua da Unidade, 100 - Centro - São Paulo/SP",
    )
    politica.configurar_area(
        area=AreaEntrega(
            area_id="centro-delivery-e2e",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            nome="Centro E2E",
            prefixos_cep=("010",),
            taxa=Decimal("7.00"),
            sla_minutos=25,
            sla_maxutos=45,
            versao=1,
        )
    )

    contexto = identidade().contexto(
        origem="seed-delivery-e2e",
        correlation_id="corr-seed-delivery-e2e",
        solicitado_em=AGORA,
    )
    enderecos = EncryptedSQLAlchemyAddressStore(session)
    for indice, (cliente_id, cep, endereco) in enumerate(clientes, start=1):
        enderecos.armazenar_validado(
            contexto=contexto,
            cliente_id=cliente_id,
            endereco_formatado=endereco,
            cep=cep,
            place_id=f"place-delivery-e2e-{indice}",
            latitude=Decimal("-23.5505") + Decimal(indice) / Decimal("10000"),
            longitude=Decimal("-46.6333") - Decimal(indice) / Decimal("10000"),
            agora=AGORA,
        )

    session.commit()

print(DB_PATH)
