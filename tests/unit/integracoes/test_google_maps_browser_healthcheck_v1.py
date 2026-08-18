from datetime import datetime, timezone

from infra.integracoes.google_maps_browser_healthcheck import _evidencia_browser
from scripts.wire_google_maps_browser_healthcheck_v1 import aplicar


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


def test_evidencia_browser_maps_vincula_prova_servidor_sem_expor_segredo() -> None:
    agora = datetime(2026, 8, 18, 18, 0, tzinfo=timezone.utc)
    evidencia = _evidencia_browser(
        contexto=_Contexto(),  # type: ignore[arg-type]
        configuracao_id="mapas--google_maps",
        evidencia_servidor="healthcheck://google-maps-server/20260818T174540Z/abc123",
        agora=agora,
    )
    assert evidencia.startswith("healthcheck://google-maps-full/20260818T180000Z/")
    assert "server" not in evidencia
    assert "api" not in evidencia.casefold()


def test_patch_ui_adiciona_teste_browser_real_sem_auto_homologar_e_e_idempotente() -> None:
    origem = '''import streamlit as st\n\nfrom infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n\n        if spec.provedor == "gemini" and existing is not None:\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "streamlit.components.v1 as components" in primeira
    assert "preparar_healthcheck_browser_google_maps" in primeira
    assert "Testar Google Maps real (navegador)" in primeira
    assert "components.html(preparacao.html" in primeira
    assert "registrar_homologacao" not in primeira
