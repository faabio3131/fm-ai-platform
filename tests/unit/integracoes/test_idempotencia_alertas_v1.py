from datetime import date

from infra.integracoes.idempotencia_alertas import (
    chave_idempotencia_alerta_estoque,
)


def _alerta(*, insumo: str, previsao: str, mensagem: str):
    return {
        "insumo": insumo,
        "previsao_esgotamento": previsao,
        "mensagem_alerta": mensagem,
    }


def test_mesma_ocorrencia_reutiliza_mesma_chave() -> None:
    alerta = _alerta(
        insumo="Queijo",
        previsao="Hoje às 20h",
        mensagem="Estoque crítico",
    )
    data_ref = date(2026, 8, 18)

    primeira = chave_idempotencia_alerta_estoque(
        contato_id=10,
        alerta=alerta,
        data_referencia=data_ref,
    )
    segunda = chave_idempotencia_alerta_estoque(
        contato_id=10,
        alerta=dict(alerta),
        data_referencia=data_ref,
    )

    assert primeira == segunda


def test_alertas_distintos_do_mesmo_contato_no_mesmo_dia_nao_colidem() -> None:
    data_ref = date(2026, 8, 18)
    queijo = chave_idempotencia_alerta_estoque(
        contato_id=10,
        alerta=_alerta(
            insumo="Queijo",
            previsao="Hoje às 20h",
            mensagem="Estoque crítico",
        ),
        data_referencia=data_ref,
    )
    bacon = chave_idempotencia_alerta_estoque(
        contato_id=10,
        alerta=_alerta(
            insumo="Bacon",
            previsao="Hoje às 21h",
            mensagem="Estoque crítico",
        ),
        data_referencia=data_ref,
    )

    assert queijo != bacon


def test_destinatarios_distintos_nao_compartilham_chave() -> None:
    alerta = _alerta(
        insumo="Tomate",
        previsao="Amanhã",
        mensagem="Reposição recomendada",
    )
    data_ref = date(2026, 8, 18)

    chave_a = chave_idempotencia_alerta_estoque(
        contato_id=10,
        alerta=alerta,
        data_referencia=data_ref,
    )
    chave_b = chave_idempotencia_alerta_estoque(
        contato_id=11,
        alerta=alerta,
        data_referencia=data_ref,
    )

    assert chave_a != chave_b
