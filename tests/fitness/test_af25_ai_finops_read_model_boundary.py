from __future__ import annotations

from pathlib import Path


def test_af25_read_model_nao_varre_usage_bruto() -> None:
    source = Path("infra/ai_finops_read_model.py").read_text(encoding="utf-8")

    assert "AIUsageEventORM" not in source
    assert "fm_ai_usage_events_v1" not in source
    assert "AIFinOpsDailyORM" in source
    assert "tenant_id == tenant" in source
    assert "unidade_id == unidade" in source
