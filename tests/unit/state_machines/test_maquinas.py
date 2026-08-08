from datetime import UTC, datetime

import pytest

from core.dominio.enums import CanalAtendimento, MomentoPagamento, OrigemPedido
from core.estados import (
    MAQUINAS,
    ComandoTransicao,
    ErroTransicao,
    PoliticaCozinha,
    RegistroIdempotenciaEmMemoria,
    SnapshotEstado,
    pode_enviar_para_cozinha,
    transicionar,
)
from core.seguranca import ContextoExecucao, Papel, Permissao


AGORA = datetime(2026, 8, 8, tzinfo=UTC)


def contexto(
    *,
    tenant="tenant-1",
    unidade="unidade-1",
    papeis=frozenset({Papel.ADMINISTRADOR}),
    permissoes=frozenset(Permissao),
):
    return ContextoExecucao(
        tenant,
        unidade,
        "ator-1",
        papeis,
        permissoes,
        "corr-1",
        AGORA,
        "teste",
        causation_id="cause-1",
        unidades_permitidas=frozenset({unidade}),
    )


def decisao(ctx=None):
    ctx = ctx or contexto()
    politica = PoliticaCozinha(
        policy_id="cozinha-default",
        version=1,
        canal=CanalAtendimento.PRESENCIAL,
        origem=OrigemPedido.BALCAO,
        momento_pagamento=MomentoPagamento.ANTECIPADO,
    )
    return pode_enviar_para_cozinha(
        politica=politica,
        contexto=ctx,
        pagamento_confirmado=True,
        estoque_disponivel=True,
    )


def comando(destino, versao=1, *, ctx=None, chave=None, motivo=None):
    return ComandoTransicao(
        destino,
        versao,
        chave or f"key-{destino}",
        AGORA,
        ctx or contexto(),
        {
            "itens_validos": True,
            "precos_calculados": True,
            "dados_confirmados": True,
            "itens_roteados": True,
            "producao_iniciada": True,
            "itens_resolvidos": True,
            "saldo_resolvido_ou_posterior": True,
            "pedidos_resolvidos": True,
        },
        motivo or ("cancelamento autorizado" if destino == "cancelado" else None),
        decisao(ctx),
    )


TRANSICOES = [
    (tipo, origem, destino)
    for tipo, maquina in MAQUINAS.items()
    for origem, destinos in maquina.transicoes.items()
    for destino in destinos
]


@pytest.mark.parametrize(("tipo", "origem", "destino"), TRANSICOES)
def test_todas_as_transicoes_normativas(tipo, origem, destino):
    atual = SnapshotEstado(tipo, "id-1", "tenant-1", "unidade-1", origem, 1)
    resultado = transicionar(atual, comando(destino))
    assert resultado.snapshot.estado == destino
    assert resultado.snapshot.version == 2
    assert resultado.snapshot.tenant_id == atual.tenant_id
    assert resultado.snapshot.unidade_id == atual.unidade_id
    assert resultado.evento.correlation_id == "corr-1"


@pytest.mark.parametrize("tipo", MAQUINAS)
def test_transicao_nao_listada_e_proibida(tipo):
    maquina = MAQUINAS[tipo]
    origem = next(iter(maquina.transicoes))
    atual = SnapshotEstado(tipo, "id", "tenant-1", "unidade-1", origem, 1)
    with pytest.raises(ErroTransicao, match="Transição recusada") as erro:
        transicionar(atual, comando("estado_inventado"))
    assert erro.value.codigo == f"transicao_{tipo}_invalida"


@pytest.mark.parametrize(
    ("tipo", "terminal"),
    [
        (tipo, terminal)
        for tipo, maquina in MAQUINAS.items()
        for terminal in maquina.terminais
    ],
)
def test_terminal_nunca_reabre(tipo, terminal):
    with pytest.raises(ErroTransicao) as erro:
        transicionar(
            SnapshotEstado(tipo, "id", "tenant-1", "unidade-1", terminal, 1),
            comando("qualquer"),
        )
    assert erro.value.codigo == "estado_terminal"


def test_idempotencia_retorna_resultado_sem_segundo_evento_e_detecta_conflito():
    registro = RegistroIdempotenciaEmMemoria()
    atual = SnapshotEstado("pedido", "p-1", "tenant-1", "unidade-1", "rascunho", 1)
    primeiro = transicionar(
        atual, comando("aguardando_confirmacao", chave="same"), registro=registro
    )
    repetido = transicionar(
        atual, comando("aguardando_confirmacao", chave="same"), registro=registro
    )
    assert repetido.idempotente and repetido.evento.event_id == primeiro.evento.event_id
    with pytest.raises(ErroTransicao) as erro:
        transicionar(atual, comando("cancelado", chave="same"), registro=registro)
    assert erro.value.codigo == "conflito_idempotencia"


def test_optimistic_locking_cross_tenant_e_rbac_deny_by_default():
    atual = SnapshotEstado("pedido", "p", "tenant-1", "unidade-1", "rascunho", 2)
    with pytest.raises(ErroTransicao) as concorrente:
        transicionar(atual, comando("aguardando_confirmacao", 1))
    assert concorrente.value.codigo == "pedido_concorrente"
    with pytest.raises(ErroTransicao) as escopo:
        transicionar(
            SnapshotEstado("pedido", "p", "tenant-2", "unidade-1", "rascunho", 1),
            comando("aguardando_confirmacao"),
        )
    assert escopo.value.codigo == "recurso_indisponivel"
    sem_permissao = contexto(permissoes=frozenset())
    with pytest.raises(ErroTransicao) as negado:
        transicionar(
            SnapshotEstado("pedido", "p", "tenant-1", "unidade-1", "rascunho", 1),
            comando("aguardando_confirmacao", ctx=sem_permissao),
        )
    assert negado.value.codigo == "permissao_insuficiente"


def test_gerente_ia_nao_confirma_acao_critica():
    ia = contexto(
        papeis=frozenset({Papel.GERENTE_IA}),
        permissoes=frozenset({Permissao.PEDIDO_ALTERAR}),
    )
    with pytest.raises(ErroTransicao) as erro:
        transicionar(
            SnapshotEstado("pedido", "p", "tenant-1", "unidade-1", "rascunho", 1),
            comando("aguardando_confirmacao", ctx=ia),
        )
    assert erro.value.codigo == "confirmacao_exigida"


def test_pedido_exige_decisao_de_cozinha_e_nao_pagamento_pago():
    atual = SnapshotEstado("pedido", "p", "tenant-1", "unidade-1", "confirmado", 1)
    cmd = comando("enviado_producao")
    object.__setattr__(cmd, "decisao_cozinha", None)
    with pytest.raises(ErroTransicao) as erro:
        transicionar(atual, cmd)
    assert erro.value.codigo == "cozinha_nao_autorizada"


def test_evento_e_auditoria_sao_completos_e_metadata_sanitizada():
    atual = SnapshotEstado("pedido", "p", "tenant-1", "unidade-1", "rascunho", 1)
    cmd = comando("aguardando_confirmacao")
    object.__setattr__(cmd, "metadata", {"token": "segredo", "seguro": "ok"})
    resultado = transicionar(atual, cmd)
    assert resultado.evento.event_type == "pedido.aguardando_confirmacao"
    assert dict(resultado.evento.payload) == {"seguro": "ok"}
    assert resultado.auditoria.antes_resumido == (("estado", "rascunho"),)
    assert resultado.auditoria.depois_resumido == (
        ("estado", "aguardando_confirmacao"),
    )


def test_pagamento_producao_e_entrega_nao_alteram_outras_maquinas():
    pagamento = transicionar(
        SnapshotEstado("pagamento", "x", "tenant-1", "unidade-1", "pendente", 1),
        comando("pago"),
    )
    producao = transicionar(
        SnapshotEstado("producao", "x", "tenant-1", "unidade-1", "em_preparo", 1),
        comando("pronta"),
    )
    entrega = transicionar(
        SnapshotEstado("entrega", "x", "tenant-1", "unidade-1", "em_rota", 1),
        comando("entregue"),
    )
    assert {
        pagamento.snapshot.aggregate_type,
        producao.snapshot.aggregate_type,
        entrega.snapshot.aggregate_type,
    } == {"pagamento", "producao", "entrega"}
