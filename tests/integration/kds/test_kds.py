from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.kds import (
    CacheFilaKDS,
    ErroKDS,
    KDSBase,
    RepositorioAuditoriaEmMemoria,
    RepositorioKDSSQLAlchemy,
    ServicoKDS,
)
from core.pedidos.modelos_orm import ItemPedidoORM, OrdersBase, PedidoORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def contexto(papel=Papel.ADMINISTRADOR, *, tenant="tenant-1", unidade="unidade-1"):
    return ContextoExecucao(
        tenant,
        unidade,
        f"ator-{papel.value}",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{papel.value}",
        AGORA,
        "teste-kds",
        unidades_permitidas=frozenset({unidade}),
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    OrdersBase.metadata.create_all(engine)
    KDSBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as sessao:
        yield sessao


def seed_item(session, pedido_id, item_id, ordem=1):
    session.add(
        PedidoORM(
            id=pedido_id,
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            origem="pdv",
            canal="balcao",
            status="enviado_producao",
            cliente_id=None,
            criado_em=AGORA - timedelta(minutes=2),
            atualizado_em=AGORA - timedelta(minutes=2),
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"pedido-{pedido_id}",
            request_hash=f"hash-{pedido_id}",
            subtotal=Decimal("20.00"),
            descontos=Decimal("0.00"),
            taxas=Decimal("0.00"),
            total=Decimal("20.00"),
        )
    )
    session.add(
        ItemPedidoORM(
            id=item_id,
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            pedido_id=pedido_id,
            ordem=ordem,
            produto_id=f"produto-{item_id}",
            nome_produto=f"Produto {item_id}",
            quantidade=1,
            preco_unitario=Decimal("20.00"),
            subtotal=Decimal("20.00"),
            observacao=None,
            ficha_versao="v1",
        )
    )
    session.flush()


def servico(session, *, cache=None):
    auditoria = RepositorioAuditoriaEmMemoria()
    return (
        ServicoKDS(
            RepositorioKDSSQLAlchemy(session),
            auditoria,
            cache=cache,
            agora=lambda: AGORA,
        ),
        auditoria,
    )


def preparar_multissetor(session):
    seed_item(session, "pedido-quente", "item-quente")
    seed_item(session, "pedido-bebida", "item-bebida")
    svc, _ = servico(session)
    admin = contexto()
    quente = svc.criar_setor(
        admin,
        codigo="quente",
        nome="Cozinha quente",
        ordem=1,
        sla_segundos=600,
        setor_id="setor-quente",
    )
    bebidas = svc.criar_setor(
        admin,
        codigo="bebidas",
        nome="Bebidas",
        ordem=2,
        sla_segundos=180,
        setor_id="setor-bebidas",
    )
    quente_item = svc.rotear_item(
        admin,
        pedido_id="pedido-quente",
        pedido_item_id="item-quente",
        setor_id=quente.setor_id,
        quantidade=Decimal("1.0000"),
        prioridade=1,
        idempotency_key="route-quente",
        producao_id="prod-quente",
    )
    bebida_item = svc.rotear_item(
        admin,
        pedido_id="pedido-bebida",
        pedido_item_id="item-bebida",
        setor_id=bebidas.setor_id,
        quantidade=Decimal("1.0000"),
        prioridade=10,
        idempotency_key="route-bebida",
        producao_id="prod-bebida",
    )
    return svc, quente, bebidas, quente_item, bebida_item


def test_multissetor_isola_filas_ordena_prioridade_e_roteamento_e_idempotente(session):
    svc, quente, bebidas, quente_item, bebida_item = preparar_multissetor(session)
    admin = contexto()

    geral = svc.listar_fila(admin)
    assert [i.producao.producao_id for i in geral.itens] == ["prod-bebida", "prod-quente"]
    assert [i.producao.producao_id for i in svc.listar_fila(admin, setor_id=quente.setor_id).itens] == [
        "prod-quente"
    ]
    assert [i.producao.producao_id for i in svc.listar_fila(admin, setor_id=bebidas.setor_id).itens] == [
        "prod-bebida"
    ]

    repetido = svc.rotear_item(
        admin,
        pedido_id="pedido-quente",
        pedido_item_id="item-quente",
        setor_id=quente.setor_id,
        quantidade=Decimal("1.0000"),
        prioridade=1,
        idempotency_key="route-quente",
        producao_id="outro-id-ignorado",
    )
    assert repetido.producao_id == quente_item.producao_id

    with pytest.raises(ErroKDS) as conflito:
        svc.rotear_item(
            admin,
            pedido_id="pedido-quente",
            pedido_item_id="item-quente",
            setor_id=quente.setor_id,
            quantidade=Decimal("2.0000"),
            prioridade=1,
            idempotency_key="route-quente",
        )
    assert conflito.value.codigo == "conflito_idempotencia"
    assert bebida_item.setor_id != quente_item.setor_id


def test_transicoes_precondicoes_idempotencia_concorrencia_auditoria_e_retirada(session):
    svc, _, _, quente_item, _ = preparar_multissetor(session)
    cozinha = contexto(Papel.COZINHA)

    aceito = svc.transicionar(
        cozinha,
        producao_id=quente_item.producao_id,
        destino="aceita",
        versao_esperada=1,
        idempotency_key="aceitar-quente",
        precondicoes={"setor_correto": True},
    )
    assert aceito.item.status == "aceita" and aceito.item.versao == 2

    repetido = svc.transicionar(
        cozinha,
        producao_id=quente_item.producao_id,
        destino="aceita",
        versao_esperada=1,
        idempotency_key="aceitar-quente",
        precondicoes={"setor_correto": True},
    )
    assert repetido.idempotente

    with pytest.raises(ErroKDS) as conflito:
        svc.transicionar(
            cozinha,
            producao_id=quente_item.producao_id,
            destino="em_preparo",
            versao_esperada=2,
            idempotency_key="aceitar-quente",
            precondicoes={"estoque_resolvido": True, "estacao_apta": True},
        )
    assert conflito.value.codigo == "conflito_idempotencia"

    iniciado = svc.transicionar(
        cozinha,
        producao_id=quente_item.producao_id,
        destino="em_preparo",
        versao_esperada=2,
        idempotency_key="iniciar-quente",
        precondicoes={"estoque_resolvido": True, "estacao_apta": True},
    )
    assert iniciado.item.iniciada_em == AGORA

    with pytest.raises(ErroKDS) as concorrente:
        svc.transicionar(
            cozinha,
            producao_id=quente_item.producao_id,
            destino="pausada",
            versao_esperada=2,
            idempotency_key="stale-quente",
            motivo="equipamento",
        )
    assert concorrente.value.codigo == "producao_concorrente"

    with pytest.raises(ErroKDS) as sem_motivo:
        svc.transicionar(
            cozinha,
            producao_id=quente_item.producao_id,
            destino="pausada",
            versao_esperada=3,
            idempotency_key="pausa-sem-motivo",
        )
    assert sem_motivo.value.codigo == "motivo_obrigatorio"

    pausado = svc.transicionar(
        cozinha,
        producao_id=quente_item.producao_id,
        destino="pausada",
        versao_esperada=3,
        idempotency_key="pausar-quente",
        motivo="equipamento",
    )
    assert pausado.item.status == "pausada"

    retomado = svc.transicionar(
        cozinha,
        producao_id=quente_item.producao_id,
        destino="em_preparo",
        versao_esperada=4,
        idempotency_key="retomar-quente",
        precondicoes={"impedimento_resolvido": True},
    )
    assert retomado.item.status == "em_preparo"

    with pytest.raises(ErroKDS) as checklist:
        svc.transicionar(
            cozinha,
            producao_id=quente_item.producao_id,
            destino="pronta",
            versao_esperada=5,
            idempotency_key="pronta-incompleta",
            precondicoes={"quantidade_concluida": True},
        )
    assert checklist.value.codigo == "precondicao_nao_atendida"

    pronto = svc.transicionar(
        cozinha,
        producao_id=quente_item.producao_id,
        destino="pronta",
        versao_esperada=5,
        idempotency_key="pronto-quente",
        precondicoes={"quantidade_concluida": True, "checklist_concluido": True},
    )
    assert pronto.item.status == "pronta"

    expedicao = contexto(Papel.EXPEDICAO)
    retirado = svc.transicionar(
        expedicao,
        producao_id=quente_item.producao_id,
        destino="retirada",
        versao_esperada=6,
        idempotency_key="retirar-quente",
        precondicoes={"conferencia_realizada": True, "posse_transferida": True},
    )
    assert retirado.item.status == "retirada"
    assert retirado.item.retirada_em == AGORA


def test_fila_offline_usa_ultimo_snapshot_e_fica_somente_leitura(session, monkeypatch):
    cache = CacheFilaKDS()
    svc, _, _, _, _ = preparar_multissetor(session)
    svc.cache = cache
    admin = contexto()
    online = svc.listar_fila(admin)
    assert online.itens

    def falhar(*args, **kwargs):
        raise OperationalError("select", {}, Exception("offline"))

    monkeypatch.setattr(svc.repositorio, "listar_fila", falhar)
    degradado = svc.listar_fila_tolerante(admin)
    assert degradado.degradado is True
    assert degradado.somente_leitura is True
    assert degradado.motivo_degradacao == "persistencia_indisponivel"
    assert [i.producao.producao_id for i in degradado.itens] == [
        i.producao.producao_id for i in online.itens
    ]
