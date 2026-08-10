from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.central_pedidos import CentralPedidosSQLAlchemy, FiltroCentralPedidos
from core.central_pedidos.servicos import ServicoComandosCentral
from core.estados.maquinas import ErroTransicao
from core.dominio.enums import CanalAtendimento, PedidoStatus
from core.dominio.ids import PedidoId, TenantId, UnidadeId
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    PaymentsBase,
)
from core.pdv.modelos_orm import PDVBase
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.modelos_orm import OrdersBase
from core.seguranca import ContextoExecucao, Papel, Permissao
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from tests.unit.orders.factories import pedido

AGORA = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)


def contexto(tenant="tenant-a", unidade="unidade-a", permissoes=None):
    return ContextoExecucao(
        tenant,
        unidade,
        "operador",
        frozenset({Papel.CAIXA}),
        permissoes
        if permissoes is not None
        else frozenset({Permissao.PEDIDO_VISUALIZAR, Permissao.PEDIDO_ALTERAR}),
        "corr-central",
        AGORA,
        "teste",
        unidades_permitidas=frozenset({unidade}),
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    OrdersBase.metadata.create_all(engine)
    PaymentsBase.metadata.create_all(engine)
    PDVBase.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def salvar(
    session,
    identificador,
    *,
    tenant="tenant-a",
    unidade="unidade-a",
    canal=CanalAtendimento.PRESENCIAL,
    minutos=0,
):
    original = pedido()
    novo = replace(
        original,
        id=PedidoId(identificador),
        tenant_id=TenantId(tenant),
        unidade_id=UnidadeId(unidade),
        canal=canal,
        criado_em=AGORA - timedelta(minutes=minutos),
        atualizado_em=AGORA - timedelta(minutes=minutos),
        correlation_id=type(original.correlation_id)(f"corr-{identificador}"),
        idempotency_key=type(original.idempotency_key)(f"idem-{identificador}"),
        itens=tuple(
            replace(
                i,
                tenant_id=TenantId(tenant),
                unidade_id=UnidadeId(unidade),
                id=type(i.id)(f"item-{identificador}"),
                adicionais=tuple(
                    replace(
                        a,
                        id=f"ad-{identificador}",
                        tenant_id=TenantId(tenant),
                        unidade_id=UnidadeId(unidade),
                    )
                    for a in i.adicionais
                ),
            )
            for i in original.itens
        ),
        observacoes=tuple(
            replace(
                o,
                id=f"obs-{identificador}",
                tenant_id=TenantId(tenant),
                unidade_id=UnidadeId(unidade),
            )
            for o in original.observacoes
        ),
    )
    return RepositorioPedidosSQLAlchemy(session).salvar(novo)


def pagamento(
    session,
    pedido_id,
    *,
    status="pendente",
    pago=Decimal("0.00"),
    previsto=Decimal("24.00"),
    pagamento_id=None,
):
    identificador = pagamento_id or f"pay-{pedido_id}"
    session.add(
        ObrigacaoPagamentoORM(
            id=identificador,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            pedido_id=pedido_id,
            comanda_id=None,
            valor_previsto=previsto,
            moeda="BRL",
            criado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"ob-{identificador}",
            request_hash="hash",
        )
    )
    session.add(
        PagamentoORM(
            id=identificador,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            pedido_id=pedido_id,
            comanda_id=None,
            status=status,
            metodo="dinheiro",
            valor_previsto=previsto,
            valor_pago=pago,
            valor_estornado=Decimal("0.00"),
            saldo=previsto - pago,
            moeda="BRL",
            recebimento_posterior=False,
            provedor=None,
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"pg-{identificador}",
            request_hash="hash",
        )
    )
    session.flush()


def test_lista_paginada_ordenada_filtrada_decimal_e_detalhe_sem_financeiro(session):
    salvar(session, "p-1", minutos=2)
    salvar(session, "p-2", canal=CanalAtendimento.WHATSAPP, minutos=1)
    pagina = CentralPedidosSQLAlchemy(session, agora=lambda: AGORA).listar(
        contexto(),
        FiltroCentralPedidos(
            canal=(CanalAtendimento.WHATSAPP.value,), tamanho_pagina=1
        ),
    )
    assert pagina.total == 1
    assert pagina.itens[0].pedido_id == "p-2"
    assert pagina.itens[0].total == Decimal("24.00")
    assert pagina.itens[0].financeiro.situacao == "ausente"
    detalhe = CentralPedidosSQLAlchemy(session, agora=lambda: AGORA).detalhar(
        contexto(), "p-2"
    )
    assert detalhe and detalhe.itens[0].adicionais and detalhe.observacoes
    assert detalhe.resumo.criado_em.utcoffset() == timedelta(0)


def test_idor_tenant_unidade_e_rbac(session):
    salvar(session, "segredo", tenant="tenant-b", unidade="unidade-b")
    central = CentralPedidosSQLAlchemy(session, agora=lambda: AGORA)
    assert central.detalhar(contexto(), "segredo") is None
    assert central.detalhar(contexto("tenant-b", "outra"), "segredo") is None
    with pytest.raises(PermissionError):
        central.listar(contexto(permissoes=frozenset()), FiltroCentralPedidos())


def test_filtros_derivados_antecedem_paginacao_sem_perda_ou_duplicacao(session):
    # Matches financeiros ficam intercalados alem da primeira pagina bruta.
    for indice in range(8):
        pedido_id = f"p-{indice}"
        salvar(session, pedido_id, minutos=indice)
        if indice % 2 == 1:
            pagamento(session, pedido_id, status="pago", pago=Decimal("24.00"))
    central = CentralPedidosSQLAlchemy(session, agora=lambda: AGORA)
    paginas = [
        central.listar(
            contexto(),
            FiltroCentralPedidos(
                situacao_financeira="confirmado", pagina=pagina, tamanho_pagina=2
            ),
        )
        for pagina in (1, 2)
    ]
    assert [pagina.total for pagina in paginas] == [4, 4]
    ids = [item.pedido_id for pagina in paginas for item in pagina.itens]
    assert ids == ["p-1", "p-3", "p-5", "p-7"]
    assert len(ids) == len(set(ids)) == 4


def test_multiplos_pagamentos_somam_obrigacoes_e_exigem_todos_pagos(session):
    salvar(session, "misto-parcial")
    pagamento(
        session,
        "misto-parcial",
        status="pago",
        pago=Decimal("14.00"),
        previsto=Decimal("14.00"),
        pagamento_id="pay-misto-parcial-a",
    )
    pagamento(
        session,
        "misto-parcial",
        previsto=Decimal("10.00"),
        pagamento_id="pay-misto-parcial-b",
    )

    salvar(session, "misto-confirmado", minutos=1)
    pagamento(
        session,
        "misto-confirmado",
        status="pago",
        pago=Decimal("14.00"),
        previsto=Decimal("14.00"),
        pagamento_id="pay-misto-confirmado-a",
    )
    pagamento(
        session,
        "misto-confirmado",
        status="pago",
        pago=Decimal("10.00"),
        previsto=Decimal("10.00"),
        pagamento_id="pay-misto-confirmado-b",
    )

    central = CentralPedidosSQLAlchemy(session, agora=lambda: AGORA)
    parcial = central.detalhar(contexto(), "misto-parcial")
    assert parcial is not None
    assert parcial.financeiro.valor_previsto == Decimal("24.00")
    assert parcial.financeiro.valor_pago == Decimal("14.00")
    assert parcial.financeiro.situacao == "parcial"

    confirmado = central.detalhar(contexto(), "misto-confirmado")
    assert confirmado is not None
    assert confirmado.financeiro.valor_previsto == Decimal("24.00")
    assert confirmado.financeiro.valor_pago == Decimal("24.00")
    assert confirmado.financeiro.situacao == "confirmado"

    pagina_confirmados = central.listar(
        contexto(), FiltroCentralPedidos(situacao_financeira="confirmado")
    )
    assert [item.pedido_id for item in pagina_confirmados.itens] == [
        "misto-confirmado"
    ]
    pagina_parciais = central.listar(
        contexto(), FiltroCentralPedidos(situacao_financeira="parcial")
    )
    assert [item.pedido_id for item in pagina_parciais.itens] == ["misto-parcial"]


def test_somente_alertas_pagina_o_conjunto_derivado_e_total_correto(session):
    for indice in range(7):
        pedido_id = f"alerta-{indice}"
        salvo = salvar(session, pedido_id, minutos=indice)
        if indice in {1, 3, 5}:
            pagamento(session, pedido_id)
        else:
            # Sem pagamento e recente: não há alerta financeiro inventado.
            assert salvo.status is PedidoStatus.RASCUNHO
    central = CentralPedidosSQLAlchemy(session, agora=lambda: AGORA)
    pagina1 = central.listar(
        contexto(), FiltroCentralPedidos(somente_com_alertas=True, tamanho_pagina=2)
    )
    pagina2 = central.listar(
        contexto(),
        FiltroCentralPedidos(somente_com_alertas=True, pagina=2, tamanho_pagina=2),
    )
    assert pagina1.total == pagina2.total == 3
    assert [x.pedido_id for x in pagina1.itens] == ["alerta-1", "alerta-3"]
    assert [x.pedido_id for x in pagina2.itens] == ["alerta-5"]


def test_comando_usa_maquina_versao_evento_auditoria_e_idempotencia(session):
    salvar(session, "comando")
    auditoria = RepositorioAuditoriaEmMemoria()
    servico = ServicoComandosCentral(session, auditoria)
    precondicoes = {"itens_validos": True, "precos_calculados": True}
    atualizado = servico.transicionar(
        contexto=contexto(),
        pedido_id="comando",
        destino="aguardando_confirmacao",
        versao_esperada=1,
        idempotency_key="central-comando",
        timestamp=AGORA,
        precondicoes=precondicoes,
    )
    assert atualizado.status is PedidoStatus.AGUARDANDO_CONFIRMACAO
    assert atualizado.versao == 2 and len(auditoria.eventos) == 1
    assert (
        servico.transicionar(
            contexto=contexto(),
            pedido_id="comando",
            destino="aguardando_confirmacao",
            versao_esperada=1,
            idempotency_key="central-comando",
            timestamp=AGORA,
            precondicoes=precondicoes,
        ).versao
        == 2
    )
    with pytest.raises(ErroTransicao) as erro:
        servico.transicionar(
            contexto=contexto(),
            pedido_id="comando",
            destino="confirmado",
            versao_esperada=1,
            idempotency_key="central-stale",
            timestamp=AGORA,
        )
    assert erro.value.codigo == "pedido_concorrente"
    assert auditoria.eventos[-1].resultado == "negado"


def test_comando_idempotencia_rejeita_reuso_em_outro_pedido_e_payload_divergente(
    session,
):
    salvar(session, "idem-a")
    salvar(session, "idem-b")
    auditoria = RepositorioAuditoriaEmMemoria()
    servico = ServicoComandosCentral(session, auditoria)
    precondicoes = {"itens_validos": True, "precos_calculados": True}

    servico.transicionar(
        contexto=contexto(),
        pedido_id="idem-a",
        destino="aguardando_confirmacao",
        versao_esperada=1,
        idempotency_key="central-compartilhada",
        timestamp=AGORA,
        precondicoes=precondicoes,
    )

    with pytest.raises(ValueError, match="conflito_idempotencia"):
        servico.transicionar(
            contexto=contexto(),
            pedido_id="idem-b",
            destino="aguardando_confirmacao",
            versao_esperada=1,
            idempotency_key="central-compartilhada",
            timestamp=AGORA,
            precondicoes=precondicoes,
        )
    with pytest.raises(ValueError, match="conflito_idempotencia"):
        servico.transicionar(
            contexto=contexto(),
            pedido_id="idem-a",
            destino="aguardando_confirmacao",
            versao_esperada=1,
            idempotency_key="central-compartilhada",
            timestamp=AGORA,
            precondicoes={"itens_validos": True, "precos_calculados": False},
        )

    pedido_b = RepositorioPedidosSQLAlchemy(session).buscar(
        TenantId("tenant-a"), UnidadeId("unidade-a"), PedidoId("idem-b")
    )
    assert pedido_b is not None
    assert pedido_b.status is PedidoStatus.RASCUNHO
    assert pedido_b.versao == 1


def test_comando_negado_por_rbac_tambem_e_auditado(session):
    salvar(session, "negado")
    auditoria = RepositorioAuditoriaEmMemoria()
    with pytest.raises(ErroTransicao) as erro:
        ServicoComandosCentral(session, auditoria).transicionar(
            contexto=contexto(permissoes=frozenset({Permissao.PEDIDO_VISUALIZAR})),
            pedido_id="negado",
            destino="aguardando_confirmacao",
            versao_esperada=1,
            idempotency_key="central-negado",
            timestamp=AGORA,
            precondicoes={"itens_validos": True, "precos_calculados": True},
        )
    assert erro.value.codigo == "permissao_insuficiente"
    assert len(auditoria.eventos) == 1
    assert auditoria.eventos[0].resultado == "negado"
