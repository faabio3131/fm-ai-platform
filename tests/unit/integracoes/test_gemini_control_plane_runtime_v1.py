from __future__ import annotations

import pytest

import gemini_config


def test_gemini_comercial_rejeita_api_key_global_mesmo_se_variavel_existir(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "segredo-global-nao-deve-ser-usado")
    monkeypatch.setattr(gemini_config, "_runtime_commercial", lambda: True)

    with pytest.raises(
        gemini_config.GeminiConfigurationError,
        match="GEMINI_API_KEY global não é fonte válida no runtime comercial",
    ):
        gemini_config._api_key()


def test_generate_content_comercial_delega_exclusivamente_ao_control_plane(monkeypatch) -> None:
    sentinel = object()
    chamadas: list[tuple[object, object | None]] = []

    monkeypatch.setattr(gemini_config, "_runtime_commercial", lambda: True)

    def fake_commercial_generate_content(*, contents, config):
        chamadas.append((contents, config))
        return sentinel

    monkeypatch.setattr(
        gemini_config,
        "_commercial_generate_content",
        fake_commercial_generate_content,
    )
    monkeypatch.setattr(
        gemini_config,
        "get_client",
        lambda: pytest.fail("cliente por GEMINI_API_KEY não pode ser usado em comercial"),
    )

    result = gemini_config.generate_content(contents="teste seguro")

    assert result is sentinel
    assert chamadas == [("teste seguro", None)]


def test_upload_global_fica_bloqueado_no_runtime_comercial(monkeypatch) -> None:
    monkeypatch.setattr(gemini_config, "_runtime_commercial", lambda: True)

    with pytest.raises(
        gemini_config.GeminiConfigurationError,
        match="Upload Gemini por chave global está bloqueado no runtime comercial",
    ):
        gemini_config.upload_file(file="qualquer-arquivo")
