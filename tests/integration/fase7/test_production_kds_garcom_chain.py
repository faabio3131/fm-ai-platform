from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.garcom import ServicoGarcom
from core.kds import (
    KDSBase,
    RepositorioAuditoriaEmMemoria,
    RepositorioKDSSQLAlchemy,
    ServicoKDS,
)
from core.pedidos.modelos_orm import ItemPedidoORM, OrdersBase, PedidoORM
from core.salao import RepositorioSalaoSQLAlchemy, SalaoBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 9, 2, 15, 30, tzinfo=UTC)
TENANT = "tenant-f7e"
UNIDADE = "unidade-f7e"
GARCOM = "garcom-f7e"
PEDIDO = "pedido-f7e"
ITEM = "item-f7e"


def _contexto(papel: Papel, usuario_id: str | None = None) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=usuario_id or f"ator-{papel.value}",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-f7e-{papel.value}",
        solicitado_em=AGORA,
        origem="tests.f7e.production_chain",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _seed_pedido(session: Session) -> None:
    pedido = PedidoORM(
        id=PEDIDO,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="salao",
        canal="mesa",
        status="enviado_producao",
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id="corr-pedido-f7e",
        idempotency_key="idem-pedido-f7e",
        request_hash="hash-pedido-f7e",
        subtotal=Decimal("32.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("32.00"),
    )
    pedido.itens = [
        ItemPedidoORM(
            id=ITEM,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=PEDIDO,
            ordem=1,
            produto_id="produto-f7e",
            nome_produto="Prato F7-E",
            quantidade=1,
            preco_unitario=Decimal("32.00"),
            subtotal=Decimal("32.00"),
            observacao=None,
            ficha_versao="v1",
        )
    ]
    session.add(pedido)
    session.flush()


def test_pedido_roteado_no_kds_pronto_alerta_garcom_e_conta() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    OrdersBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)
    KDSBase.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        repo_salao = RepositorioSalaoSQLAlchemy(session)
        repo_kds = RepositorioKDSSQLAlchemy(session)
        garcom = ServicoGarcom(repo_salao, repo_kds, agora=lambda: AGORA)
        kds = ServicoKDS(
            repo_kds,
            RepositorioAuditoriaEmMemoria(),
            agora=lambda: AGORA,
        )
        ctx_garcom = _contexto(Papel.GARCOM, GARCOM)
        ctx_admin = _contexto(Papel.ADMINISTRADOR)

        # 1. Garçom abre a mesa/comanda sob a própria identidade.
        mesa = garcom.salao.cadastrar_mesa(
            ctx_admin,
            mesa_id="mesa-f7e",
            codigo="E7",
            capacidade=4,
            idempotency_key="f7e:mesa",
        )
        comanda = garcom.abrir_comanda(
            ctx_garcom,
            mesa_id=mesa.mesa_id,
            expected_mesa_version=mesa.versao,
            numero="F7E-001",
            comanda_id="comanda-f7e",
            idempotency_key="f7e:abrir",
        )

        # 2. Pedido canônico existente é vinculado ao Salão; não é copiado.
        _seed_pedido(session)
        comanda = garcom.vincular_pedido(
            ctx_garcom,
            comanda_id=comanda.comanda_id,
            pedido_id=PEDIDO,
            expected_version=comanda.versao,
            idempotency_key="f7e:vincular",
        )
        assert comanda.total == Decimal("32.00")

        # 3. O KDS autoritativo cria setor e roteia o item real.
        setor = kds.criar_setor(
            ctx_admin,
            codigo="cozinha-f7e",
            nome="Cozinha F7-E",
            ordem=1,
            sla_segundos=600,
            setor_id="setor-f7e",
        )
        producao = kds.rotear_item(
            ctx_admin,
            pedido_id=PEDIDO,
            pedido_item_id=ITEM,
            setor_id=setor.setor_id,
            quantidade=Decimal("1.0000"),
            idempotency_key="f7e:route",
            producao_id="producao-f7e",
        )
        fila = kds.listar_fila(ctx_admin, setor_id=setor.setor_id)
        assert [item.producao.producao_id for item in fila.itens] == [producao.producao_id]
        assert fila.itens[0].producao.status == "aguardando"

        # 4. A produção percorre as transições oficiais; nada é semeado como pronta.
        aceita = kds.transicionar(
            ctx_admin,
            producao_id=producao.producao_id,
            destino="aceita",
            versao_esperada=1,
            idempotency_key="f7e:aceita",
            precondicoes={"setor_correto": True},
        )
        preparo = kds.transicionar(
            ctx_admin,
            producao_id=producao.producao_id,
            destino="em_preparo",
            versao_esperada=aceita.item.versao,
            idempotency_key="f7e:preparo",
            precondicoes={"estoque_resolvido": True, "estacao_apta": True},
        )
        pronta = kds.transicionar(
            ctx_admin,
            producao_id=producao.producao_id,
            destino="pronta",
            versao_esperada=preparo.item.versao,
            idempotency_key="f7e:pronta",
            precondicoes={
                "quantidade_concluida": True,
                "checklist_concluido": True,
            },
        )
        assert pronta.item.status == "pronta"

        # 5. O Garçom deriva o alerta do KDS apenas para a própria comanda.
        painel = garcom.listar_painel(ctx_garcom)
        assert [alerta.pedido_id for alerta in painel.alertas_prontos] == [PEDIDO]
        alerta = painel.alertas_prontos[0]
        assert alerta.setor_id == setor.setor_id
        assert alerta.comanda_id == comanda.comanda_id
        assert alerta.mesa_codigo == "E7"

        outro = garcom.listar_painel(_contexto(Papel.GARCOM, "garcom-outro"))
        assert outro.alertas_prontos == ()

        # 6. Após o pronto, o próprio Garçom solicita a conta; financeiro segue separado.
        conta = garcom.solicitar_conta(
            ctx_garcom,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="f7e:conta",
        )
        assert conta.status.value == "conta_solicitada"
        assert conta.saldo == Decimal("32.00")

        session.commit()
