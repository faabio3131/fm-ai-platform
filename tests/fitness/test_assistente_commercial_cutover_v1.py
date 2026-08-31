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


def test_commercial_audio_uses_same_runtime_and_ai_router() -> None:
    ui = _text("core/assistente_atendimento/ui_streamlit.py")
    runtime = _text("application/assistente_atendimento_runtime.py")
    gateway = _text("infra/integracoes/transportes.py")

    assert "st.file_uploader(" in ui
    assert "runtime.interpretar_audio(" in ui
    assert "def interpretar_audio(" in runtime
    assert "CapabilityIA.ATENDIMENTO_TRANSCRICAO" in runtime
    assert "ConteudoAudioIA(" in runtime
    assert "ModalidadeEntrada.AUDIO" in runtime
    assert "types.Part.from_bytes(" in gateway
    assert "core.mica" not in runtime


def test_commercial_delivery_uses_maps_and_canonical_delivery_policy() -> None:
    ui = _text("core/assistente_atendimento/ui_streamlit.py")
    runtime = _text("application/assistente_atendimento_runtime.py")
    maps_quote = _text("infra/assistente_atendimento/entrega_maps.py")
    checkout = _text("core/assistente_atendimento/checkout_adapter.py")

    assert "runtime.cotar_entrega(" in ui
    assert "CotadorEntregaAssistenteGoogleMaps" in runtime
    assert "FabricaAdaptersExternos" in maps_quote
    assert ".google_maps(" in maps_quote
    assert "RepositorioPoliticaEntregaSQLAlchemy" in maps_quote
    assert "_area_para_cep(" in maps_quote
    assert "taxas=taxas_pedido" in checkout
    assert "core.delivery.runtime_teste" not in runtime
    assert "RuntimeDeliveryTeste" not in runtime
    assert "tenant-demo" not in maps_quote
    assert "unidade-demo" not in maps_quote


def test_delivery_policy_has_no_default_or_silent_backfill() -> None:
    migration = _text("migrations/delivery_policy_v1.py")
    repository = _text("infra/delivery/politica_sqlalchemy.py")

    assert "0033" in migration
    assert "create_all" in migration
    assert "backfill" in migration.casefold()
    assert "tenant_id" in repository
    assert "unidade_id" in repository
    assert "tenant-local" not in repository
    assert "unidade-local" not in repository


def test_commercial_payment_preference_is_fingerprinted_without_auto_settlement() -> None:
    ui = _text("core/assistente_atendimento/ui_streamlit.py")
    runtime = _text("application/assistente_atendimento_runtime.py")
    service = _text("core/assistente_atendimento/atendimento_servicos.py")
    checkout = _text("core/assistente_atendimento/checkout_adapter.py")

    assert "def definir_pagamento(" in runtime
    assert "pagamento_payload" in service
    assert "forma_pagamento_alterada_reconfirmacao_obrigatoria" in service
    assert "carrinho.pagamento.metodo" in checkout
    assert "ObservacaoPedido" in checkout
    assert "Pagamento ainda não confirmado" in checkout
    assert "confirmar_pagamento(" not in ui
    assert "confirmar_pagamento(" not in runtime
    assert "confirmar_pagamento(" not in service
    assert "confirmar_pagamento(" not in checkout



def test_commercial_assistant_reserves_canonical_stock_from_authoritative_ficha() -> None:
    adapter = _text("core/assistente_atendimento/checkout_adapter.py")
    bridge = _text("application/catalogo_estoque_cutover.py")
    checkout = _text("application/checkout.py")

    assert "executar_checkout_com_ficha_estoque_v1" in adapter
    assert "preparar_snapshot_ficha_estoque_v1" in bridge
    assert "listar_fichas_produto_legadas" in bridge
    assert "obter_insumo_por_id_legado" in bridge
    assert "for_update=True" in bridge
    assert "estoque_legado_divergente_do_ledger" in bridge
    assert "SnapshotFichaEstoque" in bridge
    assert "snapshot_estoque=snapshot" in bridge
    assert "reservar_estoque(" in checkout
    assert "baixar_estoque" not in adapter
    assert "baixar_estoque" not in bridge
