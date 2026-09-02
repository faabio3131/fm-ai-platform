"""Seed efêmero do F8-E para homologação KDS no runtime comercial PostgreSQL.

Exclusivo de CI/staging descartável. Não habilita FM_AI_TEST_MODE e não cria
produção KDS antecipadamente: o roteamento deve ocorrer pelo browser em app.py.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker

from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, TipoMovimento
from core.estoque.servicos import registrar_movimento, reservar_estoque
from core.kds import RepositorioAuditoriaEmMemoria, RepositorioKDSSQLAlchemy, ServicoKDS
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import ConsumidorEventosCoreSQLAlchemy
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from migrations.runner import run_migrations

TENANT = "tenant-f8e"
UNIDADE = "unidade-f8e"
LOJA_ID = 8001
AGORA = datetime(2026, 9, 2, 18, 0, tzinfo=UTC)

COZINHA_EMAIL = os.environ["F8E_COZINHA_EMAIL"]
COZINHA_PASSWORD = os.environ["F8E_COZINHA_PASSWORD"]
GARCOM_EMAIL = os.environ["F8E_GARCOM_EMAIL"]
GARCOM_PASSWORD = os.environ["F8E_GARCOM_PASSWORD"]


def _contexto(papel: Papel, usuario_id: str) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=usuario_id,
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-f8e-{usuario_id}",
        solicitado_em=AGORA,
        origem="scripts.seed_f8e_commercial_runtime",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _garantir_loja_legacy(session: Session) -> None:
    metadata = MetaData()
    lojas = Table("lojas", metadata, autoload_with=session.connection())
    mapping = Table(
        "fm_unidade_loja_legacy_v1",
        metadata,
        autoload_with=session.connection(),
    )
    loja = session.execute(
        select(lojas.c.id).where(lojas.c.id == LOJA_ID)
    ).scalar_one_or_none()
    if loja is None:
        session.execute(
            insert(lojas).values(
                id=LOJA_ID,
                nome_fantasia="Loja F8-E KDS Staging",
            )
        )
    vinculo = session.execute(
        select(mapping.c.tenant_id)
        .where(mapping.c.tenant_id == TENANT)
        .where(mapping.c.unidade_id == UNIDADE)
    ).scalar_one_or_none()
    if vinculo is None:
        session.execute(
            insert(mapping).values(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                loja_id=LOJA_ID,
                ativo=True,
            )
        )


def _garantir_identidades(session: Session) -> None:
    repo = RepositorioIdentidadesSQLAlchemy(session)
    if repo.obter_por_email(COZINHA_EMAIL) is None:
        repo.criar_usuario(
            email=COZINHA_EMAIL,
            password=COZINHA_PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.COZINHA,),
            unidades_permitidas=(UNIDADE,),
            usuario_id="cozinha-f8e",
        )
    if repo.obter_por_email(GARCOM_EMAIL) is None:
        repo.criar_usuario(
            email=GARCOM_EMAIL,
            password=GARCOM_PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GARCOM,),
            unidades_permitidas=(UNIDADE,),
            usuario_id="garcom-f8e",
        )


def _garantir_pedido(session: Session) -> PedidoORM:
    pedido = session.get(PedidoORM, ("pedido-f8e", TENANT, UNIDADE))
    if pedido is not None:
        return pedido

    pedido = PedidoORM(
        id="pedido-f8e",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="pdv",
        canal="pdv",
        status="confirmado",
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id="corr-pedido-f8e",
        idempotency_key="pedido-f8e",
        request_hash="hash-pedido-f8e",
        subtotal=Decimal("20.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("20.00"),
    )
    pedido.itens = [
        ItemPedidoORM(
            id="item-f8e",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=pedido.id,
            ordem=0,
            produto_id="produto-f8e",
            nome_produto="Burger F8-E",
            quantidade=1,
            preco_unitario=Decimal("20.00"),
            subtotal=Decimal("20.00"),
            observacao=None,
            ficha_versao="ficha-f8e-v1",
        )
    ]
    session.add(pedido)
    session.flush()
    return pedido


def _garantir_setor(session: Session) -> None:
    contexto = _contexto(Papel.ADMINISTRADOR, "admin-seed-f8e")
    repo = RepositorioKDSSQLAlchemy(session)
    if repo.obter_setor(TENANT, UNIDADE, "setor-f8e") is not None:
        return
    ServicoKDS(
        repo,
        RepositorioAuditoriaEmMemoria(),
        agora=lambda: AGORA,
    ).criar_setor(
        contexto,
        codigo="cozinha-f8e",
        nome="Cozinha F8-E",
        ordem=1,
        sla_segundos=600,
        setor_id="setor-f8e",
    )


def _persistir_resultado_estoque(session: Session, resultado) -> None:
    outbox = RepositorioOutboxSQLAlchemy(
        session,
        ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir,
    )
    auditoria = RepositorioAuditoriaSQLAlchemy(session)
    for evento in resultado.eventos:
        outbox.adicionar(evento)
    for registro in resultado.auditorias:
        auditoria.adicionar(registro)


def _garantir_reserva_estoque(session: Session, pedido: PedidoORM) -> None:
    repo = RepositorioLedgerSQLAlchemy(session)
    contexto = _contexto(Papel.ADMINISTRADOR, "admin-stock-f8e")

    entrada = registrar_movimento(
        contexto=contexto,
        repositorio=repo,
        insumo_id="insumo-f8e",
        tipo=TipoMovimento.ENTRADA,
        quantidade_movimento=Decimal(10),
        unidade_medida="un",
        origem_tipo="compra",
        origem_id="seed:f8e",
        origem_versao=1,
        idempotency_key="seed:f8e:insumo",
        motivo="seed estoque F8-E",
    )
    _persistir_resultado_estoque(session, entrada)

    snapshot = SnapshotFichaEstoque(
        pedido_id=pedido.id,
        versao_ficha="ficha-f8e-v1",
        capturado_em=AGORA,
        itens=(
            ItemSnapshotFicha(
                produto_id="produto-f8e",
                item_pedido_id="item-f8e",
                insumo_id="insumo-f8e",
                quantidade_por_unidade=Decimal(2),
                quantidade_total=Decimal(2),
                unidade_medida="un",
            ),
        ),
    )
    reserva = reservar_estoque(
        contexto=contexto,
        repositorio=repo,
        pedido_id=pedido.id,
        pedido_version=pedido.versao,
        snapshot_ficha=snapshot,
        idempotency_key="reserva:f8e",
    )
    _persistir_resultado_estoque(session, reserva)


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("F8-E nao pode executar com FM_AI_TEST_MODE=1")
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        _garantir_loja_legacy(session)
        _garantir_identidades(session)
        pedido = _garantir_pedido(session)
        _garantir_setor(session)
        _garantir_reserva_estoque(session, pedido)
    print("F8-E commercial seed ready; producao KDS ainda nao criada")


if __name__ == "__main__":
    main()
