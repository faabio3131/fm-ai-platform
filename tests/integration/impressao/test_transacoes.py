from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from application.impressao_transacoes import AplicacaoImpressaoV1
from core.impressao import (
    DestinoImpressao,
    ImpressoraFake,
    RepositorioSpoolSQLAlchemy,
    ServicoSpoolImpressao,
    StatusImpressao,
)
from core.kds.modelos import ProducaoItem, SetorProducao
from core.seguranca import ContextoExecucao, Papel, Permissao
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from migrations.runner import run_migrations

AGORA = datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-f9b",
        unidade_id="unidade-f9b",
        usuario_id="cozinha-f9b",
        papeis=frozenset({Papel.COZINHA}),
        permissoes=frozenset(
            {Permissao.PRODUCAO_VISUALIZAR, Permissao.IMPRESSAO_REIMPRIMIR}
        ),
        correlation_id="corr-f9b",
        solicitado_em=AGORA,
        origem="teste_f9b",
        unidades_permitidas=frozenset({"unidade-f9b"}),
    )


def _destino() -> DestinoImpressao:
    return DestinoImpressao(
        tenant_id="tenant-f9b",
        unidade_id="unidade-f9b",
        setor_id="setor-f9b",
        impressora_id="printer-f9b",
        max_tentativas=2,
    )


def _setor() -> SetorProducao:
    return SetorProducao(
        setor_id="setor-f9b",
        tenant_id="tenant-f9b",
        unidade_id="unidade-f9b",
        codigo="CHAPA",
        nome="Chapa",
        ordem=1,
        sla_segundos=900,
        ativo=True,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )


def _producao() -> ProducaoItem:
    return ProducaoItem(
        producao_id="producao-f9b",
        tenant_id="tenant-f9b",
        unidade_id="unidade-f9b",
        pedido_id="pedido-f9b",
        pedido_item_id="item-f9b",
        setor_id="setor-f9b",
        status="aguardando",
        prioridade=0,
        quantidade=Decimal("1"),
        tentativa=1,
        versao=1,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )


def _preparar():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    destino = _destino()
    with factory() as session:
        spool = RepositorioSpoolSQLAlchemy(session)
        service = ServicoSpoolImpressao(
            repositorio=spool,
            impressora=ImpressoraFake(),
            auditoria=RepositorioAuditoriaSQLAlchemy(session),
            destinos=(destino,),
        )
        created = service.enfileirar_item_kds(
            contexto=_contexto(),
            producao=_producao(),
            setor=_setor(),
            idempotency_key="kds-f9b-seed",
            descricao_item="Burger F9-B",
            timestamp=AGORA,
        )
        assert created.job is not None
        session.commit()
        job_id = created.job.job_id
    return factory, destino, job_id


def test_application_processa_e_commita_spool() -> None:
    factory, destino, job_id = _preparar()
    printer = ImpressoraFake()
    app = AplicacaoImpressaoV1(
        factory,
        impressora=printer,
        destinos=(destino,),
        agora=lambda: AGORA,
    )

    result = app.processar(contexto=_contexto(), job_id=job_id)

    assert result.impresso
    assert len(printer.impressoes) == 1
    with factory() as session:
        persisted = RepositorioSpoolSQLAlchemy(session).buscar(
            "tenant-f9b", "unidade-f9b", job_id
        )
        assert persisted is not None
        assert persisted.status is StatusImpressao.IMPRESSO
        assert persisted.tentativa == 1


def test_application_reimpressao_commita_job_e_auditoria_na_mesma_uow() -> None:
    factory, destino, job_id = _preparar()
    app = AplicacaoImpressaoV1(
        factory,
        impressora=ImpressoraFake(),
        destinos=(destino,),
        agora=lambda: AGORA,
    )

    reprint = app.reimprimir(
        contexto=_contexto(),
        job_id=job_id,
        motivo="ticket ilegivel f9b",
        idempotency_key="reprint-f9b",
    )

    with factory() as session:
        persisted = RepositorioSpoolSQLAlchemy(session).buscar(
            "tenant-f9b", "unidade-f9b", reprint.job_id
        )
        audits = RepositorioAuditoriaSQLAlchemy(session).listar(
            tenant_id="tenant-f9b", unidade_id="unidade-f9b"
        )

    assert persisted is not None
    assert persisted.reimpressao_de == job_id
    assert any(event.acao == "impressao.reimprimir" for event in audits)
