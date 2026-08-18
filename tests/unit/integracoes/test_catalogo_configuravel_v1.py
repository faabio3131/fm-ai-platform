from __future__ import annotations

import pytest

from core.integracoes import CATALOGO_V1, ErroConfiguracaoServico


@pytest.mark.parametrize(
    ("servico", "provedor", "parametros", "credenciais"),
    (
        (
            "social.facebook",
            "meta",
            {"page_id", "app_id"},
            {"access_token", "app_secret"},
        ),
        (
            "social.instagram",
            "meta",
            {"business_account_id", "facebook_page_id", "app_id"},
            {"access_token", "app_secret"},
        ),
        (
            "mensageria.whatsapp",
            "meta",
            {"business_account_id", "phone_number_id", "app_id"},
            {"access_token", "app_secret", "webhook_verify_token"},
        ),
        (
            "mapas",
            "google_maps",
            {"origin_address", "country_code", "language", "currency"},
            {"browser_api_key", "server_api_key"},
        ),
        (
            "pagamentos.pix",
            "pagbank",
            {"notification_url"},
            {"api_token"},
        ),
        (
            "pagamentos.pix",
            "mercado_pago",
            {"notification_url"},
            {"access_token", "webhook_secret"},
        ),
        (
            "ia.generativa",
            "gemini",
            {"model"},
            {"api_key"},
        ),
    ),
)
def test_catalogo_declara_contrato_minimo_por_servico_e_provedor(
    servico: str,
    provedor: str,
    parametros: set[str],
    credenciais: set[str],
) -> None:
    especificacao = CATALOGO_V1.obter(servico, provedor)
    assert especificacao.parametros_obrigatorios == parametros
    assert especificacao.credenciais_obrigatorias == credenciais


def test_catalogo_rejeita_provedor_nao_declarado_sem_fallback_silencioso() -> None:
    with pytest.raises(
        ErroConfiguracaoServico, match="servico_provedor_nao_suportado"
    ):
        CATALOGO_V1.obter("mapas", "provedor-inventado")
