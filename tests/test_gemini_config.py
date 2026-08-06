from pathlib import Path
from types import SimpleNamespace

import pytest

import gemini_config


class FakeModels:
    def __init__(self, names=("models/gemini-3.6-flash",)):
        self._models = [
            SimpleNamespace(name=name, supported_actions=["generateContent"])
            for name in names
        ]
        self.generated = []

    def list(self, **_kwargs):
        return self._models

    def generate_content(self, **kwargs):
        self.generated.append(kwargs)
        return SimpleNamespace(text="ok")


class FakeClient:
    def __init__(self, names=("models/gemini-3.6-flash",)):
        self.models = FakeModels(names)
        self.files = SimpleNamespace(upload=lambda **kwargs: kwargs)


@pytest.fixture(autouse=True)
def clean_gateway(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    gemini_config.reset_caches()
    yield
    gemini_config.reset_caches()


def use_client(monkeypatch, names=("models/gemini-3.6-flash",)):
    client = FakeClient(names)
    monkeypatch.setattr(gemini_config.genai, "Client", lambda **_kwargs: client)
    return client


def test_default_model_is_selected_only_when_available(monkeypatch):
    use_client(monkeypatch)
    assert gemini_config.get_model_name() == "gemini-3.6-flash"


@pytest.mark.parametrize("model", ["gemini-2.0-flash", "gemini-2.0-flash-001"])
def test_decommissioned_gemini_2_models_are_always_rejected(monkeypatch, model):
    monkeypatch.setenv("GEMINI_MODEL", f"models/{model}")
    use_client(monkeypatch, (f"models/{model}", "models/gemini-3.6-flash"))
    with pytest.raises(gemini_config.GeminiConfigurationError, match="foi desativado"):
        gemini_config.get_model_name()


def test_discovered_stable_flash_is_used_when_default_is_unavailable(monkeypatch):
    use_client(
        monkeypatch,
        (
            "models/gemini-4.0-flash-preview",
            "models/gemini-4.0-flash-001",
            "models/gemini-2.0-flash",
        ),
    )
    assert gemini_config.get_model_name() == "gemini-4.0-flash-001"


def test_safe_failure_when_no_compatible_stable_flash_is_available(monkeypatch):
    use_client(
        monkeypatch,
        ("models/gemini-4.0-pro", "models/gemini-4.0-flash-latest"),
    )
    with pytest.raises(
        gemini_config.GeminiConfigurationError, match="Nenhum modelo Flash estável"
    ):
        gemini_config.get_model_name()


def test_configured_model_is_normalized_and_used(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", " models/gemini-1.5-flash-002 ")
    use_client(monkeypatch, ("models/gemini-1.5-flash-002",))
    assert gemini_config.get_model_name() == "gemini-1.5-flash-002"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("gemini-2.0-flash", "gemini-2.0-flash"), (" models/gemini-pro ", "gemini-pro")],
)
def test_normalize_model_name(raw, expected):
    assert gemini_config.normalize_model_name(raw) == expected


def test_invalid_configured_model_is_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-does-not-exist")
    use_client(monkeypatch)
    with pytest.raises(
        gemini_config.GeminiConfigurationError, match="não está disponível"
    ):
        gemini_config.get_model_name()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("404 NOT_FOUND"), gemini_config.GeminiConfigurationError),
        (RuntimeError("429 RESOURCE_EXHAUSTED"), gemini_config.GeminiQuotaError),
        (RuntimeError("503 service unavailable"), gemini_config.GeminiTransientError),
    ],
)
def test_generate_content_translates_api_failures(monkeypatch, error, expected):
    client = use_client(monkeypatch)
    monkeypatch.setattr(
        client.models,
        "generate_content",
        lambda **_kwargs: (_ for _ in ()).throw(error),
    )
    with pytest.raises(expected):
        gemini_config.generate_content(contents="hello")


def test_missing_key_is_reported_without_creating_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    gemini_config.reset_caches()
    with pytest.raises(gemini_config.GeminiConfigurationError, match="não configurada"):
        gemini_config.generate_content(contents="hello")


def test_invalid_key_is_reported_safely(monkeypatch):
    monkeypatch.setattr(
        gemini_config.genai,
        "Client",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("401 API key not valid: secret")
        ),
    )
    with pytest.raises(
        gemini_config.GeminiConfigurationError, match="inválida"
    ) as caught:
        gemini_config.generate_content(contents="hello")
    assert "secret" not in str(caught.value)


def test_key_change_creates_new_client_and_model_cache(monkeypatch):
    created = {}

    def factory(**kwargs):
        key = kwargs["api_key"]
        client = FakeClient((f"models/gemini-{key}-flash",))
        created[key] = client
        return client

    monkeypatch.setattr(gemini_config.genai, "Client", factory)
    monkeypatch.setenv("GEMINI_API_KEY", "3.6")
    assert gemini_config.get_model_name() == "gemini-3.6-flash"

    monkeypatch.setenv("GEMINI_API_KEY", "4.0")
    assert gemini_config.get_model_name() == "gemini-4.0-flash"
    assert created["3.6"] is not created["4.0"]


def test_same_key_reuses_client(monkeypatch):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs["api_key"])
        return FakeClient()

    monkeypatch.setattr(gemini_config.genai, "Client", factory)
    assert gemini_config.get_client() is gemini_config.get_client()
    assert calls == ["test-key"]


def test_generate_content_uses_models_prefix_free_model(monkeypatch):
    client = use_client(monkeypatch, ("models/gemini-3.6-flash",))
    gemini_config.generate_content(contents="hello")
    assert client.models.generated[-1]["model"] == "gemini-3.6-flash"


def test_http_400_invalid_argument_is_not_reported_as_invalid_key(monkeypatch):
    client = use_client(monkeypatch)
    monkeypatch.setattr(
        client.models,
        "generate_content",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("400 INVALID_ARGUMENT bad contents")
        ),
    )
    with pytest.raises(
        gemini_config.GeminiConfigurationError, match="Requisição Gemini inválida"
    ) as caught:
        gemini_config.generate_content(contents={"bad": object()})
    assert "GEMINI_API_KEY inválida" not in str(caught.value)


@pytest.mark.parametrize(
    ("error", "expected_text"),
    [
        (
            RuntimeError("403 PERMISSION_DENIED"),
            "GEMINI_API_KEY inválida ou sem permissão",
        ),
        (RuntimeError("404 NOT_FOUND"), "Modelo Gemini indisponível"),
        (RuntimeError("429 RESOURCE_EXHAUSTED"), "Cota do Gemini atingida"),
    ],
)
def test_specific_error_messages_are_safe(monkeypatch, error, expected_text):
    client = use_client(monkeypatch)
    monkeypatch.setattr(
        client.models,
        "generate_content",
        lambda **_kwargs: (_ for _ in ()).throw(error),
    )
    with pytest.raises(gemini_config.GeminiGatewayError, match=expected_text) as caught:
        gemini_config.generate_content(contents="hello")
    assert "test-key" not in str(caught.value)


def test_app_has_no_direct_sdk_generation_calls():
    source = Path("app.py").read_text(encoding="utf-8")
    assert ".models.generate_content(" not in source
    assert ".files.upload(" not in source


def test_app_loads_streamlit_secret_before_gateway_import():
    source = Path("app.py").read_text(encoding="utf-8")
    secret_pos = source.index("st.secrets")
    import_pos = source.index("from gemini_config import generate_content, upload_file")
    assert secret_pos < import_pos
