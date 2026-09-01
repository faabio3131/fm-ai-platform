from datetime import datetime, timezone

from infra.integracoes.google_maps_browser_healthcheck import (
    _evidencia_browser,
    _pagina_prova,
)
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


def test_pagina_prova_confirma_tilesloaded_e_exibe_evidencia_com_copia() -> None:
    pagina = _pagina_prova(
        browser_key="AIza-chave-controlada-teste",
        evidencia="healthcheck://google-maps-full/20260818T180000Z/abc123",
        token="token-controlado",
    )
    assert "tilesloaded" in pagina
    assert "/google-maps-proof/token-controlado/success" in pagina
    assert "method: 'POST'" in pagina
    assert "Copiar evidencia" in pagina
    assert "word-break: break-all" in pagina
    assert "about:srcdoc" not in pagina
    assert "Maps JavaScript API validada externamente no navegador" in pagina


def test_patch_ui_adiciona_confirmacao_e_autopreenchimento_e_e_idempotente() -> None:
    origem = '''import streamlit as st\nimport streamlit.components.v1 as components\n\nfrom infra.integracoes.google_maps_browser_healthcheck import preparar_healthcheck_browser_google_maps\nfrom infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n\n        evidence_ref = st.text_input(\n            "Referência da evidência de homologação",\n            value="",\n            max_chars=512,\n            placeholder="Ex.: healthcheck://meta/2026-08-17/resultado-123",\n            key=_key(spec, "homolog_evidence_ref"),\n        )\n\n        if spec.provedor == "google_maps" and existing is not None:\n            evidencia_servidor = st.session_state.get(\n                _key(spec, "last_real_maps_server_healthcheck_evidence")\n            )\n            st.caption("teste")\n            if st.button("Testar Google Maps real (navegador)"):\n                preparacao = preparar_healthcheck_browser_google_maps(\n                    session=session,\n                    secret_store=vault,\n                    contexto=contexto,\n                    configuracao_id=config_id,\n                    evidencia_servidor=str(evidencia_servidor or ""),\n                )\n                st.info(\n                    "O mapa abaixo e a prova real da Browser API Key em http://localhost:8765. Se carregar e ficar verde, copie a evidencia final exibida dentro do proprio teste. "\n                    "Se o Google rejeitar a chave, a integracao continua nao homologada."\n                )\n                components.iframe(preparacao.url, height=430, scrolling=False)\n\n        if spec.provedor == "gemini" and existing is not None:\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "obter_evidencia_confirmada_google_maps" in primeira
    assert "maps_browser_proof_token" in primeira
    assert "last_real_maps_full_healthcheck_evidence" in primeira
    assert "Concluir teste e preencher evidência" in primeira
    assert "A referência foi preenchida automaticamente" in primeira
    assert "components.iframe(preparacao.url, height=520" in primeira
    assert "components.html(preparacao.html" not in primeira
    assert "registrar_homologacao" not in primeira
