from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from application.legacy_store_reconciliation import (
    ErroReconciliacaoLojaLegada,
    SolicitacaoReconciliacaoLoja,
    reconciliar_loja_legada,
)
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import (
    PermissaoInsuficiente,
    TenantNaoAutorizado,
    UnidadeNaoAutorizada,
    UsuarioInativo,
)
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao
from migrations.runner import DEFAULT_MIGRATIONS, applied_versions, run_migrations
from test_mode import prepare_legacy_scope

_V0016 = "0016_integration_secret_vault_v1"
_V0027 = "0027_legacy_catalog_unit_scope_v1"
_V0028 = "0028_legacy_expiration_alert_integrity_v1"
_V0029 = "0029_internal_notification_recipients_v1"
_V0030 = "0030_migration_history_integrity_v1"
_V0031 = "0031_ai_usage_metering_v1"
_V0032 = "0032_ai_finops_read_model_v1"
_V0033 = "0033_delivery_policy_v1"
_V0034 = "0034_crm_customer_context_v1"
_V0035 = "0035_assistente_channel_runtime_v1"
_V0036 = "0036_administracao_proprietario_v1"
_TENANT = "tenant-reconciliado"
_UNIDADE = "unidade-reconciliada"
_LOJA = 71
_ENGINES: list[Engine] = []


@pytest.fixture(autouse=True)
def _descartar_engines() -> Iterator[None]:
    yield
    for engine in _ENGINES:
        engine.dispose()
    _ENGINES.clear()


def _index(version: str) -> int:
    return next(
        index
        for index, migration in enumerate(DEFAULT_MIGRATIONS)
        if migration.version == version
    )


def _engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}", future=True)
    _ENGINES.append(engine)

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def _identidade(
    *,
    papel: Papel = Papel.ADMINISTRADOR,
    sensivel: bool = True,
    tenant: str = _TENANT,
    unidades: frozenset[str] = frozenset({_UNIDADE}),
    ativo: bool = True,
) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="admin-reconciliacao",
        email="admin-reconciliacao@example.invalid",
        senha_hash="hash-nao-utilizado-no-servico",
        tenant_id=tenant,
        unidade_id=next(iter(unidades)),
        papeis=frozenset({papel}),
        unidades_permitidas=unidades,
        ativo=ativo,
        acesso_admin_sensivel=sensivel,
    )


def _reconciliar(engine: Engine, solicitacao: SolicitacaoReconciliacaoLoja, **kwargs):
    return reconciliar_loja_legada(
        engine,
        solicitacao,
        identidade=kwargs.pop("identidade", _identidade()),
        **kwargs,
    )


def _historico_ate_0016(engine: Engine) -> None:
    run_migrations(engine, migrations=DEFAULT_MIGRATIONS[: _index(_V0016) + 1])
    assert "lojas" not in inspect(engine).get_table_names()
    with engine.begin() as connection:
        for insumo_id, nome, saldo in (
            (1, "Farinha histórica", 12.0),
            (2, "Queijo histórico", 8.5),
            (3, "Tomate histórico", 5.0),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO insumos (
                        id, nome, unidade_medida, saldo_atual,
                        estoque_minimo, custo_unitario
                    ) VALUES (:id, :nome, 'kg', :saldo, 1, 2)
                    """
                ),
                {"id": insumo_id, "nome": nome, "saldo": saldo},
            )


def _avancar_ate_falha_0027(engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="nenhuma loja histórica cadastrada"):
        run_migrations(engine)
    with engine.begin() as connection:
        versions = applied_versions(connection)
        assert "0026_crm_consentimentos_historico_v1" in versions
        assert _V0027 not in versions
        assert _V0028 not in versions
        assert connection.execute(text("SELECT COUNT(*) FROM lojas")).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM fm_unidade_loja_legacy_v1")
        ).scalar_one() == 0


def _solicitacao(
    *,
    tenant: str = _TENANT,
    unidade: str = _UNIDADE,
    loja: int = _LOJA,
    nome: str | None = "Loja histórica reconciliada",
) -> SolicitacaoReconciliacaoLoja:
    return SolicitacaoReconciliacaoLoja(
        tenant_id=tenant,
        unidade_id=unidade,
        loja_id=loja,
        loja_nome=nome,
    )


def test_upgrade_0016_sem_reconciliacao_falha_fechado_sem_inventar_ownership(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path / "upgrade-sem-reconciliacao.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)

    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id, nome, saldo_atual, loja_id FROM insumos ORDER BY id")
        ).all()
    assert [tuple(row) for row in rows] == [
        (1, "Farinha histórica", 12.0, None),
        (2, "Queijo histórico", 8.5, None),
        (3, "Tomate histórico", 5.0, None),
    ]


def test_mensagem_0027_distingue_zero_lojas_de_multiplas_lojas(
    tmp_path: Path,
) -> None:
    zero = _engine(tmp_path / "zero-lojas.db")
    _historico_ate_0016(zero)
    _avancar_ate_falha_0027(zero)

    multiplas = _engine(tmp_path / "multiplas-lojas.db")
    _historico_ate_0016(multiplas)
    run_migrations(multiplas, migrations=DEFAULT_MIGRATIONS[: _index(_V0027)])
    with multiplas.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (71, 'Loja 71'), (72, 'Loja 72')"
            )
        )
    with pytest.raises(RuntimeError, match="ambiente multi-loja"):
        run_migrations(multiplas)


def test_reconciliacao_cria_loja_mapping_atomicamente_e_retomada_chega_a_0028(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path / "upgrade-reconciliado.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)

    resultado = _reconciliar(engine, _solicitacao())
    assert resultado.estado == "loja_e_mapping_criados"
    assert resultado.loja_criada is True
    assert resultado.mapping_criado is True

    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM lojas")).scalar_one() == 1
        mapping = connection.execute(
            text(
                "SELECT tenant_id, unidade_id, loja_id, ativo "
                "FROM fm_unidade_loja_legacy_v1"
            )
        ).one()
        assert tuple(mapping) == (_TENANT, _UNIDADE, _LOJA, 1)
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM fm_auditoria_v1 "
                "WHERE acao = 'loja_legada.reconciliar'"
            )
        ).scalar_one() == 1

    assert run_migrations(engine) == (
        _V0027,
        _V0028,
        _V0029,
        _V0030,
        _V0031,
        _V0032,
        _V0033,
        _V0034,
        _V0035,
        _V0036,
    )
    assert run_migrations(engine) == ()

    with engine.begin() as connection:
        insumos = connection.execute(
            text("SELECT id, nome, saldo_atual, loja_id FROM insumos ORDER BY id")
        ).all()
        assert [tuple(row) for row in insumos] == [
            (1, "Farinha histórica", 12.0, _LOJA),
            (2, "Queijo histórico", 8.5, _LOJA),
            (3, "Tomate histórico", 5.0, _LOJA),
        ]
        assert applied_versions(connection) == frozenset(
            migration.version for migration in DEFAULT_MIGRATIONS
        )
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_repeticao_identica_e_idempotente_e_conflitos_falham_fechado(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path / "idempotencia-conflitos.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)
    _reconciliar(engine, _solicitacao())

    repetida = _reconciliar(engine, _solicitacao(nome=None))
    assert repetida.estado == "mapping_idempotente"
    assert repetida.loja_criada is False
    assert repetida.mapping_criado is False

    with pytest.raises(ErroReconciliacaoLojaLegada, match="outra loja"):
        _reconciliar(engine, _solicitacao(loja=72, nome=None))
    with pytest.raises(ErroReconciliacaoLojaLegada, match="outro escopo"):
        _reconciliar(
            engine,
            _solicitacao(tenant="tenant-concorrente", unidade="unidade-b", nome=None),
            identidade=_identidade(
                tenant="tenant-concorrente", unidades=frozenset({"unidade-b"})
            ),
        )

    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM lojas")).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM fm_unidade_loja_legacy_v1")
        ).scalar_one() == 1


def test_criacao_de_loja_e_mapping_faz_rollback_atomico_em_falha(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path / "rollback-atomico.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TRIGGER bloquear_mapping_teste
                BEFORE INSERT ON fm_unidade_loja_legacy_v1
                BEGIN
                    SELECT RAISE(ABORT, 'falha injetada');
                END
                """
            )
        )

    with pytest.raises(IntegrityError, match="falha injetada"):
        _reconciliar(engine, _solicitacao())

    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM lojas")).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM fm_unidade_loja_legacy_v1")
        ).scalar_one() == 0
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM fm_auditoria_v1 "
                "WHERE acao = 'loja_legada.reconciliar'"
            )
        ).scalar_one() == 0


def test_loja_existente_exige_selecao_explicita_e_estado_compativel(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path / "loja-existente.db")
    _historico_ate_0016(engine)
    run_migrations(engine, migrations=DEFAULT_MIGRATIONS[: _index(_V0027)])
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO lojas (id, nome_fantasia) VALUES (71, 'Existente')")
        )

    with pytest.raises(ErroReconciliacaoLojaLegada, match="diverge"):
        _reconciliar(engine, _solicitacao())
    resultado = _reconciliar(engine, _solicitacao(nome=None))
    assert resultado.estado == "mapping_criado"


def test_fresh_install_permanece_convergente_em_banco_temporario(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path / "fresh.db")
    assert run_migrations(engine) == tuple(
        migration.version for migration in DEFAULT_MIGRATIONS
    )
    assert run_migrations(engine) == ()


def test_repeticao_com_nome_divergente_falha_fechado(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "idempotencia-nome-divergente.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)
    _reconciliar(engine, _solicitacao())

    with pytest.raises(ErroReconciliacaoLojaLegada, match="diverge"):
        _reconciliar(engine, _solicitacao(nome="Nome conflitante"))

    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM lojas")).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM fm_unidade_loja_legacy_v1")
        ).scalar_one() == 1


@pytest.mark.parametrize(
    ("identidade", "erro"),
    [
        (_identidade(sensivel=False), PermissaoInsuficiente),
        (_identidade(papel=Papel.GERENTE, sensivel=False), PermissaoInsuficiente),
        (_identidade(papel=Papel.GERENTE, sensivel=True), PermissaoInsuficiente),
        (_identidade(papel=Papel.ATENDIMENTO, sensivel=True), PermissaoInsuficiente),
        (_identidade(ativo=False), UsuarioInativo),
        (_identidade(tenant="tenant-divergente"), TenantNaoAutorizado),
        (
            _identidade(unidades=frozenset({"unidade-nao-autorizada"})),
            UnidadeNaoAutorizada,
        ),
    ],
)
def test_rbac_e_escopo_negam_sem_efeito_parcial_e_auditam(
    tmp_path: Path,
    identidade: IdentidadeUsuario,
    erro: type[Exception],
) -> None:
    engine = _engine(tmp_path / f"deny-{identidade.usuario_id}-{len(_ENGINES)}.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)

    with pytest.raises(erro):
        _reconciliar(engine, _solicitacao(), identidade=identidade)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM lojas")).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM fm_unidade_loja_legacy_v1")
        ).scalar_one() == 0
        auditoria = connection.execute(
            text(
                "SELECT usuario_id, resultado FROM fm_auditoria_v1 "
                "WHERE acao = 'loja_legada.reconciliar'"
            )
        ).one()
        assert tuple(auditoria) == (identidade.usuario_id, "negado")


def test_capability_ausente_nega_mesmo_admin_sensivel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path / "capability-ausente.db")
    _historico_ate_0016(engine)
    _avancar_ate_falha_0027(engine)
    sem_capability = MATRIZ_PADRAO[Papel.ADMINISTRADOR] - {
        Permissao.LOJA_LEGADA_RECONCILIAR
    }
    monkeypatch.setitem(MATRIZ_PADRAO, Papel.ADMINISTRADOR, sem_capability)

    with pytest.raises(PermissaoInsuficiente):
        _reconciliar(engine, _solicitacao())


def test_sqlite_padrao_sem_journal_memory_e_com_integridade(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "journal-padrao.db")
    _historico_ate_0016(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() != "memory"
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"


def test_sandbox_prepara_mapping_antes_do_backfill_0027(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path / "sandbox-legacy-scope.db")
    _historico_ate_0016(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO produtos "
                "(id, nome, categoria, preco_venda, custo_total_cmv, margem_exibicao) "
                "VALUES (1, 'Produto sandbox', 'Teste', 10, 2, '80%')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fichas_tecnicas "
                "(id, produto_id, insumo_id, quantidade_utilizada) "
                "VALUES (1, 1, 1, 1)"
            )
        )
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")

    prepare_legacy_scope(engine, tenant_id=_TENANT, unidade_id=_UNIDADE)

    with engine.begin() as connection:
        mapping = connection.execute(
            text(
                "SELECT loja_id FROM fm_unidade_loja_legacy_v1 "
                "WHERE tenant_id = :tenant AND unidade_id = :unidade AND ativo = TRUE"
            ),
            {"tenant": _TENANT, "unidade": _UNIDADE},
        ).scalar_one()
        assert int(
            connection.execute(
                text("SELECT loja_id FROM produtos WHERE id = 1")
            ).scalar_one()
        ) == int(mapping)
        assert int(
            connection.execute(
                text("SELECT loja_id FROM insumos WHERE id = 1")
            ).scalar_one()
        ) == int(mapping)
