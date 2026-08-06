import importlib


def test_test_mode_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    import test_mode

    importlib.reload(test_mode)
    assert test_mode.is_test_mode() is False
    runtime = test_mode.build_runtime()
    assert runtime.database_url == "sqlite:///./banco_erp_local.db"


def test_test_mode_uses_temp_sqlite_and_mocks(monkeypatch, tmp_path):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_TEST_TMPDIR", str(tmp_path))
    import test_mode

    importlib.reload(test_mode)
    runtime = test_mode.build_runtime()
    assert runtime.database_url.startswith("sqlite:///")
    assert "banco_erp_local.db" not in runtime.database_url
    assert test_mode.mock_generate_content(contents="cardapio").text.startswith("[")
    assert "erro 429" in str(
        _raises(lambda: test_mode.mock_generate_content(contents="FM_AI_MOCK_429"))
    )


def _raises(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - test helper captures expected mock exception
        return exc
    raise AssertionError("expected exception")
