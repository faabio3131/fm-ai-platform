from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.pedidos.modelos_orm import OrdersBase, PedidoORM
from core.salao import (
    ErroSalao,
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
    SalaoBase,
    ServicoSalao,
    StatusComanda,
    StatusMesa,
)
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 8, 11, 13, 30, tzinfo=UTC)


def contexto(papel: Papel = Papel.GERENTE, *, tenant_id: str = "tenant-1") -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id,
        "unidade-1",
        f"ator-{papel.value}",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{papel.value}",
        AGORA,
        "pytest",
        unidades_permitidas=frozenset({"unidade-1"}),
    )


def novo_servico() -> tuple[Session, ServicoSalao]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    OrdersBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)
    session = Session(engine)
    return session, ServicoSalao(RepositorioSalaoSQLAlchemy(session), agora=lambda: AGORA)


def pedido(session: Session, pedido_id: str, total: str, *, tenant_id: str = "tenant-1") -> None:
    valor = Decimal(total)
    session.add(
        PedidoORM(
            id=pedido_id,
            tenant_id=tenant_id,
            unidade_id="unidade-1",
            origem="salao",
            canal="mesa",
            status="confirmado",
            cliente_id=None,
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"idem-{pedido_id}",
            request_hash=f"hash-{pedido_id}",
            subtotal=valor,
            descontos=Decimal("0.00"),
            taxas=Decimal("0.00"),
            total=valor,
        )
    )
    session.flush()


def criar_mesa(servico: ServicoSalao, ctx: ContextoExecucao, mesa_id: str, codigo: str):
    return servico.cadastrar_mesa(
        ctx,
        mesa_id=mesa_id,
        codigo=codigo,
        capacidade=4,
        idempotency_key=f"mesa:{mesa_id}",
    )


def test_fluxo_completo_pagamento_misto_e_fechamento() -> None:
    session, servico = novo_servico()
    ctx = contexto()
    with session.begin():
        mesa1 = criar_mesa(servico, ctx, "mesa-1", "01")
        criar_mesa(servico, ctx, "mesa-2", "02")
        pedido(session, "pedido-1", "40.00")
        pedido(session, "pedido-2", "30.00")
        comanda = servico.abrir_comanda(
            ctx,
            comanda_id="cmd-1",
            numero="C-001",
            mesa_id=mesa1.mesa_id,
            expected_mesa_version=mesa1.versao,
            idempotency_key="abrir:cmd-1",
        )
        servico.adicionar_participante(
            ctx,
            comanda_id=comanda.comanda_id,
            participante_id="p-1",
            apelido="Ana",
            expected_version=comanda.versao,
            idempotency_key="participante:p-1",
        )
        comanda_recarregada = servico.repositorio.obter_comanda(
            "tenant-1", "unidade-1", "cmd-1"
        )
        assert comanda_recarregada is not None
        comanda = comanda_recarregada
        comanda = servico.vincular_pedido(
            ctx,
            comanda_id="cmd-1",
            pedido_id="pedido-1",
            participante_id="p-1",
            expected_version=comanda.versao,
            idempotency_key="vincular:pedido-1",
        )
        comanda = servico.vincular_pedido(
            ctx,
            comanda_id="cmd-1",
            pedido_id="pedido-2",
            expected_version=comanda.versao,
            idempotency_key="vincular:pedido-2",
        )
        assert comanda.total == Decimal("70.00")
        assert comanda.status == StatusComanda.EM_CONSUMO

        mesa1_atual = servico.repositorio.obter_mesa("tenant-1", "unidade-1", "mesa-1")
        mesa2_atual = servico.repositorio.obter_mesa("tenant-1", "unidade-1", "mesa-2")
        assert mesa1_atual is not None and mesa2_atual is not None
        comanda = servico.transferir_comanda(
            ctx,
            comanda_id="cmd-1",
            mesa_destino_id="mesa-2",
            expected_comanda_version=comanda.versao,
            expected_origem_version=mesa1_atual.versao,
            expected_destino_version=mesa2_atual.versao,
            idempotency_key="transferir:cmd-1",
        )
        assert comanda.mesa_id == "mesa-2"

        comanda = servico.solicitar_conta(
            ctx,
            comanda_id="cmd-1",
            expected_version=comanda.versao,
            idempotency_key="conta:cmd-1",
        )
        comanda, parcelas = servico.definir_divisao_pagamento(
            ctx,
            comanda_id="cmd-1",
            expected_version=comanda.versao,
            idempotency_key="dividir:cmd-1",
            divisoes=(
                (MetodoFechamento.PIX, Decimal("40.00"), "p-1"),
                (MetodoFechamento.DINHEIRO, Decimal("30.00"), None),
            ),
        )
        assert sum((p.valor for p in parcelas), Decimal("0.00")) == Decimal("70.00")

        comanda = servico.registrar_pagamento_confirmado(
            ctx,
            comanda_id="cmd-1",
            pagamento_id="pay-1",
            metodo=MetodoFechamento.PIX,
            valor=Decimal("40.00"),
            expected_version=comanda.versao,
            idempotency_key="pay:1",
        )
        assert comanda.status == StatusComanda.PARCIALMENTE_PAGA
        assert comanda.saldo == Decimal("30.00")
        comanda = servico.registrar_pagamento_confirmado(
            ctx,
            comanda_id="cmd-1",
            pagamento_id="pay-2",
            metodo=MetodoFechamento.DINHEIRO,
            valor=Decimal("30.00"),
            expected_version=comanda.versao,
            idempotency_key="pay:2",
        )
        assert comanda.saldo == Decimal("0.00")
        comanda = servico.fechar_comanda(
            ctx,
            comanda_id="cmd-1",
            expected_version=comanda.versao,
            idempotency_key="fechar:cmd-1",
            pedidos_resolvidos=True,
        )
        assert comanda.status == StatusComanda.FECHADA
        mesa2_final = servico.repositorio.obter_mesa("tenant-1", "unidade-1", "mesa-2")
        assert mesa2_final is not None and mesa2_final.status == StatusMesa.LIVRE


def test_separar_e_juntar_nao_duplica_pedido() -> None:
    session, servico = novo_servico()
    ctx = contexto()
    with session.begin():
        m1 = criar_mesa(servico, ctx, "mesa-1", "01")
        m2 = criar_mesa(servico, ctx, "mesa-2", "02")
        for pedido_id, valor in (("p1", "10.00"), ("p2", "20.00"), ("p3", "30.00")):
            pedido(session, pedido_id, valor)
        c1 = servico.abrir_comanda(
            ctx,
            comanda_id="c1",
            numero="C1",
            mesa_id="mesa-1",
            expected_mesa_version=m1.versao,
            idempotency_key="abrir:c1",
        )
        c1 = servico.vincular_pedido(
            ctx, comanda_id="c1", pedido_id="p1", expected_version=c1.versao,
            idempotency_key="v:p1"
        )
        c1 = servico.vincular_pedido(
            ctx, comanda_id="c1", pedido_id="p2", expected_version=c1.versao,
            idempotency_key="v:p2"
        )
        c2 = servico.abrir_comanda(
            ctx,
            comanda_id="c2",
            numero="C2",
            mesa_id="mesa-2",
            expected_mesa_version=m2.versao,
            idempotency_key="abrir:c2",
        )
        c2 = servico.vincular_pedido(
            ctx, comanda_id="c2", pedido_id="p3", expected_version=c2.versao,
            idempotency_key="v:p3"
        )
        separada = servico.separar_comanda(
            ctx,
            origem_id="c1",
            nova_comanda_id="c3",
            novo_numero="C3",
            pedido_ids=("p2",),
            expected_origem_version=c1.versao,
            idempotency_key="separar:c1",
        )
        assert separada.total == Decimal("20.00")
        destino = servico.juntar_comandas(
            ctx,
            origem_id="c3",
            destino_id="c2",
            expected_origem_version=separada.versao,
            expected_destino_version=c2.versao,
            idempotency_key="juntar:c3:c2",
        )
        assert destino.total == Decimal("50.00")
        pedidos_destino = servico.repositorio.listar_pedidos("tenant-1", "unidade-1", "c2")
        assert {item.pedido_id for item in pedidos_destino} == {"p2", "p3"}


def test_multi_tenant_e_concorrencia_falham_fechado() -> None:
    session, servico = novo_servico()
    ctx = contexto()
    with session.begin():
        mesa = criar_mesa(servico, ctx, "mesa-1", "01")
        comanda = servico.abrir_comanda(
            ctx,
            comanda_id="cmd-1",
            numero="C1",
            mesa_id=mesa.mesa_id,
            expected_mesa_version=mesa.versao,
            idempotency_key="abrir:c1",
        )
        with pytest.raises(ErroSalao) as erro:
            servico.solicitar_conta(
                contexto(tenant_id="tenant-2"),
                comanda_id="cmd-1",
                expected_version=comanda.versao,
                idempotency_key="idor",
            )
        assert erro.value.codigo == "comanda_indisponivel"
        with pytest.raises(ErroSalao) as erro:
            servico.solicitar_conta(
                ctx,
                comanda_id="cmd-1",
                expected_version=999,
                idempotency_key="stale",
            )
        assert erro.value.codigo == "comanda_concorrente"
