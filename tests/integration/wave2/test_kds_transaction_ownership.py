from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import kds_transacoes
from core.dominio.enums import PedidoStatus
from core.kds.modelos_orm import ProducaoItemORM, SetorProducaoORM
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
)
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca import (
    MATRIZ_PADRAO,
    ContextoExecucao,
    Papel,
)
from infra.eventos.modelos_orm import OutboxEventoORM
from migrations.runner import run_migrations

TENANT = "tenant-sd1e-kds"
UNIDADE = "loja-sd1e-kds"
AGORA = datetime(
    2026,
    8,
    27,
    18,
    30,
    tzinfo=timezone.utc,
)


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    run_migrations(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    return engine, factory


def _contexto() -> ContextoExecucao:
    papel = Papel.ADMINISTRADOR

    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-sd1e-kds",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id="corr-sd1e-kds",
        solicitado_em=AGORA,
        origem="tests.sd1e.kds",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _seed(
    factory,
    *,
    pedido_id: str,
) -> None:
    with factory() as session:
        pedido = PedidoORM(
            id=pedido_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            origem="pdv",
            canal="pdv",
            status="confirmado",
            cliente_id=None,
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"pedido-{pedido_id}",
            request_hash=f"hash-{pedido_id}",
            subtotal=Decimal("20.00"),
            descontos=Decimal("0.00"),
            taxas=Decimal("0.00"),
            total=Decimal("20.00"),
        )

        pedido.itens = [
            ItemPedidoORM(
                id=f"item-{pedido_id}",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_id,
                ordem=0,
                produto_id="produto-kds",
                nome_produto="Produto KDS",
                quantidade=1,
                preco_unitario=Decimal("20.00"),
                subtotal=Decimal("20.00"),
                observacao=None,
                ficha_versao="v1",
            )
        ]

        session.add(pedido)

        session.add(
            ObrigacaoPagamentoORM(
                id=f"pagamento-{pedido_id}",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_id,
                comanda_id=None,
                valor_previsto=Decimal("20.00"),
                moeda="BRL",
                criado_em=AGORA,
                versao=1,
                correlation_id=f"corr-{pedido_id}",
                idempotency_key=f"obrigacao-{pedido_id}",
                request_hash=f"hash-obrigacao-{pedido_id}",
            )
        )

        session.add(
            PagamentoORM(
                id=f"pagamento-{pedido_id}",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_id,
                comanda_id=None,
                status="pago",
                metodo="dinheiro",
                valor_previsto=Decimal("20.00"),
                valor_pago=Decimal("20.00"),
                valor_estornado=Decimal("0.00"),
                saldo=Decimal("0.00"),
                moeda="BRL",
                recebimento_posterior=False,
                provedor=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=1,
                correlation_id=f"corr-{pedido_id}",
                idempotency_key=f"pagamento-{pedido_id}",
                request_hash=f"hash-pagamento-{pedido_id}",
            )
        )

        session.add(
            SetorProducaoORM(
                id="setor-quente",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="quente",
                nome="Cozinha quente",
                ordem=1,
                sla_segundos=600,
                ativo=True,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )

        session.commit()


def _rotear(
    factory,
    *,
    pedido_id: str,
    producao_id: str,
):
    return kds_transacoes.rotear_item_kds_v1(
        session_factory=factory,
        contexto=_contexto(),
        pedido_id=pedido_id,
        pedido_item_id=f"item-{pedido_id}",
        setor_id="setor-quente",
        quantidade=Decimal(1),
        idempotency_key=f"route-{pedido_id}",
        prioridade=1,
        producao_id=producao_id,
    )


def test_application_kds_roteamento_commita_integralmente() -> None:
    engine, factory = _infra()
    pedido_id = "pedido-kds-commit"

    _seed(
        factory,
        pedido_id=pedido_id,
    )

    resultado = _rotear(
        factory,
        pedido_id=pedido_id,
        producao_id="producao-kds-commit",
    )

    assert (
        resultado.pedido_status
        is PedidoStatus.ENVIADO_PRODUCAO
    )

    with Session(engine) as session:
        producao = session.scalar(
            select(ProducaoItemORM).where(
                ProducaoItemORM.id
                == "producao-kds-commit",
                ProducaoItemORM.tenant_id == TENANT,
                ProducaoItemORM.unidade_id == UNIDADE,
            )
        )

        assert producao is not None

        pedido = session.scalar(
            select(PedidoORM).where(
                PedidoORM.id == pedido_id,
                PedidoORM.tenant_id == TENANT,
                PedidoORM.unidade_id == UNIDADE,
            )
        )

        assert pedido is not None
        assert pedido.status == "enviado_producao"

        assert session.scalar(
            select(func.count())
            .select_from(OutboxEventoORM)
        ) > 0


def test_application_kds_rollback_remove_persistencia_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _infra()
    pedido_id = "pedido-kds-rollback"

    _seed(
        factory,
        pedido_id=pedido_id,
    )

    real = (
        kds_transacoes.ServicoKDSCanonico.rotear_item
    )

    def falhar_depois_do_write(
        self,
        *args,
        **kwargs,
    ):
        real(
            self,
            *args,
            **kwargs,
        )

        raise RuntimeError(
            "falha_depois_do_write_kds"
        )

    monkeypatch.setattr(
        kds_transacoes.ServicoKDSCanonico,
        "rotear_item",
        falhar_depois_do_write,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_write_kds",
    ):
        _rotear(
            factory,
            pedido_id=pedido_id,
            producao_id="producao-kds-rollback",
        )

    with Session(engine) as session:
        producao = session.scalar(
            select(ProducaoItemORM).where(
                ProducaoItemORM.id
                == "producao-kds-rollback",
                ProducaoItemORM.tenant_id == TENANT,
                ProducaoItemORM.unidade_id == UNIDADE,
            )
        )

        assert producao is None

        pedido = session.scalar(
            select(PedidoORM).where(
                PedidoORM.id == pedido_id,
                PedidoORM.tenant_id == TENANT,
                PedidoORM.unidade_id == UNIDADE,
            )
        )

        assert pedido is not None
        assert pedido.status == "confirmado"

        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEventoORM)
            )
            == 0
        )


def test_application_kds_transicao_commita_e_preserva_replay() -> None:
    engine, factory = _infra()
    pedido_id = "pedido-kds-transition"

    _seed(
        factory,
        pedido_id=pedido_id,
    )

    _rotear(
        factory,
        pedido_id=pedido_id,
        producao_id="producao-kds-transition",
    )

    primeira = kds_transacoes.transicionar_kds_v1(
        session_factory=factory,
        contexto=_contexto(),
        producao_id="producao-kds-transition",
        destino="aceita",
        versao_esperada=1,
        idempotency_key="transition-kds-aceita",
        precondicoes={"setor_correto": True},
    )

    assert primeira.item.status == "aceita"
    assert primeira.idempotente is False

    replay = kds_transacoes.transicionar_kds_v1(
        session_factory=factory,
        contexto=_contexto(),
        producao_id="producao-kds-transition",
        destino="aceita",
        versao_esperada=1,
        idempotency_key="transition-kds-aceita",
        precondicoes={"setor_correto": True},
    )

    assert replay.idempotente is True

    with Session(engine) as session:
        producao = session.scalar(
            select(ProducaoItemORM).where(
                ProducaoItemORM.id
                == "producao-kds-transition",
                ProducaoItemORM.tenant_id == TENANT,
                ProducaoItemORM.unidade_id == UNIDADE,
            )
        )

        assert producao is not None
        assert producao.status == "aceita"
