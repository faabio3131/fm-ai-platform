from datetime import datetime, timezone

from infra.integracoes.meta_healthcheck import _evidencia, _recurso
from scripts.wire_meta_access_healthcheck_v1 import aplicar


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


def test_evidencia_meta_e_sanitizada_e_deterministica() -> None:
    evidencia = _evidencia(
        contexto=_Contexto(),  # type: ignore[arg-type]
        configuracao_id="social.facebook--meta",
        recurso_id="123456",
        agora=datetime(2026, 8, 19, 11, 0, tzinfo=timezone.utc),
    )
    assert evidencia.startswith("healthcheck://meta-access/20260819T110000Z/")
    assert "123456" not in evidencia
    assert "tenant-a" not in evidencia


def test_recurso_meta_separa_os_tres_servicos_sem_mutacao() -> None:
    assert _recurso("social.facebook", {"page_id": "page-1"}) == ("page-1", "name")
    assert _recurso("social.instagram", {"business_account_id": "ig-1"}) == (
        "ig-1",
        "username",
    )
    assert _recurso("mensageria.whatsapp", {"phone_number_id": "wa-1"}) == (
        "wa-1",
        "display_phone_number,verified_name",
    )


def test_patch_ui_adiciona_healthcheck_meta_sem_homologar_e_e_idempotente() -> None:
    origem = '''from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n\n        st.caption(\n            "O status Ativo só deve ser registrado após validação real do provedor. "\n\n        if spec.provedor == "google_maps" and existing is not None:\n            st.caption(\n                "O teste abaixo chama de verdade a Geocoding API e a Routes API usando somente a Server API Key salva no cofre. "\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "executar_healthcheck_meta" in primeira
    assert "Testar acesso real Meta (somente leitura)" in primeira
    assert "last_real_meta_access_evidence" in primeira
    assert "registrar_homologacao" not in primeira
    assert "publicar_facebook" not in primeira
    assert "publicar_instagram" not in primeira
    assert "enviar_whatsapp" not in primeira
