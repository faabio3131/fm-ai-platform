from datetime import date, datetime, timezone

import pytest

from infra.legacy_expiration_alert import status_validade_legado


@pytest.mark.parametrize(
    ("validade", "janela", "esperado"),
    [
        (date(2026, 8, 23), 15, "🔴 VENCIDO!"),
        (date(2026, 8, 24), 15, "🔴 VENCIDO!"),
        (date(2026, 8, 27), 3, "🟡 Vence em 3 dias!"),
        (datetime(2026, 8, 31, 12, tzinfo=timezone.utc), 7, "🟡 Vence em 7 dias!"),
        (date(2026, 9, 8), 15, "🟡 Vence em 15 dias!"),
        (date(2026, 9, 9), 15, "🟢 No Prazo"),
        (None, 15, "🟢 No Prazo"),
    ],
)
def test_status_validade_legado(
    validade: date | datetime | None,
    janela: int,
    esperado: str,
) -> None:
    assert status_validade_legado(
        data_validade=validade,
        dias_alerta_vencimento=janela,
        hoje=date(2026, 8, 24),
    ) == esperado
