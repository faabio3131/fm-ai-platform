from core.kds.flags import kds_v1_access_allowed, kds_v1_enabled
from core.seguranca import MATRIZ_PADRAO, Papel


def test_kds_desligado_por_padrao(monkeypatch):
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.delenv("FM_AI_KDS_V1", raising=False)
    assert kds_v1_enabled() is False


def test_kds_nao_ativa_fora_do_modo_de_teste(monkeypatch):
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.setenv("FM_AI_KDS_V1", "1")
    assert kds_v1_enabled() is False


def test_kds_exige_as_duas_flags(monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_KDS_V1", "1")
    assert kds_v1_enabled() is True


def test_kds_superficie_exige_permissao_de_visualizacao(monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_KDS_V1", "1")

    assert kds_v1_access_allowed(MATRIZ_PADRAO[Papel.COZINHA]) is True
    assert kds_v1_access_allowed(MATRIZ_PADRAO[Papel.EXPEDICAO]) is True
    assert kds_v1_access_allowed(MATRIZ_PADRAO[Papel.GARCOM]) is False
