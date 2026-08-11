from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.entrega import (
    ChecklistExpedicao,
    DeliveryBase,
    Entrega,
    ErroEntrega,
    ModalidadeEntrega,
    ProvaEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    StatusEntrega,
)
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

BASE = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _contexto(papel: Papel, usuario: str, *, unidade: str = "unidade-1") -> ContextoExecucao:
    return ContextoExecucao(
        "tenant-1",
        unidade,
        usuario,
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{usuario}",
        BASE,
        "pytest-entrega",
        unidades_permitidas=frozenset({unidade}),
    )


def _sistema() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="worker-pedido",
        motivo="pedido pronto para expedicao",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        correlation_id="corr-sistema",
        solicitado_em=BASE,
    )


def _entrega() -> Entrega:
    return Entrega(
        entrega_id="entrega-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        pedido_id="pedido-1",
        endereco_id="endereco-snapshot-1",
        modalidade=ModalidadeEntrega.PROPRIA,
        status=StatusEntrega.AGUARDANDO_PRODUCAO,
        versao=1,
    )


def test_fluxo_completo_exige_pagamento_separado_e_preserva_eventos():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DeliveryBase.metadata.create_all(engine)
    financeiro = {"resolvido": False}
    relogio = {"agora": BASE}

    def agora() -> datetime:
        relogio["agora"] += timedelta(seconds=1)
        return relogio["agora"]

    with Session(engine) as session:
        repositorio = RepositorioEntregaSQLAlchemy(session)
        servico = ServicoEntrega(
            repositorio,
            financeiro_resolvido=lambda *_: financeiro["resolvido"],
            pedido_cancelado=lambda *_: False,
            agora=agora,
        )
        expedicao = _contexto(Papel.EXPEDICAO, "expedicao-1")
        entregador = _contexto(Papel.ENTREGADOR, "driver-1")

        atual = servico.criar(
            _entrega(), contexto=expedicao, idempotency_key="entrega-criar-1"
        )
        atual = servico.marcar_pedido_pronto(
            atual.entrega_id,
            versao_esperada=atual.versao,
            contexto=_sistema(),
            idempotency_key="entrega-pronta-1",
        )
        assert atual.status is StatusEntrega.AGUARDANDO_EXPEDICAO

        atual = servico.concluir_checklist(
            atual.entrega_id,
            ChecklistExpedicao(True, True, True),
            versao_esperada=atual.versao,
            contexto=expedicao,
            idempotency_key="entrega-checklist-1",
        )
        assert atual.status is StatusEntrega.AGUARDANDO_ENTREGADOR

        atual = servico.atribuir(
            atual.entrega_id,
            "driver-1",
            versao_esperada=atual.versao,
            contexto=expedicao,
            idempotency_key="entrega-atribuir-1",
        )
        atual = servico.coletar(
            atual.entrega_id,
            versao_esperada=atual.versao,
            contexto=entregador,
            idempotency_key="entrega-coletar-1",
        )
        atual = servico.sair_em_rota(
            atual.entrega_id,
            versao_esperada=atual.versao,
            contexto=entregador,
            idempotency_key="entrega-rota-1",
        )

        with pytest.raises(ErroEntrega) as erro:
            servico.confirmar_entrega(
                atual.entrega_id,
                ProvaEntrega("proof://pedido-1", "confirmacao", agora()),
                versao_esperada=atual.versao,
                contexto=entregador,
                idempotency_key="entrega-concluir-1",
            )
        assert erro.value.codigo == "criterio_financeiro_pendente"
        assert repositorio.buscar("tenant-1", "unidade-1", atual.entrega_id).status is StatusEntrega.EM_ROTA

        financeiro["resolvido"] = True
        prova = ProvaEntrega("proof://pedido-1", "confirmacao", agora())
        concluida = servico.confirmar_entrega(
            atual.entrega_id,
            prova,
            versao_esperada=atual.versao,
            contexto=entregador,
            idempotency_key="entrega-concluir-1",
        )
        repetida = servico.confirmar_entrega(
            atual.entrega_id,
            prova,
            versao_esperada=atual.versao,
            contexto=entregador,
            idempotency_key="entrega-concluir-1",
        )

        assert concluida.status is StatusEntrega.ENTREGUE
        assert repetida == concluida
        tipos = [
            evento.tipo
            for evento in repositorio.listar_eventos(
                "tenant-1", "unidade-1", atual.entrega_id
            )
        ]
        assert tipos == [
            "entrega.criada",
            "entrega.aguardando_expedicao",
            "entrega.aguardando_entregador",
            "entrega.atribuida",
            "entrega.coletada",
            "entrega.em_rota",
            "entrega.concluida",
        ]


def test_tentativa_falha_reatribui_incrementando_tentativa():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DeliveryBase.metadata.create_all(engine)

    with Session(engine) as session:
        servico = ServicoEntrega(
            RepositorioEntregaSQLAlchemy(session),
            financeiro_resolvido=lambda *_: True,
            pedido_cancelado=lambda *_: False,
            agora=lambda: BASE,
        )
        expedicao = _contexto(Papel.EXPEDICAO, "expedicao-1")
        driver = _contexto(Papel.ENTREGADOR, "driver-1")
        atual = servico.criar(_entrega(), contexto=expedicao, idempotency_key="c1")
        atual = servico.marcar_pedido_pronto(
            atual.entrega_id,
            versao_esperada=atual.versao,
            contexto=_sistema(),
            idempotency_key="c2",
        )
        atual = servico.concluir_checklist(
            atual.entrega_id,
            ChecklistExpedicao(True, True, True),
            versao_esperada=atual.versao,
            contexto=expedicao,
            idempotency_key="c3",
        )
        atual = servico.atribuir(
            atual.entrega_id,
            "driver-1",
            versao_esperada=atual.versao,
            contexto=expedicao,
            idempotency_key="c4",
        )
        atual = servico.coletar(
            atual.entrega_id,
            versao_esperada=atual.versao,
            contexto=driver,
            idempotency_key="c5",
        )
        atual = servico.sair_em_rota(
            atual.entrega_id,
            versao_esperada=atual.versao,
            contexto=driver,
            idempotency_key="c6",
        )
        atual = servico.registrar_tentativa_falha(
            atual.entrega_id,
            "cliente ausente",
            versao_esperada=atual.versao,
            contexto=driver,
            idempotency_key="c7",
        )
        reatribuida = servico.atribuir(
            atual.entrega_id,
            "driver-2",
            versao_esperada=atual.versao,
            contexto=expedicao,
            idempotency_key="c8",
        )

        assert atual.status is StatusEntrega.TENTATIVA_FALHOU
        assert reatribuida.status is StatusEntrega.ATRIBUIDA
        assert reatribuida.tentativa == 2
        assert reatribuida.entregador_id == "driver-2"


def test_entregador_nao_acessa_entrega_de_outro_e_idor_nao_vaza_escopo():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DeliveryBase.metadata.create_all(engine)

    with Session(engine) as session:
        servico = ServicoEntrega(
            RepositorioEntregaSQLAlchemy(session),
            financeiro_resolvido=lambda *_: True,
            pedido_cancelado=lambda *_: False,
            agora=lambda: BASE,
        )
        expedicao = _contexto(Papel.EXPEDICAO, "expedicao-1")
        atual = servico.criar(_entrega(), contexto=expedicao, idempotency_key="i1")
        atual = servico.atribuir(
            atual.entrega_id,
            "driver-1",
            versao_esperada=atual.versao,
            contexto=expedicao,
            idempotency_key="i2",
        )

        assert servico.listar(_contexto(Papel.ENTREGADOR, "driver-2")) == ()
        with pytest.raises(ErroEntrega) as erro:
            servico.coletar(
                atual.entrega_id,
                versao_esperada=atual.versao,
                contexto=_contexto(Papel.ENTREGADOR, "driver-2"),
                idempotency_key="i3",
            )
        assert erro.value.codigo == "entrega_fora_alcada"

        with pytest.raises(ErroEntrega) as idor:
            servico.coletar(
                atual.entrega_id,
                versao_esperada=atual.versao,
                contexto=_contexto(Papel.ENTREGADOR, "driver-1", unidade="unidade-2"),
                idempotency_key="i4",
            )
        assert idor.value.codigo == "entrega_nao_encontrada"


def test_cancelamento_exige_pedido_cancelado_e_alcada():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DeliveryBase.metadata.create_all(engine)
    cancelado = {"valor": False}

    with Session(engine) as session:
        servico = ServicoEntrega(
            RepositorioEntregaSQLAlchemy(session),
            financeiro_resolvido=lambda *_: True,
            pedido_cancelado=lambda *_: cancelado["valor"],
            agora=lambda: BASE,
        )
        expedicao = _contexto(Papel.EXPEDICAO, "expedicao-1")
        atendimento = _contexto(Papel.ATENDIMENTO, "atendimento-1")
        atual = servico.criar(_entrega(), contexto=expedicao, idempotency_key="x1")

        with pytest.raises(ErroEntrega) as erro:
            servico.cancelar(
                atual.entrega_id,
                "pedido cancelado pelo cliente",
                versao_esperada=atual.versao,
                contexto=atendimento,
                idempotency_key="x2",
            )
        assert erro.value.codigo == "pedido_ainda_ativo"

        cancelado["valor"] = True
        final = servico.cancelar(
            atual.entrega_id,
            "pedido cancelado pelo cliente",
            versao_esperada=atual.versao,
            contexto=atendimento,
            idempotency_key="x2",
        )
        assert final.status is StatusEntrega.CANCELADA
