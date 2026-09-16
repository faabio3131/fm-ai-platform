from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.administracao_proprietario import (
    AplicacaoAdministracaoProprietarioV1,
)
from core.administracao import UnidadeAdministrativa
from core.estoque.modelos_orm import SaldoEstoqueORM
from core.pagamentos.modelos_orm import VendaFinanceiraORM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca.permissoes import Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

AGORA = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    run_migrations(engine)
    return engine


def _owner(factory):
    with factory() as session:
        identidade = RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email="owner-wp018@example.test",
            password="senha-owner-wp018-segura",
            admin_pin="472839",
            tenant_id="tenant-wp018",
            unidade_padrao_id="matriz-wp018",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("matriz-wp018",),
            acesso_admin_sensivel=True,
        )
        session.commit()
    return identidade


def _pedido(
    *,
    pedido_id: str,
    tenant_id: str,
    unidade_id: str,
    total: Decimal,
) -> PedidoORM:
    return PedidoORM(
        id=pedido_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        origem="pdv",
        canal="pdv",
        status="confirmado",
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"idem-{pedido_id}",
        request_hash=f"hash-{pedido_id}",
        subtotal=total,
        descontos=Decimal(0),
        taxas=Decimal(0),
        total=total,
    )


def _venda(
    *,
    venda_id: str,
    pedido_id: str,
    tenant_id: str,
    unidade_id: str,
    valor: Decimal,
) -> VendaFinanceiraORM:
    return VendaFinanceiraORM(
        id=venda_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        pedido_id=pedido_id,
        pagamento_id=None,
        comanda_id=None,
        criterio_codigo="pagamento_liquidado",
        criterio_versao=1,
        valor=valor,
        moeda="BRL",
        metodo="dinheiro",
        reconhecida_em=AGORA,
        correlation_id=f"corr-{venda_id}",
        idempotency_key=f"idem-{venda_id}",
        request_hash=f"hash-{venda_id}",
    )


def test_wp018_dashboard_reconhece_somente_venda_canonica_cmv_uma_vez_e_isola_escopo() -> None:
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = _owner(factory)
    app = AplicacaoAdministracaoProprietarioV1(factory)

    ctx = owner.contexto(
        origem="tests.wp018.dashboard",
        solicitado_em=AGORA,
    )
    app.registrar_acesso(contexto=ctx)

    app.criar_unidade(
        contexto=ctx,
        unidade=UnidadeAdministrativa(
            tenant_id="tenant-wp018",
            unidade_id="filial-wp018",
            codigo="FILIAL",
            nome_fantasia="Filial WP018",
            tipo="filial",
        ),
    )
    app.criar_unidade(
        contexto=ctx,
        unidade=UnidadeAdministrativa(
            tenant_id="tenant-wp018",
            unidade_id="vazia-wp018",
            codigo="VAZIA",
            nome_fantasia="Unidade Vazia WP018",
            tipo="filial",
        ),
    )

    with factory() as session:
        session.execute(
            text(
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (7018, 'Loja WP018')"
            )
        )
        session.execute(
            text(
                "INSERT INTO fm_unidade_loja_legacy_v1 "
                "(tenant_id, unidade_id, loja_id, ativo) "
                "VALUES ('tenant-wp018', 'matriz-wp018', 7018, TRUE)"
            )
        )
        session.execute(
            text(
                "INSERT INTO produtos "
                "(id, loja_id, nome, preco_venda, custo_total_cmv) "
                "VALUES (1018, 7018, 'Produto WP018', 25, 10)"
            )
        )

        reconhecido = _pedido(
            pedido_id="pedido-reconhecido-wp018",
            tenant_id="tenant-wp018",
            unidade_id="matriz-wp018",
            total=Decimal(50),
        )
        nao_reconhecido = _pedido(
            pedido_id="pedido-nao-reconhecido-wp018",
            tenant_id="tenant-wp018",
            unidade_id="matriz-wp018",
            total=Decimal(70),
        )
        filial = _pedido(
            pedido_id="pedido-filial-wp018",
            tenant_id="tenant-wp018",
            unidade_id="filial-wp018",
            total=Decimal(30),
        )

        session.add_all((reconhecido, nao_reconhecido, filial))
        session.flush()

        session.add(
            ItemPedidoORM(
                id="item-reconhecido-wp018",
                tenant_id="tenant-wp018",
                unidade_id="matriz-wp018",
                pedido_id="pedido-reconhecido-wp018",
                ordem=1,
                produto_id="legacy:produto:1018",
                nome_produto="Produto WP018",
                quantidade=2,
                preco_unitario=Decimal(25),
                subtotal=Decimal(50),
                observacao=None,
                ficha_versao=None,
            )
        )

        # Este item pertence a pedido NÃO reconhecido financeiramente.
        # Portanto não pode entrar nem na receita nem no CMV do dashboard.
        session.add(
            ItemPedidoORM(
                id="item-nao-reconhecido-wp018",
                tenant_id="tenant-wp018",
                unidade_id="matriz-wp018",
                pedido_id="pedido-nao-reconhecido-wp018",
                ordem=1,
                produto_id="legacy:produto:1018",
                nome_produto="Produto WP018",
                quantidade=10,
                preco_unitario=Decimal(7),
                subtotal=Decimal(70),
                observacao=None,
                ficha_versao=None,
            )
        )

        session.add(
            _venda(
                venda_id="venda-matriz-wp018",
                pedido_id="pedido-reconhecido-wp018",
                tenant_id="tenant-wp018",
                unidade_id="matriz-wp018",
                valor=Decimal(50),
            )
        )

        session.add(
            _venda(
                venda_id="venda-filial-wp018",
                pedido_id="pedido-filial-wp018",
                tenant_id="tenant-wp018",
                unidade_id="filial-wp018",
                valor=Decimal(30),
            )
        )

        # Outro tenant: deve ser completamente invisível.
        session.add(
            _venda(
                venda_id="venda-outro-tenant-wp018",
                pedido_id="pedido-outro-tenant-wp018",
                tenant_id="tenant-outro-wp018",
                unidade_id="unidade-outro-wp018",
                valor=Decimal(999),
            )
        )

        # Estoque é operação/ativo físico, não receita.
        session.add(
            SaldoEstoqueORM(
                tenant_id="tenant-wp018",
                unidade_id="matriz-wp018",
                insumo_id="insumo-wp018",
                saldo_fisico=Decimal(1000),
                saldo_reservado=Decimal(100),
                versao=1,
            )
        )

        session.commit()

    matriz = app.painel_executivo(
        contexto=ctx,
        unidades=("matriz-wp018",),
    )

    assert matriz.financeiro.vendas_reconhecidas == Decimal(50)
    assert matriz.financeiro.quantidade_vendas == 1
    assert matriz.financeiro.ticket_medio == Decimal(50)

    # CMV = custo 10 x quantidade 2. Pedido não reconhecido não entra.
    assert matriz.financeiro.cmv_estimado_atual == Decimal(20)
    assert matriz.financeiro.margem_estimada_atual == Decimal(30)
    assert matriz.financeiro.cobertura_cmv_itens_pct == Decimal(100)

    # Estoque alto não altera a receita.
    assert matriz.operacional.estoque_fisico_total == Decimal(1000)
    assert matriz.financeiro.vendas_reconhecidas == Decimal(50)

    consolidado = app.painel_executivo(
        contexto=ctx,
        unidades=("matriz-wp018", "filial-wp018"),
    )
    assert consolidado.financeiro.vendas_reconhecidas == Decimal(80)
    assert consolidado.financeiro.quantidade_vendas == 2
    assert consolidado.financeiro.cmv_estimado_atual == Decimal(20)
    assert consolidado.financeiro.margem_estimada_atual == Decimal(60)

    vazio = app.painel_executivo(
        contexto=ctx,
        unidades=("vazia-wp018",),
    )
    assert vazio.financeiro.vendas_reconhecidas == Decimal(0)
    assert vazio.financeiro.quantidade_vendas == 0
    assert vazio.financeiro.ticket_medio == Decimal(0)
    assert vazio.financeiro.cmv_estimado_atual is None
    assert vazio.financeiro.margem_estimada_atual is None
    assert vazio.operacional.pedidos == 0
    assert vazio.operacional.estoque_fisico_total == Decimal(0)
