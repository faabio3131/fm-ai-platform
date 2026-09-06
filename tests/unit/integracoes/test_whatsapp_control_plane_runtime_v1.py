from __future__ import annotations

from pathlib import Path

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")
CRM_MARKETING_SOURCE = Path("application/crm_marketing_comercial.py").read_text(
    encoding="utf-8"
)
CRM_SERVICE_SOURCE = Path("core/crm/servicos.py").read_text(encoding="utf-8")


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
    )[1].split("with sub_crm2:", 1)[0]

    assert "despachar_resgate_whatsapp_legado(" in trecho
    assert "_enviar_whatsapp_control_plane(" not in trecho
    assert "resultado_envio.enviado" in trecho
    assert "st.success(" in trecho
    assert "st.warning(" in trecho
    assert "except Exception:" in trecho
    assert "st.error(" in trecho

    assert "ServicoCRM(" in CRM_MARKETING_SOURCE
    assert "LeitorConsentimentosMarketingSQLAlchemy" in CRM_MARKETING_SOURCE
    assert "servico.despachar_marketing(" in CRM_MARKETING_SOURCE
    assert "CanalMarketing.WHATSAPP" in CRM_MARKETING_SOURCE
    assert "FinalidadeMarketing.PROMOCOES" in CRM_MARKETING_SOURCE
    assert "if not self.pode_enviar_marketing(" in CRM_SERVICE_SOURCE
    assert (
        'ResultadoDespachoMarketing(False, "marketing_sem_consentimento")'
        in CRM_SERVICE_SOURCE
    )


def test_forecasting_comercial_usa_control_plane_e_sanitiza_falhas() -> None:
    inicio = "def executar_forecasting_e_alertar"
    fim = "# Inicialização legada governada pela camada Application."

    assert inicio in APP_SOURCE
    assert fim in APP_SOURCE

    trecho = APP_SOURCE.split(
        inicio,
        1,
    )[1].split(
        fim,
        1,
    )[0]

    assert "_enviar_whatsapp_control_plane(" in trecho
    assert "requests.post(" not in trecho
    assert "config_meta" not in trecho
    assert "except Exception:" in trecho
    assert "except Exception as" not in trecho
    assert "Verifique as integrações Gemini e Meta/WhatsApp desta unidade." in trecho
