"""Fitness F8-B: KDS comercial exige identidade/RBAC e preserva boundaries."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _texto(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_app_so_expoe_kds_para_identidade_com_visualizacao_de_producao() -> None:
    source = _texto("app.py")
    assert "from core.seguranca import Permissao" in source
    assert "_kds_disponivel = (" in source
    assert "kds_v1_enabled()" in source
    assert (
        "Permissao.PRODUCAO_VISUALIZAR in CURRENT_IDENTITY.permissoes"
        in source
    )
    assert source.count("if _kds_disponivel:") == 2


def test_renderer_kds_comercial_deriva_identidade_e_falha_fechado() -> None:
    source = _texto("core/kds/ui_runtime.py")
    assert '_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"' in source
    assert "IdentidadeUsuario" in source
    assert 'raise PermissionError("identidade_autenticada_ausente")' in source
    assert 'if exc.codigo == "permissao_insuficiente":' in source
    assert "Seu usuário não possui acesso ao KDS desta unidade." in source


def test_harness_kds_so_pode_ser_injetado_em_test_mode() -> None:
    source = _texto("core/kds/ui_runtime.py")
    guard = source.index('if os.getenv("FM_AI_TEST_MODE") != "1":')
    schema_test = source.index("from core.kds import preparar_schema_teste")
    assert guard < schema_test
    assert 'raise RuntimeError("contexto_kds_injetado_so_permitido_em_teste")' in source
    assert "permitir_simulacao_offline and modo_e2e" in source


def test_ui_kds_nao_assume_ownership_de_commit() -> None:
    for path in ("core/kds/ui_runtime.py", "core/kds/ui_roteamento.py"):
        assert ".commit(" not in _texto(path)

    transacoes = _texto("application/kds_transacoes.py")
    assert "with UnitOfWorkV1(session_factory) as uow:" in transacoes
    assert "uow.commit()" in transacoes


def test_migration_kds_oficial_permanece_no_runner_comercial() -> None:
    source = _texto("migrations/runner.py")
    assert "0010_kds_authoritative_runtime_v1" in source
    assert "KDSBase.metadata.create_all" in source
    assert "migrations.kds_v1" not in source
