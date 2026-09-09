from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_e_http_reutilizam_boundary_sem_duplicar_regra_wp017() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    http_source = (ROOT / "http_api" / "crm.py").read_text(encoding="utf-8")
    application_source = (
        ROOT / "application" / "crm_marketing_comercial.py"
    ).read_text(encoding="utf-8")

    assert "preparar_resgates_clientes_inativos(" in app_source
    assert "despachar_resgate_cliente_inativo(" in app_source
    assert "preparar_resgates_clientes_inativos(" in http_source
    assert "despachar_resgate_cliente_inativo(" in http_source

    inicio_prompt_legado = "Escreva uma mensagem curta, carinhosa e persuasiva de "
    for consumer_source in (app_source, http_source):
        assert "timedelta(days=15)" not in consumer_source
        assert inicio_prompt_legado not in consumer_source
        assert "crm-resgate-{" not in consumer_source

    assert "timedelta(days=15)" in application_source
    assert inicio_prompt_legado in application_source
    assert "crm-resgate-{legacy_cliente_id}-{data_atual}" in application_source


def test_wp017_nao_cria_segunda_rota_crm_na_web() -> None:
    page = ROOT / "web" / "src" / "app" / "admin" / "crm" / "page.tsx"
    workspace = (
        ROOT
        / "web"
        / "src"
        / "features"
        / "backoffice"
        / "crm"
        / "components"
        / "CrmWorkspace.tsx"
    )

    assert page.is_file()
    assert workspace.is_file()
    assert "listarResgatesInativos" in workspace.read_text(encoding="utf-8")
