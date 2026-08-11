from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.garcom import ErroGarcom, ServicoGarcom
from core.kds import RepositorioKDSSQLAlchemy
from core.kds.modelos_orm import KDSBase, ProducaoItemORM, SetorProducaoORM
from core.pedidos.modelos_orm import ItemPedidoORM, OrdersBase, PedidoORM
from core.salao import RepositorioSalaoSQLAlchemy
from core.salao.modelos_orm import ComandaORM, MesaORM, PedidoComandaORM, SalaoBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
TENANT = "tenant-1"
UNIDADE = "unidade-1"


def contexto(
    papel: Papel,
    *,
    usuario_id: str | None = None,
    tenant_id: str = TENANT,
    unidade_id: str = UNIDADE,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id,
        unidade_id,
        usuario_id or f"ator-{papel.value}",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{papel.value}-{usuario_id or 'padrao'}",
        AGORA,
        "teste-garcom",
        unidades_permitidas=frozenset({unidade_id}),
    )


def _pedido(
    pedido_id: str,
    item_id: str,
    *,
    tenant_id: str = TENANT,
    unidade_id: str = UNIDADE,
) -> tuple[PedidoORM, ItemPedidoORM]:
    pedido = PedidoORM(
        id=pedido_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        origem="pdv",
        canal="salao",
        status="enviado_producao",
        cliente_id=None,
        criado_em=AGORA - timedelta(minutes=10),
        atualizado_em=AGORA - timedelta(minutes=5),
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"idem-{pedido_id}",
        request_hash=f"hash-{pedido_id}",
        subtotal=Decimal("20.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("20.00"),
    )
    item = ItemPedidoORM(
        id=item_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        pedido_id=pedido_id,
        ordem=1,
        produto_id=f"produto-{pedido_id}",
        nome_produto=f"Produto {pedido_id}",
        quantidade=1,
        preco_unitario=Decimal("20.00"),
        subtotal=Decimal("20.00"),
        observacao=None,
        ficha_versao="v1",
    )
    pedido.itens = [item]
    return pedido, item


def _seed(session: Session) -> None:
    session.add_all(
        [
            MesaORM(
                id="mesa-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="01",
                nome="Janela",
                capacidade=4,
                status="ocupada",
                ativo=True,
                versao=2,
                criado_em=AGORA - timedelta(hours=1),
                atualizado_em=AGORA - timedelta(minutes=20),
            ),
            MesaORM(
                id="mesa-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="02",
                nome="Centro",
                capacidade=4,
                status="ocupada",
                ativo=True,
                versao=2,
                criado_em=AGORA - timedelta(hours=1),
                atualizado_em=AGORA - timedelta(minutes=20),
            ),
            MesaORM(
                id="mesa-3",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="03",
                nome="Livre",
                capacidade=2,
                status="livre",
                ativo=True,
                versao=1,
                criado_em=AGORA - timedelta(hours=1),
                atualizado_em=AGORA - timedelta(minutes=20),
            ),
            MesaORM(
                id="mesa-x",
                tenant_id="tenant-2",
                unidade_id=UNIDADE,
                codigo="99",
                nome="Outro tenant",
                capacidade=2,
                status="livre",
                ativo=True,
                versao=1,
                criado_em=AGORA - timedelta(hours=1),
                atualizado_em=AGORA - timedelta(minutes=20),
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            ComandaORM(
                id="comanda-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                mesa_id="mesa-1",
                numero="C-001",
                status="em_consumo",
                responsavel_id="garcom-1",
                aberta_em=AGORA - timedelta(minutes=30),
                fechada_em=None,
                total=Decimal("20.00"),
                saldo=Decimal("20.00"),
                recebimento_posterior_autorizado=False,
                versao=2,
            ),
            ComandaORM(
                id="comanda-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                mesa_id="mesa-2",
                numero="C-002",
                status="em_consumo",
                responsavel_id="garcom-2",
                aberta_em=AGORA - timedelta(minutes=25),
                fechada_em=None,
                total=Decimal("20.00"),
                saldo=Decimal("20.00"),
                recebimento_posterior_autorizado=False,
                versao=2,
            ),
        ]
    )
    pedido_1, item_1 = _pedido("pedido-1", "item-1")
    pedido_2, item_2 = _pedido("pedido-2", "item-2")
    session.add_all([pedido_1, pedido_2])
    session.flush()

    session.add_all(
        [
            PedidoComandaORM(
                id="vinculo-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                comanda_id="comanda-1",
                pedido_id=pedido_1.id,
                participante_id=None,
                valor=Decimal("20.00"),
                criado_em=AGORA - timedelta(minutes=20),
            ),
            PedidoComandaORM(
                id="vinculo-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                comanda_id="comanda-2",
                pedido_id=pedido_2.id,
                participante_id=None,
                valor=Decimal("20.00"),
                criado_em=AGORA - timedelta(minutes=18),
            ),
            SetorProducaoORM(
                id="setor-cozinha",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="cozinha",
                nome="Cozinha",
                ordem=1,
                sla_segundos=600,
                ativo=True,
                criado_em=AGORA - timedelta(hours=1),
                atualizado_em=AGORA - timedelta(hours=1),
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            ProducaoItemORM(
                id="prod-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_1.id,
                pedido_item_id=item_1.id,
                setor_id="setor-cozinha",
                status="pronta",
                prioridade=0,
                quantidade=Decimal("1.0000"),
                tentativa=1,
                versao=4,
                criado_em=AGORA - timedelta(minutes=15),
                atualizado_em=AGORA - timedelta(minutes=2),
                pronta_em=AGORA - timedelta(minutes=2),
                responsavel_id="cozinha-1",
                pausa_acumulada_segundos=0,
                idempotency_key="route-prod-1",
                request_hash="hash-prod-1",
            ),
            ProducaoItemORM(
                id="prod-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=pedido_2.id,
                pedido_item_id=item_2.id,
                setor_id="setor-cozinha",
                status="pronta",
                prioridade=0,
                quantidade=Decimal("1.0000"),
                tentativa=1,
                versao=4,
                criado_em=AGORA - timedelta(minutes=14),
                atualizado_em=AGORA - timedelta(minutes=1),
                pronta_em=AGORA - timedelta(minutes=1),
                responsavel_id="cozinha-1",
                pausa_acumulada_segundos=0,
                idempotency_key="route-prod-2",
                request_hash="hash-prod-2",
            ),
        ]
    )
    session.commit()


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    OrdersBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)
    KDSBase.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        yield session


def servico(session: Session) -> ServicoGarcom:
    return ServicoGarcom(
        RepositorioSalaoSQLAlchemy(session),
        RepositorioKDSSQLAlchemy(session),
        agora=lambda: AGORA,
    )


def test_garcom_ve_so_mesas_livres_suas_comandas_e_seu_pronto(session):
    painel = servico(session).listar_painel(
        contexto(Papel.GARCOM, usuario_id="garcom-1")
    )
    assert {mesa.codigo for mesa in painel.mesas} == {"01", "03"}
    assert [comanda.comanda_id for comanda in painel.comandas] == ["comanda-1"]
    assert [alerta.pedido_id for alerta in painel.alertas_prontos] == ["pedido-1"]
    assert painel.alertas_prontos[0].mesa_codigo == "01"


def test_gerente_ve_todo_o_salao_e_todos_os_alertas(session):
    painel = servico(session).listar_painel(contexto(Papel.GERENTE))
    assert {mesa.codigo for mesa in painel.mesas} == {"01", "02", "03"}
    assert {comanda.comanda_id for comanda in painel.comandas} == {
        "comanda-1",
        "comanda-2",
    }
    assert {alerta.pedido_id for alerta in painel.alertas_prontos} == {
        "pedido-1",
        "pedido-2",
    }


def test_garcom_nao_altera_comanda_de_outro_responsavel(session):
    with pytest.raises(ErroGarcom) as erro:
        servico(session).solicitar_conta(
            contexto(Papel.GARCOM, usuario_id="garcom-1"),
            comanda_id="comanda-2",
            expected_version=2,
        )
    assert erro.value.codigo == "comanda_fora_alcada"
    session.rollback()
    comanda = RepositorioSalaoSQLAlchemy(session).obter_comanda(TENANT, UNIDADE, "comanda-2")
    assert comanda is not None
    assert comanda.status.value == "em_consumo"


def test_garcom_solicita_conta_da_propria_comanda(session):
    resultado = servico(session).solicitar_conta(
        contexto(Papel.GARCOM, usuario_id="garcom-1"),
        comanda_id="comanda-1",
        expected_version=2,
        idempotency_key="teste-conta-garcom",
    )
    session.commit()
    assert resultado.status.value == "conta_solicitada"
    assert resultado.versao == 3


def test_isolamento_de_tenant_na_projecao(session):
    painel = servico(session).listar_painel(
        contexto(
            Papel.GARCOM,
            usuario_id="garcom-x",
            tenant_id="tenant-2",
            unidade_id=UNIDADE,
        )
    )
    assert [mesa.codigo for mesa in painel.mesas] == ["99"]
    assert painel.comandas == ()
    assert painel.alertas_prontos == ()
