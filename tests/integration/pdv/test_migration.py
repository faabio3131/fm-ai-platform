from sqlalchemy import create_engine, inspect

from migrations.pdv_v1 import downgrade, upgrade


def test_migration_aditiva_em_memoria() -> None:
    engine = create_engine("sqlite:///:memory:")
    upgrade(engine)
    assert set(inspect(engine).get_table_names()) == {
        "pdv_efeitos_compat_v1",
        "pdv_finalizacoes_pendentes_v1",
        "pdv_reconciliacoes_v1",
        "pdv_venda_legada_links_v1",
    }
    downgrade(engine)
    assert inspect(engine).get_table_names() == []
