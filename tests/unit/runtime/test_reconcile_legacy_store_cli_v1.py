from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError

import scripts.reconcile_legacy_store_v1 as cli
from application.legacy_store_reconciliation import (
    ErroReconciliacaoLojaLegada,
    ResultadoReconciliacaoLoja,
    SolicitacaoReconciliacaoLoja,
)
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import CredenciaisInvalidas, UsuarioInativo
from core.seguranca.permissoes import Papel

_ARGS = [
    "--admin-email",
    "admin@example.invalid",
    "--tenant-id",
    "tenant-explicito",
    "--unidade-id",
    "unidade-explicita",
    "--loja-id",
    "71",
]


def _engine() -> Engine:
    return create_engine("sqlite+pysqlite:///:memory:")


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FM_AI_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///isolado-temporario.db")
    monkeypatch.setenv("FM_AI_TENANT_ID", "tenant-explicito")
    monkeypatch.setenv("FM_AI_UNIDADE_ID", "unidade-explicita")
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)


def _runtime_ok(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> None:
    monkeypatch.setattr(
        cli,
        "load_runtime_settings",
        lambda: SimpleNamespace(
            tenant_id="tenant-explicito", unidade_id="unidade-explicita"
        ),
    )
    monkeypatch.setattr(cli, "build_engine", lambda _settings: engine)
    monkeypatch.setattr(cli, "check_database_health", lambda _engine: SimpleNamespace(ok=True))


@pytest.mark.parametrize("ausente", cli._REQUIRED_ENV)
def test_cli_exige_env_antes_de_construir_engine(
    monkeypatch: pytest.MonkeyPatch, ausente: str
) -> None:
    _env(monkeypatch)
    monkeypatch.delenv(ausente, raising=False)
    monkeypatch.setattr(
        cli,
        "build_engine",
        lambda _settings: pytest.fail("engine não pode ser construído"),
    )
    assert cli.main(_ARGS) == 2


@pytest.mark.parametrize(
    ("chave", "valor"),
    [
        ("FM_AI_ENV", "test"),
        ("FM_AI_TEST_MODE", "true"),
        ("DATABASE_URL", "sqlite:///./banco_erp_local.db"),
        ("FM_AI_TENANT_ID", "tenant-local"),
        ("FM_AI_UNIDADE_ID", "unidade-local"),
    ],
)
def test_cli_rejeita_test_defaults_e_fallback_sqlite(
    monkeypatch: pytest.MonkeyPatch, chave: str, valor: str
) -> None:
    _env(monkeypatch)
    monkeypatch.setenv(chave, valor)
    assert cli.main(_ARGS) == 2


def test_cli_nao_expoe_actor_id_textual() -> None:
    destinos = {action.dest for action in cli._parser()._actions}
    assert "actor_id" not in destinos


def test_solicitacao_normaliza_campos_e_impoe_limites() -> None:
    solicitacao = SolicitacaoReconciliacaoLoja(
        tenant_id="  tenant-explicito  ",
        unidade_id="  unidade-explicita  ",
        loja_id=71,
        loja_nome="  Loja   Canônica  ",
    )
    assert solicitacao.tenant_id == "tenant-explicito"
    assert solicitacao.unidade_id == "unidade-explicita"
    assert solicitacao.loja_nome == "Loja Canônica"

    with pytest.raises(ErroReconciliacaoLojaLegada, match="limite de 64"):
        SolicitacaoReconciliacaoLoja("t" * 65, "unidade", 71)
    with pytest.raises(ErroReconciliacaoLojaLegada, match="limite de 255"):
        SolicitacaoReconciliacaoLoja("tenant", "unidade", 71, "L" * 256)


def test_executar_autentica_e_deriva_ator_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identidade = IdentidadeUsuario(
        usuario_id="ator-autenticado",
        email="admin@example.invalid",
        senha_hash="hash-persistido",
        tenant_id="tenant-explicito",
        unidade_id="unidade-explicita",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({"unidade-explicita"}),
        acesso_admin_sensivel=True,
    )
    observado: dict[str, object] = {}

    class _SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return None

    class _Auth:
        def __init__(self, _repo):
            pass

        def autenticar(self, *, email: str, password: str):
            observado["credenciais"] = (email, password)
            return identidade

    monkeypatch.setattr(cli, "Session", lambda _engine: _SessionContext())
    monkeypatch.setattr(cli, "RepositorioIdentidadesSQLAlchemy", lambda _session: object())
    monkeypatch.setattr(cli, "ServicoAutenticacao", _Auth)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "senha-temporaria")

    def _reconciliar(_engine, _solicitacao, *, identidade):
        observado["ator"] = identidade.usuario_id
        return ResultadoReconciliacaoLoja("mapping_criado", False, True, "corr-1")

    monkeypatch.setattr(cli, "reconciliar_loja_legada", _reconciliar)
    estado, correlation_id = cli._executar(
        Namespace(
            admin_email="admin@example.invalid",
            tenant_id="tenant-explicito",
            unidade_id="unidade-explicita",
            loja_id=71,
            loja_nome=None,
        ),
        _engine(),
    )
    assert (estado, correlation_id) == ("mapping_criado", "corr-1")
    assert observado == {
        "credenciais": ("admin@example.invalid", "senha-temporaria"),
        "ator": "ator-autenticado",
    }


@pytest.mark.parametrize("erro", [CredenciaisInvalidas("x"), UsuarioInativo("x")])
def test_executar_falha_fechado_para_usuario_ausente_ou_inativo(
    monkeypatch: pytest.MonkeyPatch, erro: Exception
) -> None:
    class _SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return None

    class _Auth:
        def __init__(self, _repo):
            pass

        def autenticar(self, **_kwargs):
            raise erro

    monkeypatch.setattr(cli, "Session", lambda _engine: _SessionContext())
    monkeypatch.setattr(cli, "RepositorioIdentidadesSQLAlchemy", lambda _session: object())
    monkeypatch.setattr(cli, "ServicoAutenticacao", _Auth)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "senha-temporaria")
    monkeypatch.setattr(
        cli,
        "reconciliar_loja_legada",
        lambda *_args, **_kwargs: pytest.fail("reconciliação não pode ser chamada"),
    )
    with pytest.raises(type(erro)):
        cli._executar(
            Namespace(
                admin_email="ausente@example.invalid",
                tenant_id="tenant-explicito",
                unidade_id="unidade-explicita",
                loja_id=71,
                loja_nome=None,
            ),
            _engine(),
        )


def test_cli_sanitiza_erro_e_descarta_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch)
    engine = _engine()
    disposed: list[bool] = []
    event.listen(engine, "engine_disposed", lambda _engine: disposed.append(True))
    _runtime_ok(monkeypatch, engine)
    monkeypatch.setattr(
        cli,
        "_executar",
        lambda _args, _engine: (_ for _ in ()).throw(
            SQLAlchemyError("DATABASE_URL=senha-super-secreta SELECT * FROM usuarios")
        ),
    )

    assert cli.main(_ARGS) == 4
    captured = capsys.readouterr()
    assert captured.err == "Reconciliação indisponível por erro de persistência.\n"
    assert "DATABASE_URL" not in captured.err
    assert "senha-super-secreta" not in captured.err
    assert disposed == [True]
