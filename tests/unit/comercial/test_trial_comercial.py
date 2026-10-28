from datetime import datetime, timedelta, timezone

import pytest

from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida
from core.comercial.trial import (
    EstadoTrial,
    TRIAL_DURATION_DAYS,
    calcular_fim_trial,
    validar_transicao_trial,
)


def test_trial_policy_is_exactly_30_days_in_utc() -> None:
    started = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    assert calcular_fim_trial(
        started_at=started,
        duration_days=TRIAL_DURATION_DAYS,
    ) == started + timedelta(days=30)


def test_trial_rejects_naive_clock() -> None:
    with pytest.raises(DadoComercialInvalido, match="datetime_sem_timezone"):
        calcular_fim_trial(
            started_at=datetime(2026, 9, 22, 12, 0),
            duration_days=30,
        )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (EstadoTrial.EXPIRED, EstadoTrial.ACTIVE),
        (EstadoTrial.REVOKED, EstadoTrial.ACTIVE),
        (EstadoTrial.CONVERTED, EstadoTrial.ACTIVE),
    ],
)
def test_terminal_trial_states_cannot_reactivate(
    current: EstadoTrial,
    target: EstadoTrial,
) -> None:
    with pytest.raises(TransicaoComercialInvalida, match="trial_transicao_invalida"):
        validar_transicao_trial(current, target)
