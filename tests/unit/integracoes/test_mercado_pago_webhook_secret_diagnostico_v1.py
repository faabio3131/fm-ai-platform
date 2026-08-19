from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from infra.seguranca.modelos_orm import CredencialReferenciaORM
from scripts.mercado_pago_webhook_secret_diagnostico import comparar


def _row() -> CredencialReferenciaORM:
    return CredencialReferenciaORM(
        tenant_id="tenant-local",
        unidade_id="unidade-local",
        provedor="mercado_pago",
        finalidade="webhook_secret",
        referencia="vault://opaque",
        versao=7,
        ativa=True,
        rotacionada_por="admin",
        correlation_id="corr-1",
        criada_em=datetime(2026, 8, 19, 23, 0, tzinfo=timezone.utc),
    )


def test_diagnostico_nao_expoe_segredo_e_detecta_correspondencia() -> None:
    segredo = "segredo-super-seguro-123"
    resultado = comparar(row=_row(), segredo_cofre=segredo, segredo_painel=segredo)
    payload = resultado.as_dict()

    assert payload["corresponde"] is True
    assert payload["versao"] == 7
    assert payload["finalidade"] == "webhook_secret"
    assert segredo not in str(payload)
    assert len(payload["fingerprint_cofre"]) == 12
    assert payload["fingerprint_cofre"] == payload["fingerprint_painel"]


def test_diagnostico_detecta_secret_diferente() -> None:
    resultado = comparar(
        row=_row(),
        segredo_cofre="secret-cofre",
        segredo_painel="secret-painel",
    )

    assert resultado.corresponde is False
    assert resultado.fingerprint_cofre != resultado.fingerprint_painel


def test_main_carrega_dotenv_antes_do_runtime_settings() -> None:
    source = Path("scripts/mercado_pago_webhook_secret_diagnostico.py").read_text(
        encoding="utf-8"
    )
    assert "from dotenv import load_dotenv" in source
    main_source = source.split("def main() -> None:", 1)[1]
    assert main_source.index("load_dotenv()") < main_source.index(
        "settings = load_runtime_settings()"
    )
