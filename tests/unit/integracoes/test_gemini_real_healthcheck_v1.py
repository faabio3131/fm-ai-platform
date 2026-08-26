from datetime import datetime, timezone

from scripts.wire_gemini_real_healthcheck_v1 import aplicar

from infra.integracoes.gemini_healthcheck import _evidencia


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


def test_evidencia_healthcheck_e_sanitizada_e_deterministica() -> None:
    contexto = _Contexto()
    agora = datetime(2026, 8, 18, 15, 0, tzinfo=timezone.utc)
    primeira = _evidencia(
        contexto=contexto,  # type: ignore[arg-type]
        configuracao_id="ia.generativa--gemini",
        model="gemini-3.6-flash",
        texto="KORDENA_GEMINI_OK",
        agora=agora,
    )
    segunda = _evidencia(
        contexto=contexto,  # type: ignore[arg-type]
        configuracao_id="ia.generativa--gemini",
        model="gemini-3.6-flash",
        texto="KORDENA_GEMINI_OK",
        agora=agora,
    )
    assert primeira == segunda
    assert primeira.startswith("healthcheck://gemini/20260818T150000Z/gemini-3.6-flash/")
    assert "KORDENA_GEMINI_OK" not in primeira
    assert "api" not in primeira.casefold()


def test_patch_ui_adiciona_healthcheck_sem_auto_homologar_e_e_idempotente() -> None:
    origem = '''from infra.integracoes.repositorio_sqlalchemy import (\n    ProntidaoCredenciaisSQLAlchemy,\n    RepositorioConfiguracoesExternasSQLAlchemy,\n)\n\n        st.markdown("**Homologação**")\n        st.caption(\n\n        c_save, c_validate, c_homolog = st.columns(3)\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "executar_healthcheck_gemini" in primeira
    assert "Testar Gemini real antes de homologar" in primeira
    assert "registrar_homologacao" not in primeira

