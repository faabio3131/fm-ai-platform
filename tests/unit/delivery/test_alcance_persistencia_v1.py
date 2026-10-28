from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.delivery.alcance_rota import AlcanceEntrega
from infra.delivery.alcance_sqlalchemy import AlcanceEntregaORM, configurar_alcance, obter_alcance


def test_alcance_persistido_e_isolado_por_unidade():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    AlcanceEntregaORM.__table__.create(bind=engine)
    with Session(engine) as session:
        assert obter_alcance(session, tenant_id="t", unidade_id="u1") is None
        configurar_alcance(session, AlcanceEntrega("t", "u1", 10))
        configurar_alcance(session, AlcanceEntrega("t", "u2", 30))
        configurar_alcance(session, AlcanceEntrega("outro", "u1", 50))
        session.commit()
    with Session(engine) as session:
        assert obter_alcance(session, tenant_id="t", unidade_id="u1").limite_km == 10
        assert obter_alcance(session, tenant_id="t", unidade_id="u2").limite_km == 30
        assert obter_alcance(session, tenant_id="outro", unidade_id="u1").limite_km == 50
        configurar_alcance(session, AlcanceEntrega("t", "u1", 20))
        session.commit()
    with Session(engine) as session:
        assert obter_alcance(session, tenant_id="t", unidade_id="u1").limite_km == 20
        assert obter_alcance(session, tenant_id="t", unidade_id="u2").limite_km == 30
