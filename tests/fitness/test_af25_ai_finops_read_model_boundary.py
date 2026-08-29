from __future__ import annotations

from pathlib import Path


def test_af25_read_model_nao_varre_usage_bruto() -> None:
    source = Path("infra/ai_finops_read_model.py").read_text(encoding="utf-8")

    assert "AIUsageEventORM" not in source
    assert "fm_ai_usage_events_v1" not in source
    assert "AIFinOpsDailyORM" in source
    assert "tenant_id == tenant" in source
    assert "unidade_id == unidade" in source


def test_af25_dashboard_e_read_only_sobre_read_model() -> None:
    source = Path("infra/streamlit_app/ai_finops.py").read_text(encoding="utf-8")
    app_source = Path("app.py").read_text(encoding="utf-8")

    assert "AIUsageEventORM" not in source
    assert "fm_ai_usage_events_v1" not in source
    assert "AIFinOpsProjector" not in source
    assert ".project_batch(" not in source
    assert "read_model.listar(" in source
    assert "economia monetária não é calculada" in source.casefold()
    assert "render_ai_finops_dashboard" in app_source
    assert "AIFinOpsSQLAlchemyReadModel" in app_source
