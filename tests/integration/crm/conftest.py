import pytest


@pytest.fixture(autouse=True)
def _crm_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
