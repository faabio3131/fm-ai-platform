from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from core.delivery.erros import ErroDelivery
from core.delivery.runtime_teste import RuntimeDeliveryTeste
from core.hardening import ModoDegradacao, ResultadoCaos, ServicoHardeningGateE

TENANT = "tenant-demo"
UNIDADE = "unidade-demo"
CLIENTE = "cliente-demo"


def test_pico_concorrente_nao_duplica_mutacao_do_mesmo_carrinho() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = runtime.servico.abrir_carrinho(
        carrinho_id="hardening-load-cart",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
    )

    def adicionar(_: int) -> str:
        try:
            runtime.servico.adicionar_item(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                carrinho_id=carrinho.carrinho_id,
                produto_id="burger-teste",
                quantidade=1,
                expected_version=carrinho.versao,
                catalogo=runtime.catalogo,
            )
            return "ok"
        except ErroDelivery as exc:
            return exc.codigo

    with ThreadPoolExecutor(max_workers=32) as pool:
        resultados = list(pool.map(adicionar, range(128)))

    assert resultados.count("ok") == 1
    assert resultados.count("conflito_concorrencia") == 127
    atual = runtime.carrinhos.obter(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
    )
    assert atual is not None
    assert len(atual.itens) == 1
    assert atual.itens[0].quantidade == 1
    assert atual.itens[0].subtotal == Decimal("32.00")


def test_caos_fail_closed_reprova_perda_duplicidade_e_recuperacao_lenta() -> None:
    servico = ServicoHardeningGateE()
    saudavel = ResultadoCaos(
        cenario="marketplace_timeout",
        modo_esperado=ModoDegradacao.FAIL_CLOSED,
        falha_injetada=True,
        recuperou=True,
        recuperacao_segundos=25,
        limite_recuperacao_segundos=60,
    )
    assert saudavel.aprovado is True

    perda = ResultadoCaos(
        cenario="kds_offline",
        modo_esperado=ModoDegradacao.DEGRADADO_SEGURO,
        falha_injetada=True,
        recuperou=True,
        recuperacao_segundos=15,
        limite_recuperacao_segundos=60,
        perda_dados=True,
    )
    duplicidade = ResultadoCaos(
        cenario="impressora_reconecta",
        modo_esperado=ModoDegradacao.DEGRADADO_SEGURO,
        falha_injetada=True,
        recuperou=True,
        recuperacao_segundos=20,
        limite_recuperacao_segundos=60,
        efeitos_duplicados=True,
    )
    lenta = ResultadoCaos(
        cenario="fila_eventos_retorna",
        modo_esperado=ModoDegradacao.DEGRADADO_SEGURO,
        falha_injetada=True,
        recuperou=True,
        recuperacao_segundos=121,
        limite_recuperacao_segundos=120,
    )
    assert perda.aprovado is False
    assert duplicidade.aprovado is False
    assert lenta.aprovado is False
