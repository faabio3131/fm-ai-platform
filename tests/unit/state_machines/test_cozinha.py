from datetime import UTC, datetime

import pytest

from core.dominio.enums import (
    CanalAtendimento,
    CodigoDecisaoCozinha,
    MomentoPagamento,
    OrigemPedido,
    RiscoPedido,
)
from core.estados import PoliticaCozinha, pode_enviar_para_cozinha
from core.seguranca import ContextoExecucao, Papel, Permissao


def ctx(*, gerente=False, ia=False):
    papeis = frozenset(
        {Papel.GERENTE if gerente else Papel.GERENTE_IA if ia else Papel.CAIXA}
    )
    permissoes = (
        frozenset({Permissao.PEDIDO_LIBERAR_COZINHA}) if gerente or ia else frozenset()
    )
    return ContextoExecucao(
        "t",
        "u",
        "ator",
        papeis,
        permissoes,
        "corr",
        datetime(2026, 8, 8, tzinfo=UTC),
        "teste",
        unidades_permitidas=frozenset({"u"}),
    )


@pytest.mark.parametrize(
    ("canal", "origem", "momento", "confirmado", "posterior", "esperado"),
    [
        (
            CanalAtendimento.PRESENCIAL,
            OrigemPedido.BALCAO,
            MomentoPagamento.ANTECIPADO,
            True,
            False,
            True,
        ),
        (
            CanalAtendimento.PRESENCIAL,
            OrigemPedido.BALCAO,
            MomentoPagamento.ANTECIPADO,
            False,
            False,
            False,
        ),
        (
            CanalAtendimento.PRESENCIAL,
            OrigemPedido.BALCAO,
            MomentoPagamento.NA_RETIRADA,
            False,
            True,
            True,
        ),
        (
            CanalAtendimento.QR_MESA,
            OrigemPedido.MESA,
            MomentoPagamento.NO_FECHAMENTO,
            False,
            True,
            True,
        ),
        (
            CanalAtendimento.DELIVERY_PROPRIO,
            OrigemPedido.DELIVERY_PROPRIO,
            MomentoPagamento.ANTECIPADO,
            True,
            False,
            True,
        ),
        (
            CanalAtendimento.DELIVERY_PROPRIO,
            OrigemPedido.DELIVERY_PROPRIO,
            MomentoPagamento.NA_ENTREGA,
            False,
            True,
            True,
        ),
        (
            CanalAtendimento.MARKETPLACE,
            OrigemPedido.MARKETPLACE,
            MomentoPagamento.ANTECIPADO,
            True,
            False,
            True,
        ),
        (
            CanalAtendimento.MARKETPLACE,
            OrigemPedido.MARKETPLACE,
            MomentoPagamento.POSTERIOR_AUTORIZADO,
            False,
            True,
            True,
        ),
        (
            CanalAtendimento.TELEFONE,
            OrigemPedido.WHATSAPP,
            MomentoPagamento.NA_ENTREGA,
            False,
            True,
            True,
        ),
    ],
)
def test_matriz_de_canais(canal, origem, momento, confirmado, posterior, esperado):
    politica = PoliticaCozinha(
        policy_id="matriz-v1",
        version=1,
        canal=canal,
        origem=origem,
        momento_pagamento=momento,
        permite_pagamento_posterior=posterior,
        requer_pagamento_confirmado=not posterior,
    )
    assert (
        pode_enviar_para_cozinha(
            politica=politica,
            contexto=ctx(),
            pagamento_confirmado=confirmado,
            estoque_disponivel=True,
        ).permitido
        is esperado
    )


def test_risco_estoque_e_overrides():
    base = dict(
        policy_id="p",
        version=2,
        canal=CanalAtendimento.PRESENCIAL,
        origem=OrigemPedido.BALCAO,
        momento_pagamento=MomentoPagamento.ANTECIPADO,
    )
    risco = pode_enviar_para_cozinha(
        politica=PoliticaCozinha(**base, risco=RiscoPedido.ALTO),
        contexto=ctx(),
        pagamento_confirmado=True,
        estoque_disponivel=True,
    )
    assert (
        not risco.permitido
        and risco.codigo_decisao == CodigoDecisaoCozinha.BLOQUEADO_RISCO_ALTO
    )
    estoque = pode_enviar_para_cozinha(
        politica=PoliticaCozinha(**base),
        contexto=ctx(),
        pagamento_confirmado=True,
        estoque_disponivel=False,
    )
    assert (
        not estoque.permitido
        and estoque.codigo_decisao == CodigoDecisaoCozinha.BLOQUEADO_ESTOQUE
    )
    politica_override = PoliticaCozinha(
        **base, risco=RiscoPedido.ALTO, override_permitido=True
    )
    assert not pode_enviar_para_cozinha(
        politica=politica_override,
        contexto=ctx(),
        pagamento_confirmado=True,
        estoque_disponivel=True,
        solicitar_override=True,
    ).permitido
    autorizado = pode_enviar_para_cozinha(
        politica=politica_override,
        contexto=ctx(gerente=True),
        pagamento_confirmado=False,
        estoque_disponivel=False,
        solicitar_override=True,
    )
    assert autorizado.permitido and autorizado.metadados["override"] is True
    assert not pode_enviar_para_cozinha(
        politica=politica_override,
        contexto=ctx(ia=True),
        pagamento_confirmado=True,
        estoque_disponivel=True,
        solicitar_override=True,
    ).permitido
