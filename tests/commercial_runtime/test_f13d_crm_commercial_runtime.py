from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker

from application.crm_marketing_comercial import despachar_resgate_whatsapp_legado
from core.crm.adapters import PortaEnvioMarketing
from core.crm.cashback import ServicoCashback
from core.crm.modelos import OrigemClienteCRM
from core.dominio.dinheiro import Dinheiro
from core.pdv.modelos import EntradaPDV
from core.pdv.roteamento import ModoPDV
from core.runtime.config import RuntimeEnvironment, load_runtime_settings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.crm.cashback_sqlalchemy import RepositorioCashbackSQLAlchemy
from infra.transacoes.uow import RecursosTransacionaisV1
from tests.integration.pdv.conftest import ClienteTeste
from tests.integration.pdv.helpers import executar

pytestmark = pytest.mark.skipif(
    os.getenv("FM_AI_ENV") != "staging"
    or not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="F13-D commercial runtime exige staging com PostgreSQL efemero",
)

TENANT = "tenant-f6d"
UNIDADE = "unidade-f6d"
LEGACY_CLIENTE_ID = 13001
CLIENTE_CRM_ID = "cliente-crm-f13d"
AGORA = datetime(2026, 9, 5, 23, 0, tzinfo=timezone.utc)


class EnvioProbe(PortaEnvioMarketing):
    def __init__(self) -> None:
        self.chamadas = 0

    def enviar(
        self,
        *,
        referencia_contato: str,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None:
        del referencia_contato, campanha_ref, idempotency_key
        self.chamadas += 1


def _factory() -> sessionmaker[Session]:
    assert os.getenv("FM_AI_TEST_MODE") != "1"
    settings = load_runtime_settings()
    assert settings.environment is RuntimeEnvironment.STAGING
    assert settings.commercial
    engine = create_engine(settings.database_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _seed_cliente(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        connection = session.connection()
        clientes = Table("clientes", MetaData(), autoload_with=connection)
        crm_clientes = Table("crm_clientes_v1", MetaData(), autoload_with=connection)
        mapping = Table("crm_cliente_legado_v1", MetaData(), autoload_with=connection)

        if session.execute(
            select(clientes.c.id).where(clientes.c.id == LEGACY_CLIENTE_ID)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(clientes).values(
                    id=LEGACY_CLIENTE_ID,
                    nome="Cliente F13-D",
                    whatsapp="5511999991301",
                    total_gasto=0.0,
                    saldo_cashback=10.0,
                    status="Ativo",
                )
            )

        if session.execute(
            select(crm_clientes.c.cliente_id)
            .where(crm_clientes.c.tenant_id == TENANT)
            .where(crm_clientes.c.unidade_id == UNIDADE)
            .where(crm_clientes.c.cliente_id == CLIENTE_CRM_ID)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(crm_clientes).values(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    cliente_id=CLIENTE_CRM_ID,
                    origem=OrigemClienteCRM.LEGADO_REGULARIZADO.value,
                    marketplace_origem=None,
                    criado_em=AGORA,
                    versao=1,
                )
            )

        if session.execute(
            select(mapping.c.cliente_id)
            .where(mapping.c.tenant_id == TENANT)
            .where(mapping.c.unidade_id == UNIDADE)
            .where(mapping.c.legacy_cliente_id == LEGACY_CLIENTE_ID)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(mapping).values(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    legacy_cliente_id=LEGACY_CLIENTE_ID,
                    cliente_id=CLIENTE_CRM_ID,
                    criado_por="gate-f13d",
                    correlation_id="corr-f13d-seed",
                    criado_em=AGORA,
                )
            )

        ServicoCashback(RepositorioCashbackSQLAlchemy(session)).creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE_CRM_ID,
            valor=Decimal("10.00"),
            origem="regularizacao_governada",
            referencia="gate://f13d/regularizacao",
            idempotency_key="f13d:regularizacao:cashback",
            ocorrido_em=AGORA,
        )


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "caixa-f13d",
        frozenset({Papel.CAIXA}),
        MATRIZ_PADRAO[Papel.CAIXA],
        "corr-f13d",
        AGORA,
        "commercial-runtime-f13d",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def test_f13d_crm_cashback_pdv_liquidacao_saldo_em_postgresql_comercial() -> None:
    factory = _factory()
    _seed_cliente(factory)

    with factory() as session:
        produtos = Table("produtos", MetaData(), autoload_with=session.connection())
        produto = session.execute(
            select(
                produtos.c.id,
                produtos.c.nome,
                produtos.c.preco_venda,
                produtos.c.custo_total_cmv,
            )
            .where(produtos.c.nome == "Produto F6-D")
            .where(produtos.c.loja_id == "6001")
        ).one()

    entrada = EntradaPDV(
        produto_id=int(produto.id),
        produto_nome=str(produto.nome),
        quantidade=1,
        preco_unitario=Dinheiro(Decimal(str(produto.preco_venda))),
        custo_total=Dinheiro(Decimal(str(produto.custo_total_cmv))),
        forma_pagamento="Dinheiro Em Espécie",
        terminal_id="caixa-f13d",
        checkout_id="checkout-f13d",
        cliente_id=LEGACY_CLIENTE_ID,
        valor_recebido=Dinheiro(Decimal("50.00")),
        usar_cashback=True,
        desconto_cashback=Dinheiro(Decimal("5.00")),
        confirmacao_presencial=True,
    )

    resultado = executar(
        factory,
        _contexto(),
        entrada,
        ModoPDV.AUTHORITATIVE_CANARY,
    )
    assert resultado.sucesso
    assert resultado.pedido_id is not None
    assert resultado.pagamento_id is not None

    with factory() as session:
        recursos = RecursosTransacionaisV1(session)
        saldo = recursos.cashback.saldo(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE_CRM_ID,
        )
        historico = recursos.cashback.historico(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE_CRM_ID,
        )
        cliente_legado = session.get(ClienteTeste, LEGACY_CLIENTE_ID)

        assert saldo == Decimal("5.75")
        assert len(historico) == 3
        assert cliente_legado is not None
        assert Decimal(str(cliente_legado.saldo_cashback)) == saldo


def test_f13d_marketing_sem_consentimento_nao_toca_transporte_comercial() -> None:
    factory = _factory()
    _seed_cliente(factory)
    envio = EnvioProbe()

    resultado = despachar_resgate_whatsapp_legado(
        session_factory=factory,
        contexto=_contexto(),
        legacy_cliente_id=LEGACY_CLIENTE_ID,
        campanha_ref="campanha-f13d-sem-consentimento",
        texto="Mensagem que nao pode ser enviada sem consentimento.",
        idempotency_key="f13d:marketing:no-consent",
        envio=envio,
    )

    assert not resultado.enviado
    assert resultado.motivo == "marketing_sem_consentimento"
    assert envio.chamadas == 0
