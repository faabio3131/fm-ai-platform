from core.garcom.flags import garcom_v1_enabled


def test_flag_falha_fechada_sem_modo_teste(monkeypatch):
    monkeypatch.setenv("FM_AI_GARCOM_V1", "1")
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    assert garcom_v1_enabled() is False


def test_flag_exige_modo_teste_e_flag(monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_GARCOM_V1", "1")
    assert garcom_v1_enabled() is True


def test_flag_desabilitada_por_padrao(monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.delenv("FM_AI_GARCOM_V1", raising=False)
    assert garcom_v1_enabled() is False
