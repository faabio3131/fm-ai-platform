"""Seed efêmero do gate F7-F no runtime comercial PostgreSQL.

Este script é exclusivo de CI/staging descartável. Ele não habilita FM_AI_TEST_MODE,
não cria pagamento artificial e usa serviços canônicos para Salão/Garçom/KDS.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker

from core.garcom import ServicoGarcom
from core.kds import RepositorioAuditoriaEmMemoria, RepositorioKDSSQLAlchemy, ServicoKDS
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.salao import RepositorioSalaoSQLAlchemy, ServicoSalao
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

TENANT = "tenant-f7f"
UNIDADE = "unidade-f7f"
LOJA_ID = 7001
AGORA = datetime(2026, 9, 2, 15, 45, tzinfo=UTC)

GERENTE_EMAIL = "gerente-f7f@fm.ai"
GERENTE_PASSWORD = "F7F-Gerente-2026!"
GARCOM_EMAIL = "garcom-f7f@fm.ai"
GARCOM_PASSWORD = "F7F-Garcom-2026!"


def _contexto(papel: Papel, usuario_id: str) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=usuario_id,
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-f7f-{usuario_id}",
        solicitado_em=AGORA,
        origem="scripts.seed_f7f_commercial_runtime",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _criar_pedido(
    session: Session,
    *,
    pedido_id: str,
    item_id: str,
    produto_id: str,
    nome: str,
    total: str,
    status: str,
) -> None:
    if session.get(PedidoORM, (pedido_id, TENANT, UNIDADE)) is not None:
        return
    valor = Decimal(total)
    pedido = PedidoORM(
        id=pedido_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="salao",
        canal="mesa",
        status=status,
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
    pedido.itens = [
        ItemPedidoORM(
            id=item_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=pedido_id,
            ordem=1,
            produto_id=produto_id,
            nome_produto=nome,
            quantidade=1,
            preco_unitario=valor,
            subtotal=valor,
            observacao=None,
            ficha_versao="v1",
        )
    ]
    session.add(pedido)
    session.flush()


def _garantir_loja_legacy(session: Session) -> None:
    metadata = MetaData()
    lojas = Table("lojas", metadata, autoload_with=session.connection())
    mapping = Table(
        "fm_unidade_loja_legacy_v1",
        metadata,
        autoload_with=session.connection(),
    )
    if session.execute(select(lojas.c.id).where(lojas.c.id == LOJA_ID)).scalar_one_or_none() is None:
        session.execute(insert(lojas).values(id=LOJA_ID, nome_fantasia="Loja F7-F Staging"))
    if (
        session.execute(
            select(mapping.c.tenant_id)
            .where(mapping.c.tenant_id == TENANT)
            .where(mapping.c.unidade_id == UNIDADE)
        ).scalar_one_or_none()
        is None
    ):
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
    if repo.obter_por_email(GERENTE_EMAIL) is None:
        repo.criar_usuario(
            email=GERENTE_EMAIL,
            password=GERENTE_PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
            usuario_id="gerente-f7f",
        )
    if repo.obter_por_email(GARCOM_EMAIL) is None:
        repo.criar_usuario(
            email=GARCOM_EMAIL,
            password=GARCOM_PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GARCOM,),
            unidades_permitidas=(UNIDADE,),
            usuario_id="garcom-f7f",
        )


def _seed_salao_gerente(session: Session) -> None:
    ctx = _contexto(Papel.GERENTE, "gerente-f7f")
    repo = RepositorioSalaoSQLAlchemy(session)
    servico = ServicoSalao(repo, agora=lambda: AGORA)
    if repo.obter_mesa(TENANT, UNIDADE, "mesa-f7f-gerente") is not None:
        return
    mesa = servico.cadastrar_mesa(
        ctx,
        mesa_id="mesa-f7f-gerente",
        codigo="F71",
        nome="Fechamento F7-F",
        capacidade=4,
        idempotency_key="f7f:gerente:mesa",
    )
    _criar_pedido(
        session,
        pedido_id="pedido-f7f-gerente",
        item_id="item-f7f-gerente",
        produto_id="produto-f7f-gerente",
        nome="Prato Fechamento F7-F",
        total="20.00",
        status="confirmado",
    )
    comanda = servico.abrir_comanda(
        ctx,
        comanda_id="comanda-f7f-gerente",
        numero="GERENTE-F7F",
        mesa_id=mesa.mesa_id,
        expected_mesa_version=mesa.versao,
        idempotency_key="f7f:gerente:abrir",
    )
    comanda = servico.vincular_pedido(
        ctx,
        comanda_id=comanda.comanda_id,
        pedido_id="pedido-f7f-gerente",
        expected_version=comanda.versao,
        idempotency_key="f7f:gerente:vincular",
    )
    servico.solicitar_conta(
        ctx,
        comanda_id=comanda.comanda_id,
        expected_version=comanda.versao,
        idempotency_key="f7f:gerente:conta",
    )


def _seed_garcom_kds(session: Session) -> None:
    ctx_admin = _contexto(Papel.ADMINISTRADOR, "admin-seed-f7f")
    ctx_garcom = _contexto(Papel.GARCOM, "garcom-f7f")
    repo_salao = RepositorioSalaoSQLAlchemy(session)
    repo_kds = RepositorioKDSSQLAlchemy(session)
    garcom = ServicoGarcom(repo_salao, repo_kds, agora=lambda: AGORA)
    kds = ServicoKDS(repo_kds, RepositorioAuditoriaEmMemoria(), agora=lambda: AGORA)
    if repo_salao.obter_mesa(TENANT, UNIDADE, "mesa-f7f-garcom") is not None:
        return
    mesa = garcom.salao.cadastrar_mesa(
        ctx_admin,
        mesa_id="mesa-f7f-garcom",
        codigo="G72",
        nome="Garcom F7-F",
        capacidade=4,
        idempotency_key="f7f:garcom:mesa",
    )
    _criar_pedido(
        session,
        pedido_id="pedido-f7f-garcom",
        item_id="item-f7f-garcom",
        produto_id="produto-f7f-garcom",
        nome="Prato Garcom F7-F",
        total="32.00",
        status="enviado_producao",
    )
    comanda = garcom.abrir_comanda(
        ctx_garcom,
        mesa_id=mesa.mesa_id,
        expected_mesa_version=mesa.versao,
        numero="GARCOM-F7F",
        comanda_id="comanda-f7f-garcom",
        idempotency_key="f7f:garcom:abrir",
    )
    garcom.vincular_pedido(
        ctx_garcom,
        comanda_id=comanda.comanda_id,
        pedido_id="pedido-f7f-garcom",
        expected_version=comanda.versao,
        idempotency_key="f7f:garcom:vincular",
    )
    setor = kds.criar_setor(
        ctx_admin,
        codigo="cozinha-f7f",
        nome="Cozinha F7-F",
        ordem=1,
        sla_segundos=600,
        setor_id="setor-f7f",
    )
    producao = kds.rotear_item(
        ctx_admin,
        pedido_id="pedido-f7f-garcom",
        pedido_item_id="item-f7f-garcom",
        setor_id=setor.setor_id,
        quantidade=Decimal("1.0000"),
        idempotency_key="f7f:kds:route",
        producao_id="producao-f7f",
    )
    aceita = kds.transicionar(
        ctx_admin,
        producao_id=producao.producao_id,
        destino="aceita",
        versao_esperada=1,
        idempotency_key="f7f:kds:aceita",
        precondicoes={"setor_correto": True},
    )
    preparo = kds.transicionar(
        ctx_admin,
        producao_id=producao.producao_id,
        destino="em_preparo",
        versao_esperada=aceita.item.versao,
        idempotency_key="f7f:kds:preparo",
        precondicoes={"estoque_resolvido": True, "estacao_apta": True},
    )
    kds.transicionar(
        ctx_admin,
        producao_id=producao.producao_id,
        destino="pronta",
        versao_esperada=preparo.item.versao,
        idempotency_key="f7f:kds:pronta",
        precondicoes={"quantidade_concluida": True, "checklist_concluido": True},
    )


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("F7-F nao pode executar com FM_AI_TEST_MODE=1")
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    run_migrations(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with SessionLocal.begin() as session:
        _garantir_loja_legacy(session)
        _garantir_identidades(session)
        _seed_salao_gerente(session)
        _seed_garcom_kds(session)
    print("F7-F commercial seed ready")


if __name__ == "__main__":
    main()
