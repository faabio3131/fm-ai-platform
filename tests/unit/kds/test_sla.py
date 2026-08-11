from datetime import UTC, datetime, timedelta
from decimal import Decimal

from core.kds import EstadoSLA, ProducaoItem, SetorProducao, calcular_sla

AGORA = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def setor(sla=100):
    return SetorProducao(
        "setor-1",
        "tenant-1",
        "unidade-1",
        "quente",
        "Cozinha quente",
        1,
        sla,
        True,
        AGORA - timedelta(minutes=10),
        AGORA - timedelta(minutes=10),
    )


def item(*, criado_ha=50, status="em_preparo", pausa_ha=None, pausa_acumulada=0):
    return ProducaoItem(
        "prod-1",
        "tenant-1",
        "unidade-1",
        "pedido-1",
        "item-1",
        "setor-1",
        status,
        0,
        Decimal("1.0000"),
        1,
        1,
        AGORA - timedelta(seconds=criado_ha),
        AGORA - timedelta(seconds=criado_ha),
        pausa_iniciada_em=(
            AGORA - timedelta(seconds=pausa_ha) if pausa_ha is not None else None
        ),
        pausa_acumulada_segundos=pausa_acumulada,
    )


def test_sla_dentro_atencao_e_estourado():
    assert calcular_sla(item(criado_ha=50), setor(), AGORA).estado == EstadoSLA.DENTRO
    assert calcular_sla(item(criado_ha=80), setor(), AGORA).estado == EstadoSLA.ATENCAO
    assert calcular_sla(item(criado_ha=101), setor(), AGORA).estado == EstadoSLA.ESTOURADO


def test_pausa_suspende_sla_sem_apagar_tempo_anterior():
    indicador = calcular_sla(
        item(criado_ha=120, status="pausada", pausa_ha=40, pausa_acumulada=20),
        setor(),
        AGORA,
    )
    assert indicador.decorrido_segundos == 60
    assert indicador.restante_segundos == 40
    assert indicador.estado == EstadoSLA.DENTRO


def test_setor_sem_sla_retorna_estado_sem_sla():
    indicador = calcular_sla(item(), setor(None), AGORA)
    assert indicador.estado == EstadoSLA.SEM_SLA
    assert indicador.restante_segundos is None
