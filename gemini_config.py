"""Configuração e gateway centralizados para a API Gemini.

O módulo é deliberadamente lazy: importar a aplicação não consulta a API. A
primeira geração lista os modelos uma única vez e valida a escolha antes do uso.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from google import genai


# O padrão só é escolhido depois de confirmar que foi retornado pela chave atual.
DEFAULT_MODEL = "gemini-3.6-flash"
DECOMMISSIONED_MODELS = frozenset({"gemini-2.0-flash", "gemini-2.0-flash-001"})
_UNSTABLE_MARKERS = ("preview", "experimental", "-exp", "latest")


class GeminiGatewayError(RuntimeError):
    """Erro seguro e acionável da integração Gemini."""


class GeminiConfigurationError(GeminiGatewayError):
    """Configuração ausente ou incompatível com a conta atual."""


class GeminiQuotaError(GeminiGatewayError):
    """Cota da API esgotada ou limite de requisições atingido."""


class GeminiTransientError(GeminiGatewayError):
    """Falha temporária no serviço Gemini."""


def normalize_model_name(name: str) -> str:
    """Retorna o identificador aceito por ``generate_content``."""
    normalized = name.strip()
    if normalized.startswith("models/"):
        normalized = normalized.removeprefix("models/")
    if not normalized:
        raise GeminiConfigurationError("GEMINI_MODEL não pode ser vazio.")
    return normalized


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY não configurada; defina a variável no ambiente."
        )
    return key


@lru_cache(maxsize=4)
def _get_client_for_key(api_key: str) -> Any:
    """Cria e reutiliza clientes por chave, sem registrar a credencial."""
    return genai.Client(api_key=api_key)


def get_client() -> Any:
    """Retorna o cliente Gemini da chave atualmente configurada."""
    return _get_client_for_key(_api_key())


def _supports_generate_content(model: Any) -> bool:
    actions = getattr(model, "supported_actions", None)
    if actions is None:
        actions = getattr(model, "supported_generation_methods", ())
    return "generateContent" in (actions or ())


@lru_cache(maxsize=4)
def _list_generate_content_models_for_key(api_key: str) -> tuple[str, ...]:
    """Lista modelos compatíveis com geração para uma chave específica."""
    try:
        models = _get_client_for_key(api_key).models.list(config={"page_size": 1000})
        names = {
            normalize_model_name(model.name)
            for model in models
            if getattr(model, "name", None) and _supports_generate_content(model)
        }
        return tuple(sorted(names))
    except GeminiGatewayError:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc


def list_generate_content_models() -> tuple[str, ...]:
    """Lista os modelos compatíveis com geração para a chave atual."""
    return _list_generate_content_models_for_key(_api_key())


def _is_stable(name: str) -> bool:
    lowered = name.lower()
    return not any(marker in lowered for marker in _UNSTABLE_MARKERS)


@lru_cache(maxsize=16)
def _get_model_name_for_config(api_key: str, configured: str | None) -> str:
    """Valida a configuração para uma chave/modelo específicos."""
    available = _list_generate_content_models_for_key(api_key)
    if configured is not None:
        selected = normalize_model_name(configured)
        if selected in DECOMMISSIONED_MODELS:
            raise GeminiConfigurationError(
                f"O modelo configurado '{selected}' foi desativado e não pode ser usado."
            )
        if selected not in available:
            raise GeminiConfigurationError(
                f"O modelo configurado '{selected}' não está disponível para esta chave."
            )
        return selected

    if DEFAULT_MODEL in available:
        return DEFAULT_MODEL

    stable_flash = sorted(
        name
        for name in available
        if _is_stable(name)
        and "flash" in name.lower()
        and name not in DECOMMISSIONED_MODELS
    )
    if stable_flash:
        return stable_flash[-1]
    raise GeminiConfigurationError(
        "Nenhum modelo Flash estável compatível com generate_content está disponível."
    )


def get_model_name() -> str:
    """Valida GEMINI_MODEL ou escolhe um modelo estável realmente disponível."""
    return _get_model_name_for_config(_api_key(), os.getenv("GEMINI_MODEL"))


def _status_code(exc: Exception) -> int | None:
    for value in (getattr(exc, "code", None), getattr(exc, "status_code", None)):
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    text = str(exc).lower()
    for code in (400, 401, 403, 404, 429, 500, 502, 503, 504):
        if str(code) in text:
            return code
    return None


def _translate_error(exc: Exception) -> GeminiGatewayError:
    code = _status_code(exc)
    text = str(exc).lower()
    if code == 400:
        return GeminiConfigurationError(
            "Requisição Gemini inválida; revise GEMINI_MODEL, contents e config enviados."
        )
    if code == 404:
        return GeminiConfigurationError(
            "Modelo Gemini indisponível para esta conta; revise GEMINI_MODEL."
        )
    if code == 429:
        return GeminiQuotaError("Cota do Gemini atingida; tente novamente mais tarde.")
    if code in (401, 403) or "api key not valid" in text or "invalid api key" in text:
        return GeminiConfigurationError("GEMINI_API_KEY inválida ou sem permissão.")
    if code in (500, 502, 503, 504) or "timeout" in text or "temporar" in text:
        return GeminiTransientError(
            "Serviço Gemini temporariamente indisponível; tente novamente."
        )
    return GeminiGatewayError("Falha ao comunicar com o serviço Gemini.")


def generate_content(*, contents: Any, config: Any | None = None) -> Any:
    """Gateway único de geração de conteúdo."""
    try:
        kwargs = {"model": get_model_name(), "contents": contents}
        if config is not None:
            kwargs["config"] = config
        return get_client().models.generate_content(**kwargs)
    except GeminiGatewayError:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc


def upload_file(*, file: str) -> Any:
    """Gateway único para uploads exigidos por entradas multimodais."""
    try:
        _api_key()
        return get_client().files.upload(file=file)
    except GeminiGatewayError:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc


def reset_caches() -> None:
    """Limpa estado lazy; destinado a testes e mudanças controladas de ambiente."""
    _get_client_for_key.cache_clear()
    _list_generate_content_models_for_key.cache_clear()
    _get_model_name_for_config.cache_clear()
