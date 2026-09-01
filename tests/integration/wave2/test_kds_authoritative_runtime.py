from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.kds_runtime import ServicoKDSCanonico
from core.dominio.enums import PedidoStatus
from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.estoque.modelos import (
    ItemSnapshotFicha,
    SnapshotFichaEstoque,
    StatusReserva,
    TipoMovimento,
)
from core.estoque.modelos_orm import ReservaEstoqueORM, SaldoEstoqueORM, StockBase
from core.estoque.servicos import registrar_movimento, reservar_estoque
from core.kds.erros import ErroKDS
from core.kds.modelos_orm import KDSBase, SetorProducaoORM
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    PaymentsBase,
)
from core.pedidos.modelos_orm import ItemPedidoORM, OrdersBase, PedidoORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.eventos.modelos_orm import EventBusBase, OutboxEventoORM
from infra.gerente_ia.modelos_orm import (
    ConsumidorEventosCoreSQLAlchemy,
    CoreRuntimeBase,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.modelos_orm import EventoAuditoriaORM, SecurityBase
from migrations.runner import run_migrations

TENANT = "tenant-kds-runtime"
UNIDADE = "unidade-kds-runtime"
AGORA = datetime(2026, 8, 13, 18, tzinfo=timezone.utc)


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrdersBase.metadata.create_all(engine)
    PaymentsBase.metadata.create_all(engine)
    StockBase.metadata.create_all(engine)
    KDSBase.metadata.create_all(engine)
    EventBusBase.metadata.create_all(engine)
    CoreRuntimeBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _contexto(papel: Papel = Papel.COZINHA) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=f"usuario-{papel.value}",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-kds-{papel.value}",
        solicitado_em=AGORA,
        origem="kds-integration-test",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _seed_pedido(factory, *, pedido_id="pedido-kds", status="confirmado", dois=True):
    with factory() as session:
        pedido = PedidoORM(
            id=pedido_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            origem="pdv",
            canal="pdv",
            status=status,
            cliente_id=None,
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"idem-{pedido_id}",
            request_hash=f"hash-{pedido_id}",
            subtotal=Decimal("40.00" if dois else "20.00"),
            descontos=Decimal("0.00"),
            taxas=Decimal("0.00"),
            total=Decimal("40.00" if dois else "20.00"),
        )
        itens = [
            ItemPedidoORM(
                id=f"item-{pedido_id}-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_id,
                ordem=0,
                produto_id="produto-1",
                nome_produto="Burger KDS",
                quantidade=1,
                preco_unitario=Decimal("20.00"),
                subtotal=Decimal("20.00"),
                observacao=None,
                ficha_versao="v1",
            )
        ]
        if dois:
            itens.append(
                ItemPedidoORM(
                    id=f"item-{pedido_id}-2",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    pedido_id=pedido_id,
                    ordem=1,
                    produto_id="produto-2",
                    nome_produto="Batata KDS",
                    quantidade=1,
                    preco_unitario=Decimal("20.00"),
                    subtotal=Decimal("20.00"),
                    observacao=None,
                    ficha_versao="v1",
                )
            )
        pedido.itens = itens
        session.add(pedido)
        valor_total = Decimal("40.00" if dois else "20.00")
        session.add(
            ObrigacaoPagamentoORM(
                id=f"pagamento-{pedido_id}",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_id,
                comanda_id=None,
                valor_previsto=valor_total,
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
                valor_previsto=valor_total,
                valor_pago=valor_total,
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


def _seed_reserva_estoque(factory, pedido_id="pedido-kds") -> None:
    contexto = _contexto(Papel.ADMINISTRADOR)
    with factory() as session:
        repo = RepositorioLedgerSQLAlchemy(session)
        entrada = registrar_movimento(
            contexto=contexto,
            repositorio=repo,
            insumo_id="insumo-kds",
            tipo=TipoMovimento.ENTRADA,
            quantidade_movimento=Decimal("10"),
            unidade_medida="un",
            origem_tipo="compra",
            origem_id=f"seed:{pedido_id}",
            origem_versao=1,
            idempotency_key=f"seed:{pedido_id}:insumo",
            motivo="seed estoque KDS",
        )
        for evento in entrada.eventos:
            RepositorioOutboxSQLAlchemy(
                session,
                ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir,
            ).adicionar(evento)
        for auditoria in entrada.auditorias:
            RepositorioAuditoriaSQLAlchemy(session).adicionar(auditoria)

        pedido = session.get(PedidoORM, (pedido_id, TENANT, UNIDADE))
        assert pedido is not None
        snapshot = SnapshotFichaEstoque(
            pedido_id=pedido_id,
            versao_ficha="ficha-kds-v1",
            capturado_em=AGORA,
            itens=(
                ItemSnapshotFicha(
                    produto_id="produto-1",
                    item_pedido_id=f"item-{pedido_id}-1",
                    insumo_id="insumo-kds",
                    quantidade_por_unidade=Decimal("2"),
                    quantidade_total=Decimal("2"),
                    unidade_medida="un",
                ),
            ),
        )
        reserva = reservar_estoque(
            contexto=contexto,
            repositorio=repo,
            pedido_id=pedido_id,
            pedido_version=pedido.versao,
            snapshot_ficha=snapshot,
            idempotency_key=f"reserva:{pedido_id}",
        )
        for evento in reserva.eventos:
            RepositorioOutboxSQLAlchemy(
                session,
                ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir,
            ).adicionar(evento)
        for auditoria in reserva.auditorias:
            RepositorioAuditoriaSQLAlchemy(session).adicionar(auditoria)
        session.commit()


def _status_pedido(factory, pedido_id="pedido-kds") -> str:
    with factory() as session:
        row = session.get(PedidoORM, (pedido_id, TENANT, UNIDADE))
        assert row is not None
        return row.status


def test_kds_sincroniza_estado_macro_do_pedido_sem_dar_permissao_extra_a_cozinha():
    _, factory = _infra()
    _seed_pedido(factory)
    contexto = _contexto(Papel.COZINHA)

    with factory() as session:
        servico = ServicoKDSCanonico(session, agora=lambda: AGORA)
        item1 = servico.rotear_item(
            contexto,
            pedido_id="pedido-kds",
            pedido_item_id="item-pedido-kds-1",
            setor_id="setor-quente",
            quantidade=Decimal(1),
            idempotency_key="route-kds-1",
            producao_id="producao-kds-1",
        )
        item2 = servico.rotear_item(
            contexto,
            pedido_id="pedido-kds",
            pedido_item_id="item-pedido-kds-2",
            setor_id="setor-quente",
            quantidade=Decimal(1),
            idempotency_key="route-kds-2",
            producao_id="producao-kds-2",
        )
        assert item1.pedido_status is PedidoStatus.ENVIADO_PRODUCAO
        assert item2.pedido_status is PedidoStatus.ENVIADO_PRODUCAO
        session.commit()

    assert _status_pedido(factory) == "enviado_producao"

    with factory() as session:
        servico = ServicoKDSCanonico(session, agora=lambda: AGORA)
        aceito = servico.transicionar(
            contexto,
            producao_id="producao-kds-1",
            destino="aceita",
            versao_esperada=1,
            idempotency_key="kds-1-aceita",
            precondicoes={"setor_correto": True},
        )
        iniciado = servico.transicionar(
            contexto,
            producao_id="producao-kds-1",
            destino="em_preparo",
            versao_esperada=aceito.item.versao,
            idempotency_key="kds-1-inicia",
            precondicoes={"estoque_resolvido": True, "estacao_apta": True},
        )
        assert iniciado.pedido_status is PedidoStatus.EM_PREPARO
        pronto1 = servico.transicionar(
            contexto,
            producao_id="producao-kds-1",
            destino="pronta",
            versao_esperada=iniciado.item.versao,
            idempotency_key="kds-1-pronta",
            precondicoes={
                "quantidade_concluida": True,
                "checklist_concluido": True,
            },
        )
        assert pronto1.pedido_status is PedidoStatus.EM_PREPARO
        session.commit()

    with factory() as session:
        servico = ServicoKDSCanonico(session, agora=lambda: AGORA)
        aceito = servico.transicionar(
            contexto,
            producao_id="producao-kds-2",
            destino="aceita",
            versao_esperada=1,
            idempotency_key="kds-2-aceita",
            precondicoes={"setor_correto": True},
        )
        iniciado = servico.transicionar(
            contexto,
            producao_id="producao-kds-2",
            destino="em_preparo",
            versao_esperada=aceito.item.versao,
            idempotency_key="kds-2-inicia",
            precondicoes={"estoque_resolvido": True, "estacao_apta": True},
        )
        pronto2 = servico.transicionar(
            contexto,
            producao_id="producao-kds-2",
            destino="pronta",
            versao_esperada=iniciado.item.versao,
            idempotency_key="kds-2-pronta",
            precondicoes={
                "quantidade_concluida": True,
                "checklist_concluido": True,
            },
        )
        assert pronto2.pedido_status is PedidoStatus.PRONTO
        session.commit()

    assert _status_pedido(factory) == "pronto"
    with factory() as session:
        tipos = set(session.scalars(select(OutboxEventoORM.event_type)).all())
        assert "producaoroteada.v1" in tipos
        assert "producaoempreparo.v1" in tipos
        assert "producaopronta.v1" in tipos
        assert "pedido.enviado_producao" in tipos
        assert "pedido.em_preparo" in tipos
        assert "pedido.pronto" in tipos
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) >= 8


def test_inicio_real_de_producao_consume_reserva_uma_vez() -> None:
    _, factory = _infra()
    _seed_pedido(factory, dois=False)
    _seed_reserva_estoque(factory)
    contexto = _contexto(Papel.COZINHA)

    with factory() as session:
        servico = ServicoKDSCanonico(session, agora=lambda: AGORA)
        roteado = servico.rotear_item(
            contexto,
            pedido_id="pedido-kds",
            pedido_item_id="item-pedido-kds-1",
            setor_id="setor-quente",
            quantidade=Decimal(1),
            idempotency_key="route-stock-f4d",
            producao_id="producao-stock-f4d",
        )
        assert roteado.pedido_status is PedidoStatus.ENVIADO_PRODUCAO
        aceito = servico.transicionar(
            contexto,
            producao_id="producao-stock-f4d",
            destino="aceita",
            versao_esperada=1,
            idempotency_key="stock-f4d-aceita",
            precondicoes={"setor_correto": True},
        )
        iniciado = servico.transicionar(
            contexto,
            producao_id="producao-stock-f4d",
            destino="em_preparo",
            versao_esperada=aceito.item.versao,
            idempotency_key="stock-f4d-inicia",
            precondicoes={"estoque_resolvido": True, "estacao_apta": True},
        )
        assert iniciado.pedido_status is PedidoStatus.EM_PREPARO
        session.commit()

    with factory() as session:
        reserva = session.scalar(
            select(ReservaEstoqueORM).where(
                ReservaEstoqueORM.pedido_id == "pedido-kds"
            )
        )
        assert reserva is not None
        assert reserva.status == StatusReserva.CONSUMIDA.value
        saldo = session.get(
            SaldoEstoqueORM,
            (TENANT, UNIDADE, "insumo-kds"),
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal("8")
        assert Decimal(str(saldo.saldo_reservado)) == Decimal("0")


def test_kds_roteamento_e_idempotente_e_nao_duplica_evento_core():
    _, factory = _infra()
    _seed_pedido(factory, dois=False)
    contexto = _contexto()

    with factory() as session:
        servico = ServicoKDSCanonico(session, agora=lambda: AGORA)
        primeiro = servico.rotear_item(
            contexto,
            pedido_id="pedido-kds",
            pedido_item_id="item-pedido-kds-1",
            setor_id="setor-quente",
            quantidade=Decimal(1),
            idempotency_key="route-idem",
            producao_id="producao-idem",
        )
        segundo = servico.rotear_item(
            contexto,
            pedido_id="pedido-kds",
            pedido_item_id="item-pedido-kds-1",
            setor_id="setor-quente",
            quantidade=Decimal(1),
            idempotency_key="route-idem",
            producao_id="producao-idem",
        )
        assert not primeiro.idempotente
        assert segundo.idempotente
        session.commit()

    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(OutboxEventoORM).where(
                OutboxEventoORM.idempotency_key == "route-idem:core"
            )
        ) == 1


def test_kds_falha_de_roteamento_reverte_transicao_derivada_do_pedido():
    _, factory = _infra()
    _seed_pedido(factory, pedido_id="pedido-rollback", dois=False)
    contexto = _contexto()

    with factory() as session:
        servico = ServicoKDSCanonico(session, agora=lambda: AGORA)
        with pytest.raises(ErroKDS) as erro:
            servico.rotear_item(
                contexto,
                pedido_id="pedido-rollback",
                pedido_item_id="item-inexistente",
                setor_id="setor-quente",
                quantidade=Decimal(1),
                idempotency_key="route-rollback",
            )
        assert erro.value.codigo == "pedido_item_inexistente"
        session.rollback()

    assert _status_pedido(factory, "pedido-rollback") == "confirmado"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 0
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 0


def test_kds_nao_roteia_pedido_cancelado():
    _, factory = _infra()
    _seed_pedido(factory, pedido_id="pedido-cancelado", status="cancelado", dois=False)
    contexto = _contexto()
    with factory() as session:
        with pytest.raises(ErroKDS) as erro:
            ServicoKDSCanonico(session, agora=lambda: AGORA).rotear_item(
                contexto,
                pedido_id="pedido-cancelado",
                pedido_item_id="item-pedido-cancelado-1",
                setor_id="setor-quente",
                quantidade=Decimal(1),
                idempotency_key="route-cancelado",
            )
        assert erro.value.codigo == "pedido_fora_fluxo_producao"
        session.rollback()


def test_migration_comercial_0010_cria_tabelas_kds():
    engine = create_engine("sqlite:///:memory:")
    aplicadas = run_migrations(engine)
    assert "0010_kds_authoritative_runtime_v1" in aplicadas
    tabelas = set(inspect(engine).get_table_names())
    assert {"setores_producao_v1", "producao_itens_v1", "eventos_producao_v1"} <= tabelas
