from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "core" / "delivery" / "ui_streamlit.py"
APP = ROOT / "app.py"
FACADE = ROOT / "application" / "delivery_operacao_comercial.py"


def _texto(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ui_delivery_comercial_nao_contem_runtime_demo_ou_escopo_fake() -> None:
    texto = _texto(UI)
    proibidos = (
        "RuntimeDeliveryTeste",
        "runtime_teste",
        "tenant-demo",
        "unidade-demo",
        "cliente-demo",
        "_delivery_runtime",
    )
    for token in proibidos:
        assert token not in texto


def test_ui_delivery_recebe_identidade_e_session_factory_sem_tenant_livre() -> None:
    texto = _texto(UI)
    assert "identidade: IdentidadeUsuario" in texto
    assert "session_factory: SessionFactory" in texto
    assert "listar_clientes_delivery_comercial" in texto
    assert "resolver_contexto_jornada_delivery" in texto
    assert "tenant_id = st." not in texto
    assert "unidade_id = st." not in texto


def test_app_liga_delivery_com_feature_flag_rbac_e_identidade_autenticada() -> None:
    texto = _texto(APP)
    assert "delivery_v1_enabled() and delivery_v1_access_allowed(" in texto
    assert '"🛵 Delivery Próprio"' in texto
    assert "render_delivery_v1(" in texto
    assert "session_factory=SessionLocal" in texto
    assert "identidade=CURRENT_IDENTITY" in texto


def test_fachada_converge_checkout_estoque_e_entrega_canonicos() -> None:
    texto = _texto(FACADE)
    obrigatorios = (
        "preparar_snapshot_ficha_estoque_v1",
        "executar_checkout_delivery_comercial_em_transacao",
        "RepositorioEntregaSQLAlchemy",
        "ServicoEntrega",
        "transicionar_pedido",
        "cancelar_pagamento",
        "liberar_reserva",
        "UnitOfWorkV1",
    )
    for token in obrigatorios:
        assert token in texto
    assert "ServicoDelivery(" in texto
    assert ".confirmar(" not in texto
    assert "RuntimeDeliveryTeste" not in texto


def test_fachada_nao_cria_commit_ou_rollback_fora_da_uow() -> None:
    texto = _texto(FACADE)
    assert ".session.commit(" not in texto
    assert ".session.rollback(" not in texto
    assert ".commit()" in texto
    assert "uow.commit()" in texto


def test_cancelamento_pago_falha_fechado_em_vez_de_estornar_automaticamente() -> None:
    texto = _texto(FACADE)
    assert "pagamento_liquidado_exige_fluxo_financeiro_de_estorno" in texto
    assert "registrar_estorno(" not in texto
