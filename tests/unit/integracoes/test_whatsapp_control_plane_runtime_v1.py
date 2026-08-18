from __future__ import annotations

from pathlib import Path


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_whatsapp_comercial_nao_usa_http_ou_token_legado() -> None:
    assert "import requests" not in APP_SOURCE
    assert "requests.post(" not in APP_SOURCE
    assert "config_meta.whatsapp_token" not in APP_SOURCE
    assert "config_meta.whatsapp_phone_id" not in APP_SOURCE


def test_whatsapp_comercial_resolve_adapter_pelo_control_plane() -> None:
    assert "def _enviar_whatsapp_control_plane(" in APP_SOURCE
    assert 'configuracao_id="mensageria.whatsapp--meta"' in APP_SOURCE
    assert "FabricaAdaptersExternos(" in APP_SOURCE
    assert ").meta(" in APP_SOURCE
    assert "return adapter.enviar_whatsapp(" in APP_SOURCE


def test_crm_so_declara_sucesso_apos_confirmacao_do_envio() -> None:
    trecho = APP_SOURCE.split(
        'f"🚀 Disparar Campanha WhatsApp para {cli.nome}"', 1
    )[1].split("else:\n            st.success(", 1)[0]

    assert "_enviar_whatsapp_control_plane(" in trecho
    assert "if not mensagem_id:" in trecho
    assert 'raise RuntimeError("envio_sem_confirmacao")' in trecho
    assert "st.success(" in trecho
    assert "except Exception:" in trecho
    assert "st.error(" in trecho


def test_forecasting_comercial_usa_control_plane_e_sanitiza_falhas() -> None:
    trecho = APP_SOURCE.split("def executar_forecasting_e_alertar", 1)[1].split(
        "def popular_dados_iniciais", 1
    )[0]

    assert "_enviar_whatsapp_control_plane(" in trecho
    assert "requests.post(" not in trecho
    assert "config_meta" not in trecho
    assert "except Exception:" in trecho
    assert "except Exception as" not in trecho
    assert "Verifique as integrações Gemini e Meta/WhatsApp desta unidade." in trecho
