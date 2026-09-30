from datetime import datetime, timezone

from core.integracoes.google_maps import ErroGoogleMaps, ErroGoogleMapsTransitorio
from infra.integracoes.google_maps_healthcheck import (
    _classificar_falha_google_maps,
    _evidencia,
)
from scripts.wire_google_maps_real_healthcheck_v1 import aplicar


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


def test_evidencia_maps_servidor_e_sanitizada_e_deterministica() -> None:
    contexto = _Contexto()
    agora = datetime(2026, 8, 18, 16, 0, tzinfo=timezone.utc)
    primeira = _evidencia(
        contexto=contexto,  # type: ignore[arg-type]
        configuracao_id="mapas--google_maps",
        origem="Origem formatada",
        destino="Destino formatado",
        distancia_metros=4200,
        duracao_segundos=900,
        agora=agora,
    )
    segunda = _evidencia(
        contexto=contexto,  # type: ignore[arg-type]
        configuracao_id="mapas--google_maps",
        origem="Origem formatada",
        destino="Destino formatado",
        distancia_metros=4200,
        duracao_segundos=900,
        agora=agora,
    )
    assert primeira == segunda
    assert primeira.startswith("healthcheck://google-maps-server/20260818T160000Z/")
    assert "Origem formatada" not in primeira
    assert "Destino formatado" not in primeira
    assert "key" not in primeira.casefold()


def test_patch_ui_adiciona_maps_sem_auto_homologar_e_e_idempotente() -> None:
    origem = '''from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini\n\n        st.markdown("**Homologação**")\n        ultima_evidencia_real = st.session_state.get(\n            _key(spec, "last_real_healthcheck_evidence")\n        )\n        if spec.provedor == "gemini" and ultima_evidencia_real:\n            st.success("Último healthcheck externo real do Gemini concluído com sucesso.")\n            st.code(str(ultima_evidencia_real), language=None)\n            st.caption(\n                "Copie esta referência para o campo de evidência abaixo. Ela não contém a API key nem conteúdo sensível."\n            )\n        st.caption(\n\n        if spec.provedor == "gemini" and existing is not None:\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "executar_healthcheck_google_maps" in primeira
    assert "Testar Google Maps real (servidor)" in primeira
    assert "A chave de navegador ainda precisa de prova real no navegador" in primeira
    assert "registrar_homologacao" not in primeira


def test_classificacao_google_maps_e_sanitizada_e_acionavel() -> None:
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("Google Maps rejeitou requisicao HTTP 403")
    ) == "google_maps_server_key_sem_permissao"
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("geocodificacao Google Maps: REQUEST_DENIED")
    ) == "google_maps_geocoding_rejeitado"
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("geocodificacao Google Maps: BILLING_NOT_ENABLED")
    ) == "google_maps_billing_nao_ativo"
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("geocodificacao Google Maps: API_NOT_AUTHORIZED")
    ) == "google_maps_geocoding_nao_autorizado"
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("geocodificacao Google Maps: API_KEY_INVALID")
    ) == "google_maps_server_key_invalida"
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("geocodificacao Google Maps: APPLICATION_RESTRICTION")
    ) == "google_maps_server_key_restricao_aplicacao"
    assert _classificar_falha_google_maps(
        ErroGoogleMaps("geocodificacao Google Maps: OVER_QUERY_LIMIT")
    ) == "google_maps_quota_ou_faturamento"
    assert _classificar_falha_google_maps(
        ErroGoogleMapsTransitorio("Google Maps respondeu HTTP 503 apos retries")
    ) == "google_maps_provedor_indisponivel"
    assert _classificar_falha_google_maps(
        ErroGoogleMapsTransitorio("Google Maps respondeu HTTP 429 apos retries")
    ) == "google_maps_quota_ou_faturamento"
