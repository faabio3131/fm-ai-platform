from __future__ import annotations

from pathlib import Path

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_configuracao_meta_legada_so_e_inicializada_em_teste() -> None:
    assert (
        'if is_test_mode() and db.query(ConfiguracaoMeta).count() == 0:'
        in APP_SOURCE
    )
    assert 'if db.query(ConfiguracaoMeta).count() == 0:' not in APP_SOURCE.replace(
        'if is_test_mode() and db.query(ConfiguracaoMeta).count() == 0:', ''
    )


def test_pdv_comercial_nao_carrega_configuracao_legada_de_gateway() -> None:
    trecho_esperado = '''config_gtw = (
        db_pdv.query(ConfiguracaoMeta).first()
        if is_test_mode()
        else None
    )'''
    assert trecho_esperado in APP_SOURCE
    assert 'config_gtw = db_pdv.query(ConfiguracaoMeta).first()' not in APP_SOURCE


def test_gemini_comercial_declara_disponibilidade_pelo_control_plane() -> None:
    assert 'def _gemini_disponivel_no_runtime() -> bool:' in APP_SOURCE
    assert 'if not RUNTIME_SETTINGS.commercial:' in APP_SOURCE
    assert 'FabricaAdaptersExternos(' in APP_SOURCE
    assert 'configuracao_id="ia.generativa--gemini"' in APP_SOURCE
    assert 'GENAI_DISPONIVEL = _gemini_disponivel_no_runtime()' in APP_SOURCE
    assert (
        'GENAI_DISPONIVEL = is_test_mode() or bool(GEMINI_API_KEY)'
        not in APP_SOURCE
    )

