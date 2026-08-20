"""Configuração e gateway centralizados para a API Gemini.

Em desenvolvimento/teste, mantém compatibilidade com ``GEMINI_API_KEY`` para
fixtures e execução local. Em runtime comercial, a chave global é proibida como
fonte operacional: o Gemini é resolvido exclusivamente pelo control plane seguro,
isolado por tenant/unidade e somente após homologação da integração.
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


def _runtime_commercial() -> bool:
    """Detecta runtime comercial sem criar dependência no import da aplicação."""

    try:
        from core.runtime import load_runtime_settings

        return bool(load_runtime_settings().commercial)
    except Exception:
        # Falha fechada apenas para a decisão de usar o caminho comercial. Testes
        # unitários isolados de gemini_config continuam exercitando o gateway legado.
        return False


def _api_key() -> str:
    if _runtime_commercial():
        raise GeminiConfigurationError(
            "GEMINI_API_KEY global não é fonte válida no runtime comercial; "
            "configure e homologue o Gemini em Administração / Proprietário > "
            "Integrações e Credenciais."
        )
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY não configurada; defina a variável no ambiente de desenvolvimento/teste."
        )
    return key


@lru_cache(maxsize=4)
def _get_client_for_key(api_key: str) -> Any:
    """Cria e reutiliza clientes por chave, sem registrar a credencial."""
    return genai.Client(api_key=api_key)


def get_client() -> Any:
    """Retorna o cliente Gemini da chave de desenvolvimento/teste."""
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
    """Lista modelos compatíveis com geração para a chave atual em dev/teste."""
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
    """Valida GEMINI_MODEL ou escolhe um modelo estável em dev/teste."""
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
            "Requisição Gemini inválida; revise modelo, contents e config enviados."
        )
    if code == 404:
        return GeminiConfigurationError(
            "Modelo Gemini indisponível para esta conta; revise a configuração do provedor."
        )
    if code == 429:
        return GeminiQuotaError("Cota do Gemini atingida; tente novamente mais tarde.")
    if code in (401, 403) or "api key not valid" in text or "invalid api key" in text:
        return GeminiConfigurationError("Credencial Gemini inválida ou sem permissão.")
    if code in (500, 502, 503, 504) or "timeout" in text or "temporar" in text:
        return GeminiTransientError(
            "Serviço Gemini temporariamente indisponível; tente novamente."
        )
    return GeminiGatewayError("Falha ao comunicar com o serviço Gemini.")


def _commercial_generate_content(*, contents: Any, config: Any | None) -> Any:
    if config is not None:
        raise GeminiConfigurationError(
            "Configuração ad hoc do Gemini não é permitida no runtime comercial. "
            "Use o modelo homologado no control plane."
        )

    try:
        import streamlit as st

        from core.integracoes.modelos import ErroConfiguracaoServico
        from core.runtime import build_engine, load_runtime_settings
        from core.seguranca.autenticacao import IdentidadeUsuario
        from infra.integracoes import FabricaAdaptersExternos
        from infra.seguranca.session_guard import build_session_factory
        from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

        identity = st.session_state.get("_fm_ai_authenticated_identity_v1")
        if not isinstance(identity, IdentidadeUsuario) or not identity.ativo:
            raise GeminiConfigurationError(
                "Sessão autenticada necessária para usar o Gemini comercial."
            )

        settings = load_runtime_settings()
        engine = build_engine(settings)
        session_factory = build_session_factory(
            engine=engine,
            commercial=settings.commercial,
        )
        session = session_factory()
        try:
            vault = EncryptedSQLAlchemySecretStore(session)
            adapter = FabricaAdaptersExternos(
                session=session,
                secret_store=vault,
            ).gemini(
                contexto=identity.contexto(origem="gemini_config.runtime"),
                configuracao_id="ia.generativa--gemini",
            )
            return adapter.gerar(contents)
        finally:
            session.close()
    except GeminiGatewayError:
        raise
    except ErroConfiguracaoServico as exc:
        raise GeminiConfigurationError(
            "Gemini comercial não está configurado, habilitado e homologado para esta unidade."
        ) from exc
    except Exception as exc:
        raise _translate_error(exc) from exc


def generate_content(*, contents: Any, config: Any | None = None) -> Any:
    """Gera conteúdo pelo caminho adequado ao ambiente.

    Produção/staging usam exclusivamente o control plane por tenant/unidade. O
    gateway baseado em variável de ambiente permanece apenas para desenvolvimento
    e testes isolados.
    """

    if _runtime_commercial():
        return _commercial_generate_content(contents=contents, config=config)

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
    """Gateway de upload legado, restrito a desenvolvimento/teste.

    O runtime comercial atual envia entradas multimodais diretamente em
    ``generate_content`` e não pode usar chave global para upload.
    """

    if _runtime_commercial():
        raise GeminiConfigurationError(
            "Upload Gemini por chave global está bloqueado no runtime comercial."
        )
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
