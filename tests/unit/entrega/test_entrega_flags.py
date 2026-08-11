from core.entrega import entrega_v1_enabled


def test_flag_entrega_fechada_sem_test_mode(monkeypatch):
    monkeypatch.setenv("FM_AI_ENTREGA_V1", "1")
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)

    assert entrega_v1_enabled() is False


def test_flag_entrega_abre_somente_em_teste(monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_ENTREGA_V1", "1")

    assert entrega_v1_enabled() is True
