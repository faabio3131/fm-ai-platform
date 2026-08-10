from datetime import UTC, datetime, timedelta
from decimal import Decimal

from core.kds import ProducaoItem, SetorProducao, calcular_sla


AGORA = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def test_retirada_congela_relogio_do_sla():
    criado = AGORA - timedelta(seconds=300)
    retirado = criado + timedelta(seconds=90)
    setor = SetorProducao(
        "setor-1",
        "tenant-1",
        "unidade-1",
        "quente",
        "Quente",
        1,
        120,
        True,
        criado,
        criado,
    )
    item = ProducaoItem(
        "prod-1",
        "tenant-1",
        "unidade-1",
        "pedido-1",
        "item-1",
        "setor-1",
        "retirada",
        0,
        Decimal("1.0000"),
        1,
        7,
        criado,
        retirado,
        retirada_em=retirado,
    )

    indicador = calcular_sla(item, setor, AGORA)
    assert indicador.decorrido_segundos == 90
    assert indicador.restante_segundos == 30
