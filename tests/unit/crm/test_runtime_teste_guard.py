import pytest

from core.crm.runtime_teste import EnvioMarketingTeste, RuntimeCRMTeste


def test_runtime_crm_teste_falha_fechado_fora_do_test_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)

    with pytest.raises(RuntimeError, match="runtime_crm_teste_fora_do_test_mode"):
        RuntimeCRMTeste()
    with pytest.raises(RuntimeError, match="runtime_crm_teste_fora_do_test_mode"):
        EnvioMarketingTeste()


def test_runtime_crm_teste_exige_flag_explicita(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")

    runtime = RuntimeCRMTeste()
    assert runtime.envio.envios == []
