from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.salao_transacoes import AplicacaoSalaoV1
from core.dominio.enums import PagamentoStatus
from core.pagamentos.erros import (
    ConcorrenciaPagamento,
    FonteFinanceiraNaoConfiavel,
    OperacaoPagamentoNaoAutorizada,
)
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.salao import (
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
    ServicoSalao,
    StatusComanda,
)
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from migrations.runner import run_migrations

AGORA = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
TENANT = "tenant-f7c"
UNIDADE = "unidade-f7c"
PEDIDO = "pedido-f7c"
COMANDA = "comanda-f7c"


def _contexto(papel: Papel = Papel.GERENTE) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=f"ator-{papel.value}",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-{papel.value}",
        solicitado_em=AGORA,
        origem="tests.f7c.salao",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _infra(tmp_path, metodo: MetodoFechamento):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / ('f7c-' + metodo.value + '.db')}",
        future=True,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        servico = ServicoSalao(
            RepositorioSalaoSQLAlchemy(session),
            agora=lambda: AGORA,
        )
        mesa = servico.cadastrar_mesa(
            _contexto(),
            mesa_id="mesa-f7c",
            codigo="F7C",
            capacidade=4,
            idempotency_key="f7c:mesa",
        )
        session.add(
            PedidoORM(
                id=PEDIDO,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                origem="salao",
                canal="mesa",
                status="confirmado",
                cliente_id=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=1,
                correlation_id="corr-pedido-f7c",
                idempotency_key="idem-pedido-f7c",
                request_hash="hash-pedido-f7c",
                subtotal=Decimal("20.00"),
                descontos=Decimal("0.00"),
                taxas=Decimal("0.00"),
                total=Decimal("20.00"),
            )
        )
        session.flush()
        comanda = servico.abrir_comanda(
            _contexto(),
            comanda_id=COMANDA,
            numero="F7C-1",
            mesa_id=mesa.mesa_id,
            expected_mesa_version=mesa.versao,
            idempotency_key="f7c:abrir",
        )
        comanda = servico.vincular_pedido(
            _contexto(),
            comanda_id=COMANDA,
            pedido_id=PEDIDO,
            expected_version=comanda.versao,
            idempotency_key="f7c:vincular",
        )
        comanda = servico.solicitar_conta(
            _contexto(),
            comanda_id=COMANDA,
            expected_version=comanda.versao,
            idempotency_key="f7c:conta",
        )
        comanda, _ = servico.definir_divisao_pagamento(
            _contexto(),
            comanda_id=COMANDA,
            expected_version=comanda.versao,
            idempotency_key=f"f7c:plano:{metodo.value}",
            divisoes=((metodo, Decimal("20.00"), None),),
        )
        session.commit()

    return engine, factory, comanda


def test_dinheiro_cria_confirma_projeta_e_fecha_idempotente(tmp_path) -> None:
    _engine, factory, comanda = _infra(tmp_path, MetodoFechamento.DINHEIRO)
    app = AplicacaoSalaoV1(factory, agora=lambda: AGORA)

    criado = app.criar_pagamento_canonico(
        _contexto(),
        pagamento_id="pay-f7c-cash",
        pedido_id=PEDIDO,
        comanda_id=COMANDA,
        metodo=MetodoFechamento.DINHEIRO,
        valor=Decimal("20.00"),
        idempotency_key="f7c:pay:create:cash",
    )
    assert criado.pagamento.status is PagamentoStatus.PENDENTE
    assert criado.pagamento.metodo is MetodoPagamento.DINHEIRO
    assert criado.pagamento.comanda_id == COMANDA

    confirmado = app.confirmar_pagamento_canonico(
        _contexto(),
        pagamento_id="pay-f7c-cash",
        comanda_id=COMANDA,
        metodo=MetodoFechamento.DINHEIRO,
        valor=Decimal("20.00"),
        expected_payment_version=1,
        idempotency_key="f7c:pay:confirm:cash",
    )
    assert confirmado.pagamento.status is PagamentoStatus.PAGO
    assert confirmado.pagamento.saldo.valor == Decimal("0.00")

    repetido = app.confirmar_pagamento_canonico(
        _contexto(),
        pagamento_id="pay-f7c-cash",
        comanda_id=COMANDA,
        metodo=MetodoFechamento.DINHEIRO,
        valor=Decimal("20.00"),
        expected_payment_version=1,
        idempotency_key="f7c:pay:confirm:cash",
    )
    assert repetido.idempotente is True

    projetada = app.registrar_pagamento_confirmado(
        _contexto(),
        pagamento_id="pay-f7c-cash",
        comanda_id=COMANDA,
        metodo=MetodoFechamento.DINHEIRO,
        valor=Decimal("20.00"),
        expected_version=comanda.versao,
        idempotency_key="f7c:project:cash",
    )
    assert projetada.saldo == Decimal("0.00")

    fechada = app.fechar_comanda(
        _contexto(),
        comanda_id=COMANDA,
        expected_version=projetada.versao,
        idempotency_key="f7c:close",
        pedidos_resolvidos=True,
    )
    assert fechada.status is StatusComanda.FECHADA

    replay = app.fechar_comanda(
        _contexto(),
        comanda_id=COMANDA,
        expected_version=projetada.versao,
        idempotency_key="f7c:close",
        pedidos_resolvidos=True,
    )
    assert replay.status is StatusComanda.FECHADA


def test_cartao_exige_referencia_e_cas_rejeita_confirmacao_concorrente(tmp_path) -> None:
    _engine, factory, _comanda = _infra(
        tmp_path,
        MetodoFechamento.CARTAO_CREDITO,
    )
    app = AplicacaoSalaoV1(factory, agora=lambda: AGORA)
    app.criar_pagamento_canonico(
        _contexto(),
        pagamento_id="pay-f7c-card",
        pedido_id=PEDIDO,
        comanda_id=COMANDA,
        metodo=MetodoFechamento.CARTAO_CREDITO,
        valor=Decimal("20.00"),
        idempotency_key="f7c:pay:create:card",
    )

    with pytest.raises(FonteFinanceiraNaoConfiavel):
        app.confirmar_pagamento_canonico(
            _contexto(),
            pagamento_id="pay-f7c-card",
            comanda_id=COMANDA,
            metodo=MetodoFechamento.CARTAO_CREDITO,
            valor=Decimal("20.00"),
            expected_payment_version=1,
            idempotency_key="f7c:pay:confirm:card-empty",
            referencia_externa="",
        )

    confirmado = app.confirmar_pagamento_canonico(
        _contexto(),
        pagamento_id="pay-f7c-card",
        comanda_id=COMANDA,
        metodo=MetodoFechamento.CARTAO_CREDITO,
        valor=Decimal("20.00"),
        expected_payment_version=1,
        idempotency_key="f7c:pay:confirm:card",
        referencia_externa="NSU-F7C-123",
    )
    assert confirmado.pagamento.status is PagamentoStatus.PAGO

    with pytest.raises(ConcorrenciaPagamento):
        app.confirmar_pagamento_canonico(
            _contexto(),
            pagamento_id="pay-f7c-card",
            comanda_id=COMANDA,
            metodo=MetodoFechamento.CARTAO_CREDITO,
            valor=Decimal("20.00"),
            expected_payment_version=1,
            idempotency_key="f7c:pay:confirm:card-concurrent",
            referencia_externa="NSU-F7C-456",
        )


def test_pix_fica_pendente_sem_fonte_financeira_validada(tmp_path) -> None:
    _engine, factory, _comanda = _infra(tmp_path, MetodoFechamento.PIX)
    app = AplicacaoSalaoV1(factory, agora=lambda: AGORA)

    criado = app.criar_pagamento_canonico(
        _contexto(),
        pagamento_id="pay-f7c-pix",
        pedido_id=PEDIDO,
        comanda_id=COMANDA,
        metodo=MetodoFechamento.PIX,
        valor=Decimal("20.00"),
        idempotency_key="f7c:pay:create:pix",
    )
    assert criado.pagamento.status is PagamentoStatus.PENDENTE

    with pytest.raises(FonteFinanceiraNaoConfiavel):
        app.confirmar_pagamento_canonico(
            _contexto(),
            pagamento_id="pay-f7c-pix",
            comanda_id=COMANDA,
            metodo=MetodoFechamento.PIX,
            valor=Decimal("20.00"),
            expected_payment_version=1,
            idempotency_key="f7c:pay:confirm:pix",
        )

    with factory() as session:
        row = session.get(PagamentoORM, ("pay-f7c-pix", TENANT, UNIDADE))
        assert row is not None
        assert row.status == PagamentoStatus.PENDENTE.value
        assert Decimal(str(row.valor_pago)) == Decimal("0.00")


def test_financeiro_pode_confirmar_mas_nao_criar_obrigacao(tmp_path) -> None:
    _engine, factory, _comanda = _infra(tmp_path, MetodoFechamento.DINHEIRO)
    app = AplicacaoSalaoV1(factory, agora=lambda: AGORA)

    with pytest.raises(OperacaoPagamentoNaoAutorizada):
        app.criar_pagamento_canonico(
            _contexto(Papel.FINANCEIRO),
            pagamento_id="pay-f7c-financeiro",
            pedido_id=PEDIDO,
            comanda_id=COMANDA,
            metodo=MetodoFechamento.DINHEIRO,
            valor=Decimal("20.00"),
            idempotency_key="f7c:pay:create:financeiro",
        )
