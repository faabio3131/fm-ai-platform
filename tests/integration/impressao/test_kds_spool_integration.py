from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.impressao_kds import IntegracaoImpressaoKDSV1
from application.kds_transacoes import rotear_item_kds_v1
from core.impressao import (
    DestinoImpressao,
    ImpressoraFake,
    RepositorioSpoolSQLAlchemy,
)
from core.kds import (
    RepositorioAuditoriaEmMemoria,
    RepositorioKDSSQLAlchemy,
    ServicoKDS,
)
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from migrations.runner import run_migrations

AGORA = datetime(2026, 9, 2, 22, 30, tzinfo=timezone.utc)
TENANT = "tenant-f9c"
UNIDADE = "unidade-f9c"
PEDIDO = "pedido-f9c"
ITEM = "item-f9c"
SETOR = "setor-f9c"


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-f9c",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-f9c",
        solicitado_em=AGORA,
        origem="teste_f9c",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _preparar():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with factory() as session:
        session.add(
            PedidoORM(
                id=PEDIDO,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                origem="pdv",
                canal="balcao",
                status="enviado_producao",
                cliente_id=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=1,
                correlation_id="corr-pedido-f9c",
                idempotency_key="pedido-f9c",
                request_hash="hash-pedido-f9c",
                subtotal=Decimal("25.00"),
                descontos=Decimal(0),
                taxas=Decimal(0),
                total=Decimal("25.00"),
            )
        )
        session.add(
            ItemPedidoORM(
                id=ITEM,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=PEDIDO,
                ordem=1,
                produto_id="produto-f9c",
                nome_produto="Burger F9-C",
                quantidade=1,
                preco_unitario=Decimal("25.00"),
                subtotal=Decimal("25.00"),
                observacao="sem cebola",
                ficha_versao="v1",
            )
        )
        session.flush()

        kds = ServicoKDS(
            RepositorioKDSSQLAlchemy(session),
            RepositorioAuditoriaEmMemoria(),
            agora=lambda: AGORA,
        )
        kds.criar_setor(
            _contexto(),
            codigo="CHAPA",
            nome="Chapa F9-C",
            ordem=1,
            sla_segundos=600,
            setor_id=SETOR,
        )
        session.commit()

    destino = DestinoImpressao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        setor_id=SETOR,
        impressora_id="printer-f9c",
        max_tentativas=2,
    )
    integracao = IntegracaoImpressaoKDSV1(
        factory,
        impressora=ImpressoraFake(),
        destinos=(destino,),
        agora=lambda: AGORA,
    )
    return factory, integracao


def test_kds_commitado_cria_spool_idempotente_em_uow_separada() -> None:
    factory, integracao = _preparar()
    contexto = _contexto()

    primeiro = rotear_item_kds_v1(
        session_factory=factory,
        contexto=contexto,
        pedido_id=PEDIDO,
        pedido_item_id=ITEM,
        setor_id=SETOR,
        quantidade=Decimal(1),
        idempotency_key="route-f9c",
        producao_id="producao-f9c",
        integracao_impressao=integracao,
    )
    repetido = rotear_item_kds_v1(
        session_factory=factory,
        contexto=contexto,
        pedido_id=PEDIDO,
        pedido_item_id=ITEM,
        setor_id=SETOR,
        quantidade=Decimal(1),
        idempotency_key="route-f9c",
        producao_id="producao-ignorada-no-replay",
        integracao_impressao=integracao,
    )

    assert primeiro.item.producao_id == repetido.item.producao_id
    assert repetido.idempotente

    with factory() as session:
        jobs = RepositorioSpoolSQLAlchemy(session).listar(TENANT, UNIDADE)

    assert len(jobs) == 1
    assert jobs[0].producao_id == primeiro.item.producao_id
    assert jobs[0].pedido_id == PEDIDO
    assert jobs[0].pedido_item_id == ITEM
    assert "Burger F9-C" in jobs[0].conteudo
    assert "sem cebola" in jobs[0].conteudo


def test_falha_do_spool_nao_desfaz_kds(monkeypatch) -> None:
    factory, integracao = _preparar()
    contexto = _contexto()

    def falhar(**_kwargs):
        raise RuntimeError("spool indisponivel")

    monkeypatch.setattr(integracao, "enfileirar_roteamento", falhar)

    resultado = rotear_item_kds_v1(
        session_factory=factory,
        contexto=contexto,
        pedido_id=PEDIDO,
        pedido_item_id=ITEM,
        setor_id=SETOR,
        quantidade=Decimal(1),
        idempotency_key="route-f9c-falha",
        producao_id="producao-f9c-falha",
        integracao_impressao=integracao,
    )

    with factory() as session:
        producao = RepositorioKDSSQLAlchemy(session).obter_producao(
            TENANT,
            UNIDADE,
            resultado.item.producao_id,
        )
        jobs = RepositorioSpoolSQLAlchemy(session).listar(TENANT, UNIDADE)

    assert producao is not None
    assert producao.status == "aguardando"
    assert jobs == ()
