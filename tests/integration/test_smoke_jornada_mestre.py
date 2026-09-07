from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.dominio.dinheiro import Dinheiro
from core.pagamentos import (
    MetodoPagamento,
    RepositorioPagamentosSQLAlchemy,
    confirmar_pagamento,
    criar_obrigacao_pagamento,
)
from core.pagamentos.modelos_orm import PagamentoORM
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.salao import (
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
    ServicoSalao,
    StatusComanda,
    StatusMesa,
)
from core.salao.modelos_orm import (
    ComandaORM,
    MesaORM,
    PagamentoConfirmadoComandaORM,
    PedidoComandaORM,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "smoke-jornada-mestre-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Smoke-Mestre-123"
EMAIL = "gerente-smoke-mestre@example.com"
USUARIO_ID = "usuario-smoke-jornada-mestre"
TENANT = "tenant-smoke-jornada-mestre"
UNIDADE = "unidade-smoke-jornada-mestre"
MESA_ID = "mesa-smoke-jornada-mestre-01"
PAGAMENTO_ID = "pagamento-smoke-jornada-mestre-01"
PRECO = Decimal("27.50")
QUANTIDADE = 2
TOTAL = Decimal("55.00")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _contexto_sistema() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="fixture-smoke-jornada-mestre",
        motivo="preparar mesa para smoke integrado mestre",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        correlation_id="fixture:smoke-jornada-mestre",
        solicitado_em=_agora(),
    )


def _contexto_gerente() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=USUARIO_ID,
        papeis=frozenset({Papel.GERENTE}),
        permissoes=MATRIZ_PADRAO[Papel.GERENTE],
        correlation_id="corr:smoke-jornada-mestre:fechamento",
        solicitado_em=_agora(),
        origem="smoke_jornada_mestre",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _headers_salao(idempotency_key: str | None = None) -> dict[str, str]:
    auth = base64.b64encode(f"{EMAIL}:{SENHA}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": UNIDADE,
        "X-Correlation-ID": "corr-smoke-jornada-mestre-http",
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_smoke_jornada_mestre_integrada(monkeypatch) -> None:
    """Prova uma jornada real única na mesma app, engine e banco do restaurante."""

    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fm_unidade_loja_legacy_v1
                    (tenant_id, unidade_id, loja_id, ativo)
                VALUES (:tenant, :unidade, 91, TRUE)
                """
            ),
            {"tenant": TENANT, "unidade": UNIDADE},
        )

    with factory() as session:
        ServicoSalao(
            RepositorioSalaoSQLAlchemy(session),
            agora=_agora,
        ).cadastrar_mesa(
            _contexto_sistema(),
            mesa_id=MESA_ID,
            codigo="SMOKE-01",
            capacidade=4,
            idempotency_key="seed:smoke-jornada-mestre:mesa",
            nome="Mesa Smoke Mestre",
        )
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id=USUARIO_ID,
            email=EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
        )
        session.commit()

    app = build_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
        ),
        engine=engine,
        session_factory=factory,
    )
    client = TestClient(app)

    login = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": SENHA},
    )
    assert login.status_code == 200
    assert login.json()["usuario_id"] == USUARIO_ID
    assert login.json()["tenant_id"] == TENANT
    assert login.json()["unidade_ativa_id"] == UNIDADE

    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["usuario_id"] == USUARIO_ID
    assert me.json()["tenant_id"] == TENANT
    assert me.json()["unidade_ativa_id"] == UNIDADE
    assert "configuracao.alterar" in me.json()["permissoes"]
    assert "comanda.fechar" in me.json()["permissoes"]

    produto = client.post(
        "/v1/catalogo/produtos",
        headers={
            "Idempotency-Key": "smoke-mestre:produto:001",
            "X-Correlation-ID": "corr-smoke-mestre-produto",
        },
        json={
            "nome": "Prato Smoke Mestre",
            "categoria": "Homologacao",
            "preco": float(PRECO),
            "ativo": True,
        },
    )
    assert produto.status_code == 201
    produto_id = produto.json()["id"]
    assert produto.json()["ativo"] is True
    assert Decimal(str(produto.json()["preco"])) == PRECO

    abertura = client.post(
        "/v1/salao/comandas/abrir",
        headers=_headers_salao("smoke-mestre:comanda:abrir:001"),
        json={"mesa_id": MESA_ID},
    )
    assert abertura.status_code == 201
    comanda_id = abertura.json()["comanda"]["id"]
    assert abertura.json()["comanda"]["status_comanda"] == "ABERTA"

    lancamento = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=_headers_salao("smoke-mestre:pedido:001"),
        json={
            "itens": [
                {
                    "produto_id": f"legacy:produto:{produto_id}",
                    "quantidade": QUANTIDADE,
                    "observacao": "smoke integrado mestre",
                }
            ]
        },
    )
    assert lancamento.status_code == 201
    pedido_id = lancamento.json()["pedido"]["pedido_id"]
    assert lancamento.json()["comanda"]["status_comanda"] == "EM_CONSUMO"
    assert Decimal(lancamento.json()["pedido"]["valor"]) == TOTAL
    assert Decimal(lancamento.json()["comanda"]["total"]) == TOTAL
    assert Decimal(lancamento.json()["comanda"]["saldo"]) == TOTAL

    conta = client.post(
        f"/v1/salao/comandas/{comanda_id}/solicitar-conta",
        headers=_headers_salao("smoke-mestre:conta:001"),
    )
    assert conta.status_code == 200
    assert conta.json()["comanda"]["status_comanda"] == "CONTA_SOLICITADA"

    contexto = _contexto_gerente()
    with factory() as session:
        repositorio_salao = RepositorioSalaoSQLAlchemy(session)
        servico_salao = ServicoSalao(repositorio_salao, agora=_agora)
        comanda = repositorio_salao.obter_comanda(TENANT, UNIDADE, comanda_id)
        assert comanda is not None
        assert comanda.status == StatusComanda.CONTA_SOLICITADA
        assert comanda.total == TOTAL
        assert comanda.saldo == TOTAL

        em_fechamento, parcelas = servico_salao.definir_divisao_pagamento(
            contexto,
            comanda_id=comanda_id,
            expected_version=comanda.versao,
            idempotency_key="smoke-mestre:divisao:001",
            divisoes=((MetodoFechamento.DINHEIRO, TOTAL, None),),
        )
        assert em_fechamento.status == StatusComanda.FECHAMENTO_EM_ANDAMENTO
        assert len(parcelas) == 1

        repositorio_pagamentos = RepositorioPagamentosSQLAlchemy(session)
        obrigacao = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=repositorio_pagamentos,
            pagamento_id=PAGAMENTO_ID,
            pedido_id=pedido_id,
            valor_previsto=Dinheiro(TOTAL, "BRL"),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="smoke-mestre:pagamento:obrigacao:001",
            timestamp=_agora(),
            comanda_id=comanda_id,
        )
        assert obrigacao.pagamento.saldo.valor == TOTAL

        confirmado = confirmar_pagamento(
            contexto=contexto,
            repositorio=repositorio_pagamentos,
            pagamento_id=PAGAMENTO_ID,
            valor=Dinheiro(TOTAL, "BRL"),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="smoke-mestre:pagamento:confirmar:001",
            expected_version=obrigacao.pagamento.versao,
            timestamp=_agora(),
        )
        assert confirmado.pagamento.status.value == "pago"
        assert confirmado.pagamento.saldo.valor == Decimal("0.00")

        pago = servico_salao.registrar_pagamento_confirmado(
            contexto,
            comanda_id=comanda_id,
            pagamento_id=PAGAMENTO_ID,
            metodo=MetodoFechamento.DINHEIRO,
            valor=TOTAL,
            expected_version=em_fechamento.versao,
            idempotency_key="smoke-mestre:salao:pagamento:001",
        )
        assert pago.saldo == Decimal("0.00")

        fechada = servico_salao.fechar_comanda(
            contexto,
            comanda_id=comanda_id,
            expected_version=pago.versao,
            idempotency_key="smoke-mestre:comanda:fechar:001",
            pedidos_resolvidos=True,
        )
        assert fechada.status == StatusComanda.FECHADA
        assert fechada.saldo == Decimal("0.00")
        session.commit()

    with Session(engine) as session:
        comanda_db = session.get(ComandaORM, (comanda_id, TENANT, UNIDADE))
        pagamento_db = session.get(PagamentoORM, (PAGAMENTO_ID, TENANT, UNIDADE))
        mesa_db = session.get(MesaORM, (MESA_ID, TENANT, UNIDADE))
        assert comanda_db is not None
        assert pagamento_db is not None
        assert mesa_db is not None

        total_pago = session.scalar(
            select(func.coalesce(func.sum(PagamentoConfirmadoComandaORM.valor), 0))
            .where(
                PagamentoConfirmadoComandaORM.tenant_id == TENANT,
                PagamentoConfirmadoComandaORM.unidade_id == UNIDADE,
                PagamentoConfirmadoComandaORM.comanda_id == comanda_id,
            )
        )
        vinculos = session.scalar(
            select(func.count())
            .select_from(PedidoComandaORM)
            .where(
                PedidoComandaORM.tenant_id == TENANT,
                PedidoComandaORM.unidade_id == UNIDADE,
                PedidoComandaORM.comanda_id == comanda_id,
                PedidoComandaORM.pedido_id == pedido_id,
            )
        )

        assert comanda_db.status == StatusComanda.FECHADA.value
        assert Decimal(str(comanda_db.total)) == TOTAL
        assert Decimal(str(comanda_db.saldo)) == Decimal("0.00")
        assert pagamento_db.status == "pago"
        assert Decimal(str(pagamento_db.valor_pago)) == TOTAL
        assert Decimal(str(pagamento_db.saldo)) == Decimal("0.00")
        assert Decimal(str(total_pago)) == TOTAL
        assert Decimal(str(comanda_db.total)) - Decimal(str(total_pago)) == Decimal("0.00")
        assert int(vinculos or 0) == 1
        assert mesa_db.status == StatusMesa.LIVRE.value
