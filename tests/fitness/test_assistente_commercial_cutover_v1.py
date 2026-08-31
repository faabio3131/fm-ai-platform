"""Fitness guard do cutover comercial do Assistente de Atendimento V1."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_commercial_assistant_no_longer_delegates_to_mica() -> None:
    source = _text("core/assistente_atendimento/ui_streamlit.py")
    assert "core.mica" not in source
    assert "render_mica_v1" not in source
    assert "OperacaoMicaFake" not in source
    assert "RuntimeAssistenteAtendimentoV1" in source


def test_commercial_app_passes_authenticated_identity_to_assistant() -> None:
    source = _text("app.py")
    assert "render_assistente_atendimento_v1(" in source
    assert "identidade=CURRENT_IDENTITY" in source


def test_commercial_runtime_uses_canonical_checkout_and_real_scope() -> None:
    runtime = _text("application/assistente_atendimento_runtime.py")
    checkout = _text("core/assistente_atendimento/checkout_adapter.py")

    assert "CheckoutAssistenteV1" in runtime
    assert "listar_produtos_legados(" in runtime
    assert "tenant_id=contexto.tenant_id" in runtime
    assert "unidade_id=contexto.unidade_id" in runtime
    assert "executar_checkout_v1" in checkout
    assert "FM_AI_TEST_TENANT" not in runtime
    assert "FM_AI_TEST_UNIDADE" not in runtime
    assert "tenant-demo" not in runtime
    assert "unidade-demo" not in runtime


def test_commercial_runtime_uses_crm_contact_vault_and_ai_router() -> None:
    runtime = _text("application/assistente_atendimento_runtime.py")
    clientes = _text("infra/assistente_atendimento/clientes_sqlalchemy.py")

    assert "EncryptedSQLAlchemySecretStore" in runtime
    assert "construir_ai_model_router" in runtime
    assert "CapabilityIA.ATENDIMENTO_INTERPRETACAO" in runtime
    assert "EncryptedSQLAlchemyContactStore" in clientes
    assert "RepositorioClientesCRMSQLAlchemy" in clientes
