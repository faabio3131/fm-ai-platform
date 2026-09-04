from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.entrega_composicao import listar_entregadores_elegiveis
from application.entrega_transacoes import AplicacaoEntregaV1
from core.entrega import (
    DeliveryBase,
    Entrega,
    ModalidadeEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    StatusEntrega,
)
from core.entrega.erros import ErroEntrega
from core.entrega.modelos_orm import EntregaORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from infra.seguranca import RepositorioIdentidadesSQLAlchemy, SecurityBase

TENANT = "tenant-f10d"
UNIDADE = "unidade-f10d"
OUTRA_UNIDADE = "unidade-f10d-outra"
AGORA = datetime(2026, 9, 4, 18, 30, tzinfo=UTC)


def _contexto_expedicao() -> ContextoExecucao:
    papel = Papel.EXPEDICAO
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "expedicao-f10d",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        "corr-f10d",
        AGORA,
        "tests.f10d.expedicao",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SecurityBase.metadata.create_all(engine)
    DeliveryBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        identidades = RepositorioIdentidadesSQLAlchemy(session)
        identidades.criar_usuario(
            usuario_id="driver-ok",
            email="driver.ok@f10d.local",
            password="DriverF10d!123",
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis={Papel.ENTREGADOR},
            unidades_permitidas={UNIDADE},
        )
        identidades.criar_usuario(
            usuario_id="driver-inativo",
            email="driver.inativo@f10d.local",
            password="DriverF10d!123",
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis={Papel.ENTREGADOR},
            unidades_permitidas={UNIDADE},
        )
        identidades.definir_ativo(usuario_id="driver-inativo", ativo=False)
        identidades.criar_usuario(
            usuario_id="usuario-sem-papel",
            email="garcom@f10d.local",
            password="DriverF10d!123",
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis={Papel.GARCOM},
            unidades_permitidas={UNIDADE},
        )
        identidades.criar_usuario(
            usuario_id="driver-outra-unidade",
            email="driver.outra.unidade@f10d.local",
            password="DriverF10d!123",
            tenant_id=TENANT,
            unidade_padrao_id=OUTRA_UNIDADE,
            papeis={Papel.ENTREGADOR},
            unidades_permitidas={OUTRA_UNIDADE},
        )
        identidades.criar_usuario(
            usuario_id="driver-outro-tenant",
            email="driver.outro.tenant@f10d.local",
            password="DriverF10d!123",
            tenant_id="tenant-f10d-outro",
            unidade_padrao_id=UNIDADE,
            papeis={Papel.ENTREGADOR},
            unidades_permitidas={UNIDADE},
        )

        contexto_sistema = ContextoExecucao.sistema(
            identidade="seed-f10d",
            motivo="seed entrega governanca entregador",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            correlation_id="corr-seed-f10d",
            solicitado_em=AGORA,
        )
        ServicoEntrega(
            RepositorioEntregaSQLAlchemy(session),
            financeiro_resolvido=lambda *_: True,
            pedido_cancelado=lambda *_: False,
            agora=lambda: AGORA,
        ).criar(
            Entrega(
                entrega_id="entrega-f10d",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-f10d",
                endereco_id="address://f10d",
                modalidade=ModalidadeEntrega.PROPRIA,
                status=StatusEntrega.AGUARDANDO_PRODUCAO,
                versao=1,
            ),
            contexto=contexto_sistema,
            idempotency_key="seed-entrega-f10d",
        )
        session.commit()

    return engine, factory


def test_lista_comercial_expoe_somente_entregador_elegivel() -> None:
    _, factory = _infra()
    with factory() as session:
        resultado = listar_entregadores_elegiveis(
            session,
            contexto=_contexto_expedicao(),
        )

    assert tuple(item.usuario_id for item in resultado) == ("driver-ok",)


def test_atribuicao_governada_persiste_identidade_canonica() -> None:
    engine, factory = _infra()
    resultado = AplicacaoEntregaV1(factory, agora=lambda: AGORA).atribuir_entregador_governado(
        "entrega-f10d",
        "driver-ok",
        versao_esperada=1,
        contexto=_contexto_expedicao(),
        idempotency_key="f10d:atribuir:driver-ok",
    )

    assert resultado.status is StatusEntrega.ATRIBUIDA
    assert resultado.entregador_id == "driver-ok"

    with Session(engine) as session:
        row = session.scalar(select(EntregaORM).where(EntregaORM.id == "entrega-f10d"))
        assert row is not None
        assert row.entregador_id == "driver-ok"
        assert row.status == StatusEntrega.ATRIBUIDA.value


@pytest.mark.parametrize(
    "entregador_id",
    [
        "driver-inativo",
        "usuario-sem-papel",
        "driver-outra-unidade",
        "driver-outro-tenant",
        "usuario-inexistente",
    ],
)
def test_atribuicao_governada_recusa_identidade_nao_elegivel(
    entregador_id: str,
) -> None:
    engine, factory = _infra()

    with pytest.raises(ErroEntrega) as exc_info:
        AplicacaoEntregaV1(factory, agora=lambda: AGORA).atribuir_entregador_governado(
            "entrega-f10d",
            entregador_id,
            versao_esperada=1,
            contexto=_contexto_expedicao(),
            idempotency_key=f"f10d:atribuir:{entregador_id}",
        )
    assert exc_info.value.codigo == "entregador_nao_elegivel"

    with Session(engine) as session:
        row = session.scalar(select(EntregaORM).where(EntregaORM.id == "entrega-f10d"))
        assert row is not None
        assert row.status == StatusEntrega.AGUARDANDO_PRODUCAO.value
        assert row.entregador_id is None
        assert row.versao == 1
