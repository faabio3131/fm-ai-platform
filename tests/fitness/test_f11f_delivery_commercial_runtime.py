from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "fase11f-delivery-commercial-runtime-e2e.yml"
CONFIG = ROOT / "playwright.f11f.config.ts"
SPEC = ROOT / "tests" / "e2e" / "f11f-commercial-delivery.spec.ts"
SEED = ROOT / "scripts" / "seed_f11f_commercial_runtime.py"
BENEFIT = ROOT / "scripts" / "prepare_f11f_resolved_benefit.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_f11f_usa_app_real_postgresql_e_sem_test_mode() -> None:
    workflow = _read(WORKFLOW)
    config = _read(CONFIG)

    assert "postgres:16" in workflow
    assert "FM_AI_ENV: staging" in workflow
    assert 'test -z "${FM_AI_TEST_MODE:-}"' in workflow
    assert "playwright.f11f.config.ts" in workflow
    assert "start-streamlit-f6d-commercial.cjs" in config
    assert "delete process.env.FM_AI_TEST_MODE" in config
    assert "tests/e2e-delivery/app_delivery.py" not in workflow
    assert "tests/e2e-delivery/app_delivery.py" not in config
    assert "sqlite" not in workflow.lower()


def test_f11f_prova_jornada_rbac_isolamento_e_evidencia_duravel() -> None:
    workflow = _read(WORKFLOW)
    spec = _read(SPEC)

    for prova in (
        "Evidencia PostgreSQL final F11-F",
        "pedidos_v1",
        "pagamentos_v1",
        "estoque_reservas_v1",
        "entregas_v1",
        "event_outbox_v1",
        "fm_auditoria_v1",
    ):
        assert prova in workflow

    for jornada in (
        "Pagamento na entrega",
        "fora_da_area_de_entrega",
        "GARCOM",
        "OTHER_GERENTE_EMAIL",
        "E-mail ou senha inválidos, ou usuário sem acesso a esta unidade",
        "prepare_f11f_resolved_benefit",
    ):
        assert jornada in spec

    assert "tenant-f11f-b" in workflow
    assert "unidade-f11f-b" in workflow


def test_f11f_seed_e_beneficio_sao_staging_only_e_nao_fabricam_autoridades_finais() -> None:
    seed = _read(SEED)
    benefit = _read(BENEFIT)

    assert 'os.getenv("FM_AI_TEST_MODE") == "1"' in seed
    assert 'os.getenv("FM_AI_ENV", "").strip().lower() != "staging"' in seed
    assert "RepositorioIdentidadesSQLAlchemy" in seed
    assert "EncryptedSQLAlchemyAddressStore" in seed
    assert "RepositorioPoliticaEntregaSQLAlchemy" in seed
    assert "PedidoORM" not in seed
    assert "PagamentoORM" not in seed
    assert "ReservaEstoqueORM" not in seed
    assert "EntregaORM" not in seed

    assert 'os.getenv("FM_AI_TEST_MODE") == "1"' in benefit
    assert 'os.getenv("FM_AI_ENV", "").strip().lower() != "staging"' in benefit
    assert "RepositorioCarrinhosDeliverySQLAlchemy" in benefit
    assert "salvar_cas" in benefit
    assert "desconto_cupom" in benefit
    assert "PedidoORM" not in benefit
    assert "PagamentoORM" not in benefit
