from __future__ import annotations

import inspect

from application import delivery_composicao
from infra.delivery import carrinhos_sqlalchemy
from migrations.runner import DEFAULT_MIGRATIONS


def test_f11b_composicao_comercial_nao_depende_de_runtime_de_teste_ou_demo() -> None:
    source = inspect.getsource(delivery_composicao).lower()
    assert "runtime_teste" not in source
    assert "runtimedeliveryteste" not in source
    assert "tenant-demo" not in source
    assert "unidade-demo" not in source
    assert "cliente-demo" not in source
    assert "repositoriocarrinhosdeliverysqlalchemy" in source


def test_f11b_repositorio_nao_controla_commit_ou_rollback() -> None:
    source = inspect.getsource(carrinhos_sqlalchemy).lower()
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "salvar_cas" in source
    assert "expected_version" in source


def test_f11b_migration_do_estado_delivery_e_ultima_e_oficial() -> None:
    assert DEFAULT_MIGRATIONS[-1].version == "0038_delivery_channel_state_v1"
    assert DEFAULT_MIGRATIONS[-1].revert is not None
