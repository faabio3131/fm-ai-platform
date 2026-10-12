from application.ai_router_runtime import _capabilities
from core.ai_router import CapabilityIA


def test_gemini_preserva_transcricao_quando_config_legada_declara_capability_textual() -> None:
    capabilities = _capabilities(
        provider="gemini",
        parametros={"capability": "tool_planning"},
    )

    assert capabilities == (
        CapabilityIA.TOOL_PLANNING,
        CapabilityIA.ATENDIMENTO_TRANSCRICAO,
    )


def test_gemini_sem_override_anuncia_texto_e_transcricao() -> None:
    capabilities = _capabilities(provider="gemini", parametros={})

    assert CapabilityIA.TOOL_PLANNING in capabilities
    assert CapabilityIA.ATENDIMENTO_INTERPRETACAO in capabilities
    assert CapabilityIA.ATENDIMENTO_TRANSCRICAO in capabilities
